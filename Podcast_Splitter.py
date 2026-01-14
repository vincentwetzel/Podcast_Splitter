import datetime
import logging
import subprocess
import os
import sys
import shutil
import re
from typing import Dict, List, Optional
from pathlib import Path

from mutagen.id3 import ID3
from mutagen.mp3 import MP3

# Configuration
LOG_LEVEL = logging.DEBUG
# Use Path objects for better cross-platform handling
DEFAULT_MAIN_DIR = Path("I:/Google Drive (vincentwetzel3@gmail.com)/Audio")
MP3SPLT_EXE = Path("C:/mp3splt_2.6.2_i386/mp3splt.exe")

logging.basicConfig(stream=sys.stderr, level=LOG_LEVEL, format='%(levelname)s: %(message)s')


def sanitize_folder_name(name: str) -> str:
    """Removes characters that are illegal in Windows filenames."""
    # Replace common illegal characters with a hyphen
    return re.sub(r'[<>:"/\\|?*]', '-', name).strip()


def sizeof_fmt(num: float, suffix: str = 'B') -> str:
    """Converts data sizes to human-readable values."""
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def run_split_cmd(exe: Path, file_path: Path, album_artist: str) -> bool:
    """Executes the mp3splt command safely using subprocess.run."""
    # Construct command as a list to avoid shell injection and quoting issues
    command = [
        str(exe),
        "-t", "10.00",
        "-g", f"r%[@o,@g=Podcast,@n=-2,@a=\"{album_artist}\",@t=#t_#mm_#ss__#Mm_#Ss]",
        str(file_path)
    ]

    logging.debug(f"Running command: {' '.join(command)}")
    try:
        # check=True will raise an exception if the command fails (non-zero exit code)
        subprocess.run(command, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Split failed for {file_path.name}: {e.stderr}")
        return False


def main():
    if not MP3SPLT_EXE.exists():
        logging.critical(f"mp3splt executable not found at {MP3SPLT_EXE}")
        return

    to_split_dir = DEFAULT_MAIN_DIR / "Podcasts - to split"
    output_base_dir = DEFAULT_MAIN_DIR / "Podcasts"

    if not to_split_dir.exists():
        logging.info(f"Directory not found: {to_split_dir}")
        return

    files_split_dict: Dict[str, List[str]] = {}
    unknown_album_files: List[str] = []

    split_count = 0
    moved_count = 0
    total_size = 0.0

    # --- Phase 1: Splitting ---
    for file_path in to_split_dir.glob("*.mp3"):
        try:
            audio = MP3(file_path)
            tags = ID3(file_path)

            album_title = tags.get("TALB")
            album_artist = str(tags.get("TPE2", "Unknown Artist")).strip()

            if not album_title:
                unknown_album_files.append(file_path.name)
                continue

            # Skip if already short (under 10 mins / 600s)
            if audio.info.length < 601:
                continue

            success = run_split_cmd(MP3SPLT_EXE, file_path, album_artist)

            if success:
                album_str = str(album_title)
                files_split_dict.setdefault(album_str, []).append(file_path.name)
                # Only remove original if split was successful
                file_path.unlink()
                split_count += 1

        except Exception as e:
            logging.error(f"Error processing {file_path.name}: {e}")

    # --- Phase 2: Moving & Organizing ---
    # Re-scan the directory for the new chunks created by mp3splt
    for chunk_path in to_split_dir.glob("*.mp3"):
        if chunk_path.name in unknown_album_files:
            continue

        try:
            tags = ID3(chunk_path)
            album_title = str(tags.get("TALB", "Unknown Album"))

            folder_name = sanitize_folder_name(album_title)
            dest_dir = output_base_dir / folder_name
            dest_dir.mkdir(parents=True, exist_ok=True)

            shutil.move(str(chunk_path), str(dest_dir / chunk_path.name))
            moved_count += 1
        except Exception as e:
            logging.error(f"Error moving {chunk_path.name}: {e}")

    # --- Phase 3: Cleanup & Reporting ---
    # Remove empty subdirectories in output
    empty_dirs_removed = 0
    if output_base_dir.exists():
        for sub_dir in output_base_dir.iterdir():
            if sub_dir.is_dir() and not any(sub_dir.iterdir()):
                sub_dir.rmdir()
                empty_dirs_removed += 1

    # Calculate total size of the final library
    for p_file in output_base_dir.rglob("*.mp3"):
        total_size += p_file.stat().st_size

    print_report(split_count, moved_count, empty_dirs_removed, total_size, unknown_album_files, files_split_dict)


def print_report(split, moved, removed, size, unknowns, split_details):
    print("\n" + "=" * 50)
    print("FINAL REPORT")
    print("=" * 50)
    print(f"Files Split:                {split}")
    print(f"Files Moved:                {moved}")
    print(f"Empty Directories Removed:  {removed}")
    print(f"Total Library Size:         {sizeof_fmt(size)}")
    print(f"Errors (Unknown Album):     {len(unknowns)}")

    if unknowns:
        print("\nFILES WITH UNKNOWN ALBUMS:")
        for f in unknowns: print(f" - {f}")

    if split_details:
        print("\nPODCASTS PROCESSED:")
        for album, files in split_details.items():
            print(f"\n[{album}]")
            for f in files: print(f"  > {f}")


if __name__ == "__main__":
    main()