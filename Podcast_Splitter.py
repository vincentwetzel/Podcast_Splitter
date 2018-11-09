import subprocess
import os
from mutagen.id3 import ID3
from mutagen.mp3 import MP3

main_audio_dir = "E:\Google Drive\Audio"
mp3split_exe_loc = "C:\Program Files (x86)\mp3splt\mp3splt.exe"  # mp3splt (non-GUI) must be installed to run this.

files_split_count = 0
files_moved_count = 0
files_split_dict = dict()
files_with_unknown_album = list()


def main():
    # Initialize variables
    split_dir = main_audio_dir + "\\Podcasts - to split"
    main_output_dir = main_audio_dir + "\\Podcasts"
    global files_split_count
    global files_moved_count
    global files_split_dict
    global files_with_unknown_album

    os.chdir(split_dir)  # Change current working directory
    # Split the files if they are < 10 min
    for file in os.listdir(os.getcwd()):
        if str(file) == "Thumbs.db":
            continue

        # Initialize metadata values
        audio_file = MP3(file)
        id3_tags = ID3(file)  # Calls constructor
        album_title = str(id3_tags.get("TALB"))  # Album Title

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
    for file in os.listdir(split_dir):
        extension = os.path.splitext(file)[-1].lower()
        if extension != ".mp3":
            continue
        elif file in files_with_unknown_album:
            pass
        else:
            id3_tags = ID3(file)  # Calls constructor
            album_title = id3_tags.get("TALB")  # Album Title

            # If output directory doesn't exist, create it
            if not os.path.exists(os.path.join(main_output_dir, str(album_title))):
                os.makedirs(os.path.join(main_output_dir, str(album_title)))
            os.rename(os.path.join(split_dir, file),
                      os.path.join(main_output_dir, str(album_title), file))  # Move file to final destination

            files_moved_count += 1

    # Print a report of the files that were split
    print("\n")
    for key in files_split_dict:
        print_section(key, "*")
        for val in files_split_dict[key]:
            print(val)

    # Print a final report
    print("\n\nFiles Split: " + str(files_split_count))
    print("Files Moved: " + str(files_moved_count))
    print("Problems: " + str(len(files_with_unknown_album)))
    print_section("Files with Unknown Album (not split)", "*")
    for file in files_with_unknown_album:
        print(file)


def run_win_cmd(cmd):
    print("INPUT COMMAND: " + str(cmd))
    result = []
    process = subprocess.Popen(cmd,
                               shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    output, error = process.communicate()  # Prevents cout and cerr from locking up cmd.
    for line in output:
        result.append(line)  # In case we need to print this
    errcode = process.returncode  # 0 if completed
    if errcode is not 0:  # NOTE: This was originally None but that is incorrect
        raise Exception('cmd %s failed, see above for details', cmd)


def listdir_fullpath(d):
    return [os.path.join(d, f) for f in os.listdir(d)]


def print_section(section_title, symbol):
    print("\n" + (symbol * 50) + "\n* " + section_title + "\n" + (symbol * 50) + "\n")


if __name__ == "__main__":
    main()
