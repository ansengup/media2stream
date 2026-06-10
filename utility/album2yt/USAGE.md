# album2yt — Usage Guide

Converts ripped CD albums into YouTube-ready MP4 files with embedded chapter
markers, and renames/re-tags the source MP3s for Apple Music or streaming
platforms.

## Prerequisites

- Python 3.10+
- ffmpeg (`brew install ffmpeg`)

---

## Quick start

Place your MP3s, cover image, and YAML config in one folder and run:

```bash
./album2yt.py --config album.yaml
```

That's all that's needed for the default all-in-one layout.

---

## What it produces

For each disc the pipeline writes these files to the output folder:

| File | Description |
|------|-------------|
| `discN_tracks.txt` | ffmpeg concat input list |
| `discN_audio.mp3` | Concatenated audio (temporary — deleted at the start of the next run) |
| `discN_metadata.txt` | ffmpeg metadata with embedded chapter markers |
| `discN_youtube_chapters.txt` | Timestamp list for pasting into a YouTube description |
| `discN_youtube_description.txt` | Full YouTube description including chapter timestamps |
| `<Album> - Disc N <Name>.mp4` | Final YouTube-ready MP4 |
| `youtube_playlist.txt` | Playlist title, description, and ordered video list |
| `youtube_upload_checklist.txt` | Upload checklist with suggested titles and tags |

---

## Folder layouts

### I/O modes

Three ways to organise your working files. All folder paths accept relative
or absolute paths; relative paths are resolved from the current working
directory.

**All-in-one (default)** — MP3s, YAML, cover, and outputs all in one folder.

```
Album Name/
  album.yaml
  cover.jpg
  1-01 Track.mp3
  ...
  disc1_youtube_chapters.txt
  Album - Disc 1.mp4
```
```bash
./album2yt.py --config album.yaml
```

**Separated — 2 folders** — MP3s elsewhere; config, cover, and outputs together.

```
media/
  1-01 Track.mp3
project/
  album.yaml
  cover.jpg
  Album - Disc 1.mp4
```
```bash
./album2yt.py --config project/album.yaml --input media/
```

**Separated — 3 folders** — MP3s, config/cover, and outputs each in their own folder.

```
media/
  1-01 Track.mp3
input/
  album.yaml
  cover.jpg
output/
  Album - Disc 1.mp4
```
```bash
./album2yt.py --config input/album.yaml --input media/ --output output/
```

The output folder is overwritten cleanly on each run.

### Source folder structure detection

Albums may be ripped into four layouts. The utility auto-detects which is in
use, or set `folder_structure:` explicitly in the YAML.

| Layout | Description | Example filenames |
|--------|-------------|-------------------|
| `single_disc` | One folder, one disc, track-number prefix only | `01 - Track Title.mp3` |
| `multi_disc_flat` | One folder, multiple discs, `D-TT` prefix (Apple Music default) | `1-01 Track Title.mp3` |
| `multi_folder` | One subfolder per disc inside the album folder | `Disc 1/01 Track.mp3` |
| `multi_folder_top` | Disc folders are siblings at the top level | `Album - Disc 1/01 Track.mp3` |

Detection order:
1. Sibling folders share a common name prefix with a disc indicator → `multi_folder_top`
2. Subdirectories of the working folder contain audio files → `multi_folder`
3. Filenames match `^\d-\d+` → `multi_disc_flat`
4. Otherwise → `single_disc`

A single-disc album is treated as a multi-disc album with one disc; all
downstream logic is the same regardless of layout.

---

## Album config YAML

Filename convention: `<kebab-case-album-title>.yaml`

```yaml
title: "Album Title"              # required
artist: "Artist Name"             # required
folder_structure: auto            # auto | single_disc | multi_disc_flat | multi_folder | multi_folder_top
input_dir: "/path/to/mp3s"        # optional; overridden by --input CLI flag

discs:
  - number: 1                     # required
    name: "Disc Name"             # required
    duration: "69:10"             # optional MM:SS or HH:MM:SS — used only for sanity-check
    folder: "Album Name - Disc 1" # optional; multi_folder_top only, if auto-detection is wrong
    covers:                       # optional; see Cover images section
      mode: hold
      images:
        - file: "cover.jpg"
        - file: "part2.jpg"
          from_track: 5
    tracks:
      - number: 1                 # required
        title: "Full Title"       # required — used in YouTube chapters and ffmpeg metadata
        short_title: "Short"      # optional — used for MP3 filename and ID3 title tag
        cover: "track1.jpg"       # optional — per-track image override
```

### title vs short_title

- `title` is required and used everywhere by default.
- `short_title` is optional. When present it is used for the MP3 filename and
  the ID3 title tag. `title` is always used for YouTube chapter descriptions
  and ffmpeg chapter metadata.
- Omit `short_title` when the title is already short (e.g. `"Invocation"`).

### Input folder resolution (priority order)

1. `--input` CLI flag
2. `folder:` per disc in YAML (for `multi_folder_top`)
3. `input_dir:` at album level in YAML
4. Same folder as the YAML file (default fallback)

### disc duration field

`duration: "69:10"` is optional and used only to print a warning if the sum
of per-track durations (read from the MP3 files) differs by more than 5 seconds
from the declared total. Useful for catching missing tracks or ripping errors.

---

## Cover images

### Single image (default)

Pass via `--cover` or place `cover.jpg` in the input folder. The same image
holds for the entire disc.

### Per-section hold mode

Images switch at track boundaries and hold until the next switch.

```yaml
discs:
  - number: 1
    covers:
      mode: hold
      images:
        - file: "cover.jpg"       # from track 1
        - file: "part2.jpg"
          from_track: 5           # switches at track 5
        - file: "finale.jpg"
          from_track: 11          # holds to end of disc
```

### Slideshow mode

A list of images cycles at a fixed interval, independent of track boundaries.

```yaml
discs:
  - number: 1
    covers:
      mode: slideshow
      interval: 30                # seconds per image
      images:
        - file: "cover1.jpg"
        - file: "cover2.jpg"
        - file: "cover3.jpg"
```

### Per-track override

Any track can specify its own image:

```yaml
tracks:
  - number: 3
    title: "Meditation on Aum"
    cover: "aum.jpg"
```

### Resolution priority

1. Per-track `cover:` in YAML
2. Disc-level `covers:` section in YAML
3. `--cover` CLI flag
4. `cover.jpg` in input folder

All image paths are relative to the input folder unless absolute. Images of
any dimensions are accepted — odd dimensions are rounded down to even
automatically (`-vf "scale=trunc(iw/2)*2:trunc(ih/2)*2"`), as required by
the H.264 encoder.

---

## Pipeline steps

Steps can be run individually or combined with `--steps`.

| Step | Description |
|------|-------------|
| `rename` | Rename MP3 files and update ID3 title tags |
| `chapters` | Generate concat lists, metadata files, and YouTube chapter/description files |
| `mp4` | Concatenate audio and produce MP4 video(s) |
| `all` | Run all steps in order (default) |

---

## MP3 rename behaviour

Renamed files follow this convention:

| Album type | Default format | With `--no-title-dash` |
|------------|---------------|------------------------|
| Multi-disc | `D-TT-<filename_title>.mp3` | `D-TT <filename_title>.mp3` |
| Single-disc | `TT-<filename_title>.mp3` | `TT <filename_title>.mp3` |

`filename_title` is `short_title` when present, otherwise `title`. `D` = disc
number, `TT` = zero-padded track number.

By default a dash separates the track number from the title. Pass
`--no-title-dash` to use a space instead — this matches the format Apple Music
uses when ripping CDs.

Examples:
```
# Multi-disc, default
1-01-Peace Mantra.mp3

# Multi-disc, --no-title-dash
1-01 Peace Mantra.mp3

# Single-disc, default
01-Invocation.mp3

# Single-disc, --no-title-dash
01 Invocation.mp3
```

The rename step is skipped by default if a file already has the correct target
name. Use `--force-rename` to rename regardless. Use `--dry-run` to preview
what would be renamed without touching any files.

---

## CLI reference

```
./album2yt.py --config <yaml> [options]

Required:
  --config FILE     Album config YAML file

Input/output:
  --input DIR       Folder containing MP3 files
                    (default: same folder as YAML, then input_dir in YAML)
  --output DIR      Folder for generated files
                    (default: same as --input)
  --cover FILE      Cover image for MP4
                    (default: cover.jpg in --input folder)

Pipeline control:
  --steps STEPS     Comma-separated steps: rename,chapters,mp4,all (default: all)
  --discs DISCS     Comma-separated disc numbers to process, e.g. 1,3 (default: all)
  --tracks N        Process only the first N tracks per disc (default: all)
  --force-rename    Rename files even if already correctly named
  --dry-run         Preview rename changes without touching any files (rename step only)
  --no-title-dash   Use a space instead of a dash between track number and title
                    (default: "01-Track Title.mp3"; with flag: "01 Track Title.mp3")
```

### Examples

```bash
# Full pipeline, all discs (all-in-one layout)
./album2yt.py --config breath-of-the-eternal.yaml

# Full pipeline with explicit folders
./album2yt.py --config breath-of-the-eternal.yaml \
  --input ~/Music/Breath\ of\ the\ Eternal \
  --output ~/YouTube/Breath\ of\ the\ Eternal \
  --cover cdCover.jpg

# Rename only, all discs
./album2yt.py --config breath-of-the-eternal.yaml --steps rename

# Preview what would be renamed (no files changed)
./album2yt.py --config breath-of-the-eternal.yaml --steps rename --dry-run

# Force re-rename disc 1 only
./album2yt.py --config breath-of-the-eternal.yaml --steps rename --discs 1 --force-rename

# Generate chapter files only for discs 2 and 3
./album2yt.py --config breath-of-the-eternal.yaml --steps chapters --discs 2,3

# Test run — disc 1, first 5 tracks only
./album2yt.py --config breath-of-the-eternal.yaml --steps chapters,mp4 --discs 1 --tracks 5
```

---

## Podcast mode

Produces one MP4 per source MP3 rather than one per disc. Use this for
lectures, episodes, or any long individual recordings.

Enable with `mode: podcast` in the YAML:

```yaml
title: "Podcast Series Title"
artist: "Speaker Name"
mode: podcast
covers:
  mode: hold | slideshow
  interval: 30              # slideshow only: seconds per image
  images:
    - file: "cover1.jpg"
    - file: "cover2.jpg"
episodes:                   # optional; omit to process all MP3s in sort order
  - file: "ep01.mp3"
    title: "Episode Title"  # optional — overrides output filename
    cover: "ep01_cover.jpg" # optional — per-episode image override
```

### Output filename resolution (highest to lowest)

1. Episode `title:` in YAML
2. `--number-outputs` prefix + source filename (`01 lecture-01-intro.mp4`)
3. Source filename (`lecture-01-intro.mp4`)

### Cover cycling in podcast mode

- `hold` — each file gets the next image in the list (wraps around). One
  static image per file.
- `slideshow` — the same slideshow applies to every file; images cycle at
  the fixed interval within each file.

---

## YouTube upload support

The `chapters` step also generates three files to assist with uploading:

**`discN_youtube_description.txt`** — ready-to-paste YouTube description:
```
<Album Title> — Disc N: <Disc Name>
<Artist>

Chapters:
0:00 Track 1 Title
4:32 Track 2 Title
...

[Playlist: <link — paste after upload>]
```

**`youtube_playlist.txt`** — playlist title and ordered video list.

**`youtube_upload_checklist.txt`** — ordered checklist with suggested title,
description source, and tags for each disc:
```
[ ] Disc 1: <Album> - Disc 1 <Name>.mp4
    Title:       <Album Title> — Disc 1: <Name>
    Description: copy from disc1_youtube_description.txt
    Tags:        <artist>, <album title>, disc 1, <name>
```

Automated upload via the YouTube Data API is planned as a separate
`youtube-upload` utility. The files generated here are designed to be
consumed by that utility.
