import subprocess
import os
from mutagen.id3 import ID3
import mutagen

main_audio_dir = "E:\Google Drive\Audio"
mp3split_exe_loc = "C:\Program Files (x86)\mp3splt\mp3splt.exe"  # This script requires mp3splt (non-GUI) to be installed


def main():
    # Initialize variables
    split_dir = main_audio_dir + "\\Podcasts - to split"
    output_dir = main_audio_dir + "\\Podcasts"
    files_to_split = list()

    os.chdir(split_dir)  # Change current working directory
    for file in os.listdir(split_dir):
        if str(file) == "Thumbs.db":
            continue
        files_to_split.append(os.path.join(os.getcwd(), file))

    # Split the files
    for file in files_to_split:
        print("Processing: " + str(file))
        command = mp3split_exe_loc + ' -t 10.00 ' + '\"' + str(file) + '\"'  # Must enclose file in "" in case of spaces
        run_win_cmd(command)
        os.remove(file)  # Delete original file once it has been splitted

    # Move the splitted files to their new destination.
    for file in os.listdir(split_dir):
        if file == "Thumbs.db":
            continue
        id3_tags = ID3(file)  # Calls constructor
        album_title = id3_tags.get("TALB")  # Album Title
        os.rename(os.path.join(split_dir, file),
                  os.path.join(output_dir, str(album_title), file))  # Move file to final destination


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


if __name__ == "__main__":
    main()
