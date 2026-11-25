# Podcast Splitter

Splits podcast audio into 10-minute segments, converts processed audio to OPUS, and organizes the results into album-named folders.

## Features

- **Audio and video inputs**: Supports `.mp3`, `.opus`, `.m4a`, `.m4b`, `.m4p`, `.aac`, `.ogg`, `.oga`, `.flac`, `.wav`, `.wma`, `.aiff`, `.aif`, `.mp4`, `.m4v`, `.mkv`, `.mov`, `.avi`, `.webm`, `.wmv`, `.flv`, `.mpeg`, `.mpg`, `.mpe`, `.mpv`, `.3gp`, `.3g2`, `.mts`, `.m2ts`, `.ts`, and `.vob`.
- **OPUS output**: Short files are converted to `.opus`; long files are split into `.opus` chunks encoded with FFmpeg's `libopus` encoder at 128 kbps. Conversion is lossy.
- **Audio stream selection**: Video inputs contribute their first audio stream; video and subtitle streams are not included in the output.
- **Metadata and naming**: Reads available album/title and artist metadata. When a usable title is missing, it derives one from the filename and removes trailing bracketed details. Windows short-name aliases such as `THEEVE~1` are ignored.
- **Organization**: Moves processed OPUS files into album-named folders.
- **Recycle bin**: Sends original files to the recycle bin after successful processing and organization.
- **Timestamp naming**: Split files include start/end timestamps, for example `podcast_00m_00s__10m_00s.opus`.

## Requirements

- FFmpeg must be installed and available through `PATH` or supplied with `--ffmpeg-path`.
- FFmpeg must include the `libopus` encoder.
- FFprobe should be available through `PATH` or in the same directory as FFmpeg. It is used to read duration and metadata from video containers.
- Python dependencies: `mutagen` and `send2trash`.

## Configuration

`settings.json` supports these keys:

- `input_dir`: Source directory containing audio or video files.
- `output_dir`: Destination directory for organized OPUS files.
- `ffmpeg_path` (optional): Path to the FFmpeg executable. Uses `PATH` when omitted.

## Usage

```bash
# Run with settings.json defaults
python Podcast_Splitter.py

# Override settings via CLI
python Podcast_Splitter.py --input-dir "/path/to/podcasts" --output-dir "/path/to/output"

# Specify ffmpeg path explicitly
python Podcast_Splitter.py --ffmpeg-path "/path/to/ffmpeg"

# Custom config file
python Podcast_Splitter.py --config /path/to/settings.json

# Verbose/debug logging
python Podcast_Splitter.py -v
```

