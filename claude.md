# media2stream

Utilities to digitize audio and video content (digital and analog) 
and publish to YouTube, Spotify, Amazon Music, and other platforms.

## Structure
Each utility lives in `utilities/<name>/` with its own CLAUDE.md.
Shared code and schemas are in `shared/`.

## Conventions
- Python 3, standard library only unless noted in the utility's CLAUDE.md
- ffmpeg for all audio/video processing
- Config files use YAML
- Shell scripts must be POSIX-compatible and pass ShellCheck

## Dependencies
- ffmpeg (`brew install ffmpeg`)
- Python 3.10+