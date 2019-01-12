import subprocess
import os
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
import mutagen

main_audio_dir = os.path.realpath("E:/Google Drive (vincentwetzel3@gmail.com)/Audio")
mp3split_exe_loc = os.path.realpath(
    "C:/Program Files (x86)/mp3splt/mp3splt.exe")  # mp3splt (non-GUI) must be installed to run this.

files_split_count = 0
files_moved_count = 0
files_split_dict = dict()
files_with_unknown_album = list()
empty_directories_removed = 0


def main():
    # Initialize variables
    files_to_split_dir = os.path.join(main_audio_dir, "Podcasts - to split")
    output_dir = os.path.join(main_audio_dir, "Podcasts")
    global files_split_count
    global files_moved_count
    global files_split_dict
    global files_with_unknown_album
    global empty_directories_removed

    os.chdir(files_to_split_dir)  # Change current working directory
    # Split the files if they are < 10 min
    for file in os.listdir(os.getcwd()):
        if str(file) == "Thumbs.db":
            continue

        # Initialize metadata values
        audio_file = MP3(file)
        id3_tags = ID3(file)  # Calls constructor
        album_title = str(id3_tags.get("TALB")).strip()  # Album Title

        # TODO: Add in a way to check the genre and pass on the file if the genre is missing or not "Podcast"

        if album_title == "None":
            files_with_unknown_album.append(file)
        elif audio_file.info.length < 601:  # Most 10 minute files are just over 600 seconds.
            continue
        else:
            command = "\"" + mp3split_exe_loc + "\"" + ' -t 10.00 ' + '\"' + str(
                file) + '\"'  # Must enclose file in "" in case of spaces
            run_win_cmd(command)

            # Save info about this file for the final report
            if album_title not in files_split_dict:
                files_split_dict[album_title] = [str(file)]
            else:
                files_split_dict[album_title].append(str(file))

            os.remove(file)  # Delete original file once it has been splitted
            files_split_count += 1

    # Move the splitted files to their new destination.
    for file in os.listdir(files_to_split_dir):
        extension = os.path.splitext(file)[-1].lower()
        if extension != ".mp3":
            continue
        elif file in files_with_unknown_album:
            pass
        else:
            id3_tags = ID3(file)  # Calls constructor
            album_title = id3_tags.get("TALB")  # Album Title

            # If output directory doesn't exist, create it
            if not os.path.exists(os.path.join(output_dir, str(album_title))):
                os.makedirs(os.path.join(output_dir, str(album_title)))
            os.rename(os.path.join(files_to_split_dir, file),
                      os.path.join(output_dir, str(album_title), file))  # Move file to final destination

            files_moved_count += 1

    # Check output directories, remove any that are empty.
    for dir in os.listdir(output_dir):
        if os.path.isdir(os.path.join(output_dir, dir)) and not os.listdir(os.path.join(output_dir, dir)):
            try:
                os.rmdir(os.path.join(output_dir, dir))
                empty_directories_removed += 1
                print("Empty directory removed: " + str(os.path.join(output_dir, dir)))
            except OSError as e:
                print(e)

    # Print a report of the files that were split
    print_section("PODCASTS SPLIT", "-")
    for key in files_split_dict:
        print_section(key, "*")
        for val in files_split_dict[key]:
            print(val)

    # Print a final report
    print_section("FINAL REPORT", "-")
    print("Files Split: " + str(files_split_count))
    print("Files Moved: " + str(files_moved_count))
    print("Empty Directories Removed: " + str(empty_directories_removed))
    print("\nTotal Errors: " + str(len(files_with_unknown_album)))
    if len(files_with_unknown_album) > 0:
        print_section("Files with Unknown Album (not split)", "*")
        for file in files_with_unknown_album:
            print(file)


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


if __name__ == "__main__":
    main()
