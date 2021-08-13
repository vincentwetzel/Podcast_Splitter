import datetime
import logging
import subprocess
import os
import sys
from typing import Dict, List

from mutagen.id3 import ID3
from mutagen.mp3 import MP3
import shutil

# NOTE TO USER: use logging.DEBUG for testing, logging.CRITICAL for runtime
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

main_audio_dir: str = os.path.realpath("E:/Google Drive (vincentwetzel3@gmail.com)/Audio")
mp3split_exe_loc: str = os.path.realpath(
    "C:/Program Files (x86)/mp3splt/mp3splt.exe")  # mp3splt (non-GUI) must be installed to run this.

files_moved_count: int = 0
files_split_dict: Dict[str, str] = dict()
"""{ Album Title : File }"""
files_split_count: int = 0
files_with_unknown_album_list: List[str] = list()
empty_directories_removed_count: int = 0
total_podcasts_size: int = 0


def main():
    # Initialize variables
    files_to_split_dir = os.path.join(main_audio_dir, "Podcasts - to split")
    output_dir = os.path.join(main_audio_dir, "Podcasts")
    global files_moved_count
    global files_split_dict
    global files_with_unknown_album_list
    global empty_directories_removed_count

    # Split the files if they are < 10
    if os.path.isdir(files_to_split_dir):
        os.chdir(files_to_split_dir)
        for file in os.listdir(files_to_split_dir):
            if str(file) == "Thumbs.db" or str(file) == "desktop.ini" or str.split(file, ".")[-1] == "part":
                continue

            # Initialize metadata values
            audio_file = MP3(file)
            id3_tags = ID3(file)  # Calls constructor
            album_title = str(id3_tags.get("TALB")).strip()  # Album Title

            if album_title == "None":
                # These cause errors, we will have to manually fix them before the script can split them.
                files_with_unknown_album_list.append(file)
            elif audio_file.info.length < 601:  # Most 10 minute files are just over 600 seconds.
                continue
            else:
                album_artist = str(id3_tags.get("TPE2")).strip()
                # NOTE: We must enclose file in "" in case of spaces
                current_year = str(datetime.datetime.now().year)
                command = "\"" + mp3split_exe_loc + "\" " + "-t 10.00 -g r%[@o,@g=Podcast,@n=-2,@a=\"" + album_artist + "\",@t=#t_#mm_#ss__#Mm_#Ss]" + ' \"' + str(
                    file) + '\"'
                print("SPLIT COMMAND: " + command)
                run_win_cmd(command)

                # Save info about this file for the final report
                if album_title not in files_split_dict:
                    files_split_dict[album_title] = [file]
                else:
                    files_split_dict[album_title].append(file)

                # Delete original file once it has been split
                os.remove(file)
            global files_split_count
            files_split_count += 1

    # Move the split files to their new destination.
    if os.path.isdir(files_to_split_dir):
        for file in os.listdir(files_to_split_dir):
            extension = os.path.splitext(file)[-1].lower()
            if extension != ".mp3":
                continue
            elif file in files_with_unknown_album_list:
                pass
            else:
                id3_tags = ID3(file)  # Calls constructor
                album_title = str(id3_tags.get("TALB")).strip().replace(':', '-')  # Album Title

                # Strip out special characters from podcast title so we can make an acceptable folder name.
                album_title_folder_name = ''.join(
                    e for e in album_title if (e.isalnum() or e.isspace() or e == ',' or e == '.' or e == '-'))

                # If output directory doesn't exist, create it
                if not os.path.exists(os.path.join(output_dir, str(album_title_folder_name))):
                    os.makedirs(os.path.join(output_dir, str(album_title_folder_name)))

                # Move file to final destination
                shutil.move(os.path.join(files_to_split_dir, file),
                            os.path.join(output_dir, str(album_title_folder_name), file))

                files_moved_count += 1

    # If download directory is now empty, remove it.
    if os.path.isdir(files_to_split_dir) and not os.listdir(files_to_split_dir):
        try:
            os.rmdir(files_to_split_dir)
        except Exception as e:
            print(e)

    # Check output directories, remove any that are empty.
    if os.path.isdir(output_dir):
        for dir in os.listdir(output_dir):
            if os.path.isdir(os.path.join(output_dir, dir)) and not os.listdir(os.path.join(output_dir, dir)):
                try:
                    os.rmdir(os.path.join(output_dir, dir))
                    empty_directories_removed_count += 1
                    print("Empty directory removed: " + str(os.path.join(output_dir, dir)))
                except OSError as e:
                    # OS error is thrown if files are in a directory when os.rmdir is called.
                    print(e)

    # Print a report of the files that were split
    if files_split_dict:
        print_section("PODCASTS SPLIT", "-")
        for album_name in files_split_dict:
            print_section(album_name, "*")
            for val in files_split_dict[album_name]:
                print(val)

    # Print info about the Podcast directories
    print_section("Podcast Directories Info", "-")
    print(get_podcast_directories_filesize_info())

    # Print a final report
    print_section("FINAL REPORT", "*")
    print("Files Split: " + str(files_split_count))
    print("Files Moved: " + str(files_moved_count))
    print("Empty Directories Removed: " + str(empty_directories_removed_count))
    print("Total Size of All Podcasts: " + sizeof_fmt(total_podcasts_size))
    print("\nTotal Errors: " + str(len(files_with_unknown_album_list)))
    if len(files_with_unknown_album_list) > 0:
        print_section("Files with Unknown Album (not split)", "*")
        for file in files_with_unknown_album_list:
            print(file)

    # Done!


def run_win_cmd(cmd):
    """
    Runs a command in a new cmd window. This ONLY works on Windows OS.

    :param cmd: The command to run.
    :return:    None
    """
    print("INPUT COMMAND: " + str(cmd) + "\n")
    result = []
    process = subprocess.Popen(cmd, shell=True)

    # Prevent stdout and stderr from locking up cmd.
    output, error = process.communicate()

    errcode = process.returncode  # 0 if completed
    if errcode != 0:  # NOTE: This was originally None but that is incorrect
        raise Exception('cmd %s failed, see above for details', cmd)


def print_section(section_title, symbol):
    """
    Prints a section title encased in a box of stars.

    :param section_title:   The name of the section title.
    :param symbol:  The symbol to use to create a box around the section_title. Usually this will be the '*' symbol.
    :return:    None
    """
    print("\n" + (symbol * 50) + "\n* " + section_title + "\n" + (symbol * 50) + "\n")


def get_podcast_directories_filesize_info():
    global total_podcasts_size

    output = ""
    main_podcast_dir = os.path.join(main_audio_dir, "Podcasts")

    # Make a list of all the Podcast subdirectories
    podcast_subdirectories = []
    for val in os.listdir(main_podcast_dir):
        val = os.path.join(main_podcast_dir, val)
        if os.path.isdir(val):
            podcast_subdirectories.append(val)

    # Iterate over each Subdirectory, storing its info.
    directory_infos = []
    directory_avg_file_sizes = []
    for podcast_directory in podcast_subdirectories:
        dir_info = ""
        os.chdir(podcast_directory)
        dir_size = 0
        dir_file_count = 0
        for podcast_file in os.listdir(podcast_directory):
            if os.path.splitext(podcast_file)[1] != ".mp3":
                output += "SKIP: " + str(podcast_file) + "\n"
                continue
            dir_size += os.path.getsize(podcast_file)
            dir_file_count += 1

        dir_info += "\nDIRECTORY: " + str(podcast_directory)
        dir_info += "\nFile Count: " + str(dir_file_count)

        avg_filesize = dir_size / dir_file_count
        dir_info += "\nAverage File Size: " + str(sizeof_fmt(avg_filesize))

        dir_info += "\nTotal File Size: " + str(sizeof_fmt(dir_size))
        total_podcasts_size += dir_size

        if not directory_avg_file_sizes:
            directory_avg_file_sizes.append(avg_filesize)
            directory_infos.append(dir_info)
        else:
            is_inserted = False
            for idx, val in enumerate(directory_avg_file_sizes):
                if avg_filesize > val:
                    directory_avg_file_sizes.insert(idx, avg_filesize)
                    directory_infos.insert(idx, dir_info)
                    is_inserted = True
                    break
            if not is_inserted:
                directory_avg_file_sizes.append(avg_filesize)
                directory_infos.append(dir_info)

    # All info is assembled in order, now print it.
    for dir_info in directory_infos:
        output += dir_info + "\n"

    return output


def sizeof_fmt(num, suffix='B'):
    """
    Converts a data sizes to more human-readable values.

    :param num: The number to convert. This defaults to bytes.
    :param suffix:  Default is bytes. If you want to convert another type then enter it as a parameter here (e.g. MB).
    :return:    The converted value
    """
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


if __name__ == "__main__":
    main()
