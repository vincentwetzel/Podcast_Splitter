import argparse
import json
import logging
import subprocess
import sys
import shutil
import re
import os
from typing import Dict, List, NamedTuple, Optional, Tuple
from pathlib import Path

from mutagen._file import File as MutagenFile
from mutagen.id3 import TCON
from send2trash import send2trash

# Configure logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='%(levelname)s: %(message)s')

# Supported audio format extensions
SUPPORTED_EXTENSIONS = {'.mp3', '.opus', '.m4a', '.aac', '.ogg', '.flac', '.wav'}


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
    SPLIT_DURATION_SECONDS = SPLIT_DURATION_MINUTES * 60
    MIN_LENGTH_SECONDS = SPLIT_DURATION_SECONDS + 1

    def __init__(self, ffmpeg_path: Optional[Path] = None):
        if ffmpeg_path is None:
            # Try to find ffmpeg in PATH using shutil.which
            ffmpeg_path_str = shutil.which("ffmpeg")

            if ffmpeg_path_str is None:
                # Fallback: use 'where' command which queries the system PATH directly
                try:
                    result = subprocess.run(
                        ["where", "ffmpeg"],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    if result.stdout:
                        ffmpeg_path_str = result.stdout.strip().split('\n')[0].strip()
                        if not Path(ffmpeg_path_str).exists():
                            ffmpeg_path_str = None
                except subprocess.CalledProcessError:
                    pass
                except Exception:
                    pass

            if ffmpeg_path_str is None:
                raise FileNotFoundError(
                    "ffmpeg executable not found in system PATH. Please install ffmpeg and ensure it is in your PATH, "
                    "or provide the path via --ffmpeg-path."
                )
            self.ffmpeg_path = Path(ffmpeg_path_str)
        else:
            if not ffmpeg_path.exists():
                raise FileNotFoundError(f"ffmpeg executable not found at {ffmpeg_path}")
            self.ffmpeg_path = ffmpeg_path

    def process_directory(self, source_dir: Path, output_dir: Path) -> ProcessResult:
        """Orchestrates the splitting and organization of podcast files."""
        if not source_dir.exists():
            logging.warning(f"Source directory not found: {source_dir}")
            return ProcessResult({}, 0, 0, 0.0, [])

        # Clean up any leftover temp directories and orphaned chunks from previous runs
        self._cleanup_leftovers(source_dir)

        files_to_organize: List[Path] = []
        originals_split: Dict[str, List[str]] = {}
        originals_to_recycle: Dict[str, Path] = {} # Map original filename to its Path
        failed_files: List[Path] = []

        logging.info(f"--- Phase 1: Scanning and Processing Files in {source_dir} ---")
        # Scan for all supported audio formats
        for ext in SUPPORTED_EXTENSIONS:
            for file_path in sorted(source_dir.glob(f"*{ext}")):
                new_files, original_album, failure = self._process_single_file(file_path)

                if failure:
                    failed_files.append(failure)
                if new_files:
                    files_to_organize.extend(new_files)
                if original_album:
                    # Track original file by its unique filename (not album title)
                    original_key = file_path.name
                    originals_to_recycle[original_key] = file_path
                    # Group chunks by original file key
                    chunk_names = [chunk.name for chunk in new_files]
                    originals_split.setdefault(original_key, []).extend(chunk_names)

        # Phase 2: Organize all collected files
        moved_count, org_failures = self._organize_files(files_to_organize, output_dir)
        failed_files.extend(org_failures)
        
        self._recycle_successful_originals(originals_to_recycle, originals_split, failed_files)

        # Phase 3: Cleanup and calculate final size
        empty_dirs_removed = self._cleanup_empty_dirs(output_dir)
        # Calculate size of all supported audio files
        total_size = 0.0
        for ext in SUPPORTED_EXTENSIONS:
            total_size += sum(p.stat().st_size for p in output_dir.rglob(f"*{ext}"))

        return ProcessResult(
            originals_split=originals_split,
            files_moved=moved_count,
            empty_dirs_removed=empty_dirs_removed,
            total_library_size=total_size,
            failed_files=failed_files,
        )

    def _get_metadata(self, file_path: Path) -> Tuple[Optional[str], Optional[str], Optional[float]]:
        """
        Extract metadata from audio file.
        Returns (album_title, album_artist, duration) or (None, None, None) on failure.
        """
        try:
            audio = MutagenFile(file_path, easy=False)
            if audio is None:
                return None, None, None
            
            # Get duration
            duration = None
            if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                duration = audio.info.length
            
            if duration is None:
                return None, None, None
            
            # Try to extract album title and artist from various metadata formats
            album_title = None
            album_artist = None
            
            if hasattr(audio, 'tags') and audio.tags:
                tags = audio.tags

                # Try ID3 tags (MP3)
                album_title = str(tags.get("TALB")) if tags.get("TALB") else None
                album_artist = str(tags.get("TPE2")) if tags.get("TPE2") else None

                # Helper to find a tag case-insensitively
                def find_tag(*names):
                    for key in tags.keys():
                        if key.upper() in names:
                            return str(tags[key][0])
                    return None

                # Try Vorbis comments (Opus, OGG)
                if album_title is None:
                    album_title = find_tag("ALBUM")
                if album_artist is None:
                    album_artist = find_tag("ALBUMARTIST")

                # Fallback to title if no album found (common for podcasts)
                if album_title is None:
                    album_title = find_tag("TITLE", "TIT2")

                # Fallback to artist if no album artist found
                if album_artist is None:
                    album_artist = find_tag("ARTIST", "TPE1")

                # Try MP4-style tags (M4A, AAC)
                if album_title is None and "\xa9alb" in tags:
                    album_title = str(tags["\xa9alb"][0])
                if album_artist is None and "aART" in tags:
                    album_artist = str(tags["aART"][0])
            
            return album_title, album_artist, duration
            
        except Exception as e:
            logging.debug(f"Failed to extract metadata from {file_path.name}: {e}")
            return None, None, None

    def _process_single_file(self, file_path: Path) -> Tuple[List[Path], Optional[str], Optional[Path]]:
        """
        Processes one file, either splitting it or marking it for organization.
        Returns (files_to_organize, original_album_if_split, failed_path).
        """
        try:
            album_title, album_artist, file_length = self._get_metadata(file_path)
            
            if album_title is None:
                logging.warning(f"Skipping '{file_path.name}': No album/title metadata found.")
                return [], None, file_path
            
            if file_length is None:
                logging.warning(f"Skipping '{file_path.name}': Unable to determine file length.")
                return [], None, file_path

            if file_length < self.MIN_LENGTH_SECONDS:
                logging.info(f"'{file_path.name}' is short ({file_length:.0f}s). Marking for organization.")
                # Set genre before organizing
                self._set_genre_podcast(file_path)
                return [file_path], None, None
            else:
                logging.info(f"'{file_path.name}' is long ({file_length:.0f}s). Attempting to split.")
                
                # Use default if no album artist found
                if album_artist is None:
                    album_artist = "Unknown Artist"
                else:
                    album_artist = album_artist.strip()

                new_chunks = self._run_ffmpeg_split(file_path, album_artist)
                if new_chunks:
                    logging.info(f"Successfully split '{file_path.name}' into {len(new_chunks)} chunks.")
                    return new_chunks, album_title, None
                else:
                    logging.error(f"Failed to split '{file_path.name}'. It will be left in place.")
                    return [], None, file_path

        except Exception as e:
            logging.exception(f"An unexpected error occurred while processing {file_path.name}: {e}")
            return [], None, file_path

    def _run_ffmpeg_split(self, file_path: Path, album_artist: str) -> List[Path]:
        """
        Uses ffmpeg to split audio file into chunks of SPLIT_DURATION_MINUTES.
        Returns a list of created chunk paths.
        """
        # Get file extension and length
        output_ext = file_path.suffix
        
        # Get file length for proper timestamp calculation
        _, _, file_length = self._get_metadata(file_path)
        if file_length is None:
            logging.error(f"Unable to get file length for {file_path.name}")
            return []
        
        # Build ffmpeg command to split into chunks - output directly to source directory
        chunk_pattern = f"%03d{output_ext}"
        output_pattern = str(file_path.parent / f"{file_path.stem}_chunk_{chunk_pattern}")
        
        command = [
            str(self.ffmpeg_path),
            "-i", str(file_path),
            "-f", "segment",
            "-segment_time", str(self.SPLIT_DURATION_SECONDS),
            "-c", "copy",  # Copy codec, don't re-encode
            "-map", "0:a",  # Only map audio streams
            "-reset_timestamps", "1",
            output_pattern
        ]
        
        logging.debug(f"Running ffmpeg command: {' '.join(command)}")
        
        try:
            result = subprocess.run(
                command, 
                check=True, 
                stdout=subprocess.DEVNULL,  # Don't capture stdout for performance
                stderr=subprocess.PIPE,
                text=True,
                cwd=file_path.parent
            )
            
            # Get all created chunk files
            # Find files that match the pattern: {stem}_chunk_{digits}{ext}
            chunk_prefix = f"{file_path.stem}_chunk_"
            chunks = []
            for f in file_path.parent.iterdir():
                if f.is_file() and f.name.startswith(chunk_prefix) and f.name.endswith(output_ext):
                    # Verify the middle part is numeric (chunk number)
                    middle = f.name[len(chunk_prefix):-len(output_ext)]
                    if middle.isdigit():
                        chunks.append(f)
            chunks = sorted(chunks)
            
            if not chunks:
                logging.warning(f"ffmpeg ran for {file_path.name} but no output files were detected.")
                if result.stderr:
                    logging.warning(f"ffmpeg stderr:\n{result.stderr}")
                return []
            
            # Rename chunks to the expected format with timestamps
            final_chunks = []
            for i, chunk in enumerate(chunks):
                # Calculate start and end times
                start_seconds = i * self.SPLIT_DURATION_SECONDS
                end_seconds = min((i + 1) * self.SPLIT_DURATION_SECONDS, file_length)

                start_min = int(start_seconds // 60)
                start_sec = int(start_seconds % 60)
                end_min = int(end_seconds // 60)
                end_sec = int(end_seconds % 60)

                # Format: {stem}_{start_time}__{end_time}{ext}
                # Example: Flood the Zone_40m_00s__50m_00s.mp3
                new_name = f"{file_path.stem}_{start_min:02d}m_{start_sec:02d}s__{end_min:02d}m_{end_sec:02d}s{output_ext}"
                new_path = file_path.parent / new_name

                # Move and rename
                chunk.rename(new_path)
                final_chunks.append(new_path)

            # Set genre and title for all chunks
            for chunk_path in final_chunks:
                self._set_genre_podcast(chunk_path)
                # Set title tag to match the filename (without extension)
                self._set_title_tag(chunk_path, chunk_path.stem)

            return final_chunks
            
        except subprocess.CalledProcessError as e:
            logging.error(f"Split command failed for {file_path.name}:")
            if e.stderr:
                logging.error(f"stderr: {e.stderr}")
            return []
        except Exception as e:
            logging.error(f"Unexpected error during ffmpeg execution: {e}")
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
                # Try to get album title using improved metadata extraction
                album_title, _, _ = self._get_metadata(file_path)
                if album_title is None:
                    album_title = "Unknown Album"

                folder_name = self._sanitize_folder_name(album_title)
                dest_dir = output_dir / folder_name
                dest_dir.mkdir(parents=True, exist_ok=True)

                dest_path = dest_dir / file_path.name
                shutil.move(file_path, dest_path)
                
                moved_count += 1
            except Exception as e:
                logging.error(f"Error moving {file_path.name}: {e}")
                failed_paths.append(file_path)
        return moved_count, failed_paths

    def _recycle_successful_originals(self, originals_to_recycle: Dict[str, Path], originals_split: Dict[str, List[str]], failed_files: List[Path]):
        """Sends original files to the recycle bin if their chunks were processed without error."""
        failed_file_names = {f.name for f in failed_files}

        for original_key, original_path in originals_to_recycle.items():
            # Check if any of the chunks from this original failed to move
            split_files = originals_split.get(original_key, [])
            was_successful = True
            for chunk_name in split_files:
                if chunk_name in failed_file_names:
                    was_successful = False
                    break
            
            if was_successful and original_path.exists():
                try:
                    send2trash(str(original_path))
                    logging.info(f"Successfully recycled original file: {original_path.name}")
                except Exception as e:
                    logging.error(f"Failed to recycle original file {original_path.name}: {e}")

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

    def _set_genre_podcast(self, file_path: Path):
        """Set the genre tag to 'Podcast' for an audio file."""
        try:
            audio = MutagenFile(file_path, easy=False)
            if audio is None:
                logging.warning(f"Cannot set genre for {file_path.name}: Unable to read file")
                return

            # Get the file extension to determine format
            ext = file_path.suffix.lower()

            if ext == '.mp3':
                # ID3 tags for MP3
                if audio.tags:
                    audio.tags["TCON"] = TCON(encoding=3, text="Podcast")
            elif ext in {'.opus', '.ogg', '.flac'}:
                # Vorbis comments for Opus, OGG, FLAC
                if audio.tags:
                    audio.tags["GENRE"] = "Podcast"
                else:
                    logging.debug(f"No tags found in {file_path.name}")
            elif ext in {'.m4a', '.aac'}:
                # MP4 tags for M4A, AAC
                if audio.tags:
                    audio.tags["\xa9gen"] = "Podcast"
                else:
                    logging.debug(f"No tags found in {file_path.name}")
            else:
                # Generic attempt for other formats
                if audio.tags:
                    audio.tags["GENRE"] = "Podcast"

            audio.save()
            logging.debug(f"Set genre to 'Podcast' for {file_path.name}")
        except Exception as e:
            logging.warning(f"Failed to set genre for {file_path.name}: {e}")

    def _set_title_tag(self, file_path: Path, title: str):
        """Set the title tag for an audio file."""
        try:
            audio = MutagenFile(file_path, easy=False)
            if audio is None:
                logging.warning(f"Cannot set title for {file_path.name}: Unable to read file")
                return

            ext = file_path.suffix.lower()

            if ext == '.mp3':
                from mutagen.id3 import TIT2
                if audio.tags:
                    audio.tags["TIT2"] = TIT2(encoding=3, text=title)
            elif ext in {'.opus', '.ogg', '.flac'}:
                if audio.tags:
                    audio.tags["TITLE"] = title
                else:
                    logging.debug(f"No tags found in {file_path.name}")
            elif ext in {'.m4a', '.aac'}:
                if audio.tags:
                    audio.tags["\xa9nam"] = title
                else:
                    logging.debug(f"No tags found in {file_path.name}")
            else:
                if audio.tags:
                    audio.tags["TITLE"] = title

            audio.save()
            logging.debug(f"Set title to '{title}' for {file_path.name}")
        except Exception as e:
            logging.warning(f"Failed to set title for {file_path.name}: {e}")

    @staticmethod
    def _cleanup_leftovers(source_dir: Path):
        """Cleans up temp directories and orphaned chunk files from previous failed runs."""
        cleaned_dirs = 0
        cleaned_files = 0
        
        # Remove _temp_* directories
        for item in source_dir.iterdir():
            if item.is_dir() and item.name.startswith('_temp_'):
                try:
                    shutil.rmtree(item)
                    logging.info(f"Removed leftover temp directory: {item.name}")
                    cleaned_dirs += 1
                except Exception as e:
                    logging.warning(f"Failed to remove temp directory {item.name}: {e}")
        
        # Remove orphaned chunk files
        for item in source_dir.iterdir():
            if item.is_file() and '_chunk_' in item.name and item.suffix in SUPPORTED_EXTENSIONS:
                try:
                    item.unlink()
                    logging.info(f"Removed orphaned chunk file: {item.name}")
                    cleaned_files += 1
                except Exception as e:
                    logging.warning(f"Failed to remove chunk file {item.name}: {e}")
        
        if cleaned_dirs > 0 or cleaned_files > 0:
            logging.info(f"Cleaned up {cleaned_dirs} temp directories and {cleaned_files} orphaned chunk files")


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


def load_settings(config_path: Path) -> Dict[str, str]:
    """Load default settings from a JSON file.

    The settings file should be a JSON object with keys:
      - input_dir
      - output_dir
      - ffmpeg_path (optional, will use system PATH if not provided)

    Any missing or invalid values will be ignored.
    """

    if not config_path.exists():
        logging.debug(f"Settings file not found: {config_path}")
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Settings file must contain a JSON object")
        return {k: str(v) for k, v in data.items() if v is not None}
    except Exception as e:
        logging.error(f"Failed to load settings from {config_path}: {e}")
        return {}


def main():
    """Main function to parse arguments and run the PodcastProcessor."""
    default_config_path = Path(__file__).resolve().parent / "settings.json"

    parser = argparse.ArgumentParser(description="Split and organize long audio podcast files.")
    parser.add_argument(
        "--config", type=Path, default=default_config_path,
        help=f"Path to a JSON settings file (default: {default_config_path})"
    )
    parser.add_argument(
        "--input-dir", type=Path, required=False,
        help="The directory containing podcast files to split."
    )
    parser.add_argument(
        "--output-dir", type=Path, required=False,
        help="The base directory for storing organized podcasts."
    )
    parser.add_argument(
        "--ffmpeg-path", type=Path, required=False,
        help="The full path to the ffmpeg executable (optional, uses system PATH if not provided)."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose DEBUG logging."
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    settings = load_settings(args.config) if args.config else {}

    input_dir = args.input_dir or settings.get("input_dir")
    output_dir = args.output_dir or settings.get("output_dir")
    ffmpeg_path = args.ffmpeg_path or settings.get("ffmpeg_path")

    # Ensure required values are set (either via CLI or settings file)
    if not input_dir:
        parser.error("Missing required argument: --input-dir (or set input_dir in settings.json)")
    if not output_dir:
        parser.error("Missing required argument: --output-dir (or set output_dir in settings.json)")

    try:
        processor = PodcastProcessor(ffmpeg_path=Path(ffmpeg_path) if ffmpeg_path else None)
        result = processor.process_directory(source_dir=Path(input_dir), output_dir=Path(output_dir))
        print_summary_report(result)
    except FileNotFoundError as e:
        logging.critical(e)
        sys.exit(1)
    except Exception as e:
        logging.critical(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
