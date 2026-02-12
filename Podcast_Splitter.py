import argparse
import logging
import subprocess
import sys
import shutil
import re
import os
from typing import Dict, List, NamedTuple, Optional, Tuple
from pathlib import Path

from mutagen.id3 import ID3
from mutagen.mp3 import MP3

# Configure logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='%(levelname)s: %(message)s')


class ProcessResult(NamedTuple):
    """Holds the results of the processing operation."""
    originals_split: Dict[str, List[str]]
    files_moved: int
    empty_dirs_removed: int
    total_library_size: float
    failed_files: List[Path]


class PodcastProcessor:
    """
    Processes podcast files: splits long files and organizes them.
    This class is stateless and operates on the directories provided to its methods.
    """
    # Configuration constants
    SPLIT_DURATION_MINUTES = 10.0
    MIN_LENGTH_SECONDS = SPLIT_DURATION_MINUTES * 60 + 1
    MP3SPLT_OUTPUT_RE = re.compile(r"info: creating file '([^']*)'")

    def __init__(self, mp3splt_path: Path):
        if not mp3splt_path.exists():
            raise FileNotFoundError(f"mp3splt executable not found at {mp3splt_path}")
        self.mp3splt_path = mp3splt_path

    def process_directory(self, source_dir: Path, output_dir: Path) -> ProcessResult:
        """Orchestrates the splitting and organization of podcast files."""
        if not source_dir.exists():
            logging.warning(f"Source directory not found: {source_dir}")
            return ProcessResult({}, 0, 0, 0.0, [])

        files_to_organize: List[Path] = []
        originals_split: Dict[str, List[str]] = {}
        failed_files: List[Path] = []

        logging.info(f"--- Phase 1: Scanning and Processing Files in {source_dir} ---")
        for file_path in sorted(source_dir.glob("*.mp3")):
            new_files, original_album, failure = self._process_single_file(file_path)
            
            if failure:
                failed_files.append(failure)
            if new_files:
                files_to_organize.extend(new_files)
            if original_album:
                originals_split.setdefault(original_album, []).append(file_path.name)

        # Phase 2: Organize all collected files
        moved_count, org_failures = self._organize_files(files_to_organize, output_dir)
        failed_files.extend(org_failures)

        # Phase 3: Cleanup and calculate final size
        empty_dirs_removed = self._cleanup_empty_dirs(output_dir)
        total_size = sum(p.stat().st_size for p in output_dir.rglob("*.mp3"))

        return ProcessResult(
            originals_split=originals_split,
            files_moved=moved_count,
            empty_dirs_removed=empty_dirs_removed,
            total_library_size=total_size,
            failed_files=failed_files,
        )

    def _process_single_file(self, file_path: Path) -> Tuple[List[Path], Optional[str], Optional[Path]]:
        """
        Processes one file, either splitting it or marking it for organization.
        Returns (files_to_organize, original_album_if_split, failed_path).
        """
        try:
            tags = ID3(file_path)
            album_title_frame = tags.get("TALB")
            if not album_title_frame:
                logging.warning(f"Skipping '{file_path.name}': No album tag found.")
                return [], None, file_path

            album_title = str(album_title_frame)
            audio = MP3(file_path)

            if audio.info.length < self.MIN_LENGTH_SECONDS:
                logging.info(f"'{file_path.name}' is short. Marking for organization.")
                return [file_path], None, None
            else:
                logging.info(f"'{file_path.name}' is long. Attempting to split.")
                album_artist = str(tags.get("TPE2", "Unknown Artist")).strip()
                
                new_chunks = self._run_split_cmd(file_path, album_artist)
                if new_chunks:
                    logging.info(f"Successfully split '{file_path.name}' into {len(new_chunks)} chunks.")
                    file_path.unlink()  # Delete original file
                    return new_chunks, album_title, None
                else:
                    logging.error(f"Failed to split '{file_path.name}'. It will be left in place.")
                    return [], None, file_path

        except Exception as e:
            logging.error(f"An unexpected error occurred while processing {file_path.name}: {e}")
            return [], None, file_path

    def _run_split_cmd(self, file_path: Path, album_artist: str) -> List[Path]:
        """Executes the mp3splt command and returns a list of created chunk paths."""
        command = [
            str(self.mp3splt_path), "-t", f"{self.SPLIT_DURATION_MINUTES}.00",
            "-g", f"r%[@o,@g=Podcast,@n=-2,@a=\"{album_artist}\",@t=#t_#mm_#ss__#Mm_#Ss]",
            str(file_path)
        ]
        logging.debug(f"Running command: {' '.join(command)}")
        try:
            result = subprocess.run(
                command, check=True, capture_output=True, text=True, cwd=file_path.parent
            )
            chunk_names = self.MP3SPLT_OUTPUT_RE.findall(result.stdout)
            if not chunk_names:
                logging.warning(f"mp3splt ran for {file_path.name} but no output files were detected.")
                return []
            return [file_path.parent / name for name in chunk_names]
        except subprocess.CalledProcessError as e:
            logging.error(f"Split command failed for {file_path.name}:\n{e.stderr}")
            return []

    def _organize_files(self, files_to_move: List[Path], output_dir: Path) -> Tuple[int, List[Path]]:
        """Moves files to their final destination. Returns (moved_count, failed_paths)."""
        logging.info(f"--- Phase 2: Organizing {len(files_to_move)} Files ---")
        moved_count = 0
        failed_paths = []
        for file_path in files_to_move:
            if not file_path.exists():
                logging.warning(f"Cannot move '{file_path.name}' as it no longer exists.")
                continue
            try:
                tags = ID3(file_path)
                album_title = str(tags.get("TALB", "Unknown Album"))
                folder_name = self._sanitize_folder_name(album_title)
                dest_dir = output_dir / folder_name
                dest_dir.mkdir(parents=True, exist_ok=True)

                shutil.move(str(file_path), str(dest_dir / file_path.name))
                moved_count += 1
            except Exception as e:
                logging.error(f"Error moving {file_path.name}: {e}")
                failed_paths.append(file_path)
        return moved_count, failed_paths

    @staticmethod
    def _cleanup_empty_dirs(output_dir: Path) -> int:
        """Removes empty subdirectories from the output folder."""
        logging.info("--- Phase 3: Cleaning Up Empty Directories ---")
        removed_count = 0
        if not output_dir.exists():
            return 0
        for dirpath, _, _ in sorted(os.walk(output_dir), key=lambda x: x[0].count(os.sep), reverse=True):
            if dirpath == str(output_dir):
                continue
            try:
                p = Path(dirpath)
                if not any(p.iterdir()):
                    p.rmdir()
                    logging.info(f"Removed empty directory: {p}")
                    removed_count += 1
            except OSError as e:
                logging.error(f"Error removing directory {dirpath}: {e}")
        return removed_count

    @staticmethod
    def _sanitize_folder_name(name: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', '-', name).strip()


def print_summary_report(result: ProcessResult):
    """Prints a final report of the operations."""
    def sizeof_fmt(num: float, suffix: str = 'B') -> str:
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Yi{suffix}"

    print("\n" + "=" * 50)
    print("FINAL REPORT")
    print("=" * 50)
    print(f"Original Files Split:       {len(result.originals_split)}")
    print(f"Total Chunks/Files Moved:   {result.files_moved}")
    print(f"Empty Directories Removed:  {result.empty_dirs_removed}")
    print(f"Total Library Size:         {sizeof_fmt(result.total_library_size)}")
    print(f"Errors/Files Not Processed: {len(result.failed_files)}")

    if result.failed_files:
        print("\nFILES NOT PROCESSED (see logs for details):")
        for f in result.failed_files:
            print(f" - {f.name}")

    if result.originals_split:
        print("\nORIGINAL FILES PROCESSED:")
        for album, files in result.originals_split.items():
            print(f"\n[{album}]")
            for f in files:
                print(f"  > {f}")
    print("\n" + "=" * 50)


def main():
    """Main function to parse arguments and run the PodcastProcessor."""
    parser = argparse.ArgumentParser(description="Split and organize long MP3 podcast files.")
    parser.add_argument(
        "--input-dir", type=Path, required=True,
        help="The directory containing podcast files to split."
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="The base directory for storing organized podcasts."
    )
    parser.add_argument(
        "--mp3splt-path", type=Path, required=True,
        help="The full path to the mp3splt executable."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose DEBUG logging."
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        processor = PodcastProcessor(mp3splt_path=args.mp3splt_path)
        result = processor.process_directory(source_dir=args.input_dir, output_dir=args.output_dir)
        print_summary_report(result)
    except FileNotFoundError as e:
        logging.critical(e)
        sys.exit(1)
    except Exception as e:
        logging.critical(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
