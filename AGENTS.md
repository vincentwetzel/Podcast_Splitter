# Agents

This file documents the agents that are part of this project.

## PodcastSplitter Agent

The PodcastSplitter agent is responsible for splitting podcast audio files into multiple smaller files and organizing them by album/title metadata.

### Features

- **Multi-format support**: Supports `.mp3`, `.opus`, `.m4a`, `.aac`, `.ogg`, `.flac`, `.wav`
- **FFmpeg-based splitting**: Uses ffmpeg for fast, lossless audio splitting (stream copy, no re-encoding)
- **Smart metadata extraction**: Handles ID3 tags (MP3), Vorbis comments (Opus/OGG), and MP4 tags (M4A/AAC)
- **Automatic organization**: Moves processed files into album-named folders
- **Recycle bin**: Sends original files to recycle bin after successful processing
- **Timestamp naming**: Output files include start/end timestamps (e.g., `podcast_00m_00s__10m_00s.opus`)

### Configuration

Uses `settings.json` with keys:
- `input_dir`: Source directory with podcast files to split
- `output_dir`: Destination directory for organized podcasts
- `ffmpeg_path` (optional): Path to ffmpeg executable (uses system PATH if not provided)

### Usage

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

