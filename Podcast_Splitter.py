import subprocess
import os
from mutagen.id3 import ID3
import mutagen

main_audio_dir = "E:\Google Drive\Audio"
mp3split_exe_loc = "C:\Program Files (x86)\mp3splt\mp3splt.exe"


def main():
    '''
    os.chdir(unsplit_podcast_dir)
    proc = subprocess.Popen('cmd.exe', )  # TODO: Fix this
    stdout, stderr = proc.communicate()
    print("stdout: " + stdout)
    print("done")
    '''

    # run_win_cmd("dir E:\\")

    split_dir = main_audio_dir + "\\Podcasts - to split"
    output_dir = main_audio_dir + "\\Podcasts"
    os.chdir(split_dir)
    files_to_split = list()
    for file in os.listdir(split_dir):
        if str(file) == "Thumbs.db":
            continue
        files_to_split.append(os.path.join(os.getcwd(), file))

    # Split the files
    for file in files_to_split:
        print("Processing: " + str(file))
        command = '"C:\Program Files (x86)\mp3splt\mp3splt.exe" -t 10.00 ' + '\"' + str(file) + '\"'
        run_win_cmd(command)
        os.remove(file)

    # Move the splitted files to their new destination.
    for file in os.listdir(split_dir):
        if file == "Thumbs.db":
            continue
        id3_tags = ID3(file)
        album_title = id3_tags.get("TALB")
        os.rename(os.path.join(split_dir, file), os.path.join(output_dir, str(album_title), file))


def run_win_cmd(cmd):
    print("INPUT COMMAND: " + str(cmd))
    result = []
    process = subprocess.Popen(cmd,
                               shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    output, error = process.communicate()
    for line in output:
        result.append(line)
    # print(result)  # Prints a bunch of numbers
    errcode = process.returncode
    if errcode is not 0:
        raise Exception('cmd %s failed, see above for details', cmd)


def listdir_fullpath(d):
    return [os.path.join(d, f) for f in os.listdir(d)]


if __name__ == "__main__":
    main()
