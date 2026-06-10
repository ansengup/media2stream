# album-to-youtube

Converts ripped CD albums into YouTube-ready MP4s with embedded chapter markers,
plus renamed and tagged MP3 files ready for Apple Music / streaming platforms.

Part of the `media2stream` project.

---

## What it does

1. Reads an album config YAML file
2. Detects or uses the specified folder structure of the ripped MP3s
3. Renames MP3 files and updates ID3 title tags (only if needed, or forced)
4. Generates per-disc ffmpeg concat lists, chapter metadata files, and YouTube
   chapter description text files
5. Produces one MP4 per disc (static cover image + concatenated audio, with
   embedded chapter markers)

---

## Folder structure detection

Albums may be ripped into one of four layouts. The utility auto-detects which
is in use, or the layout can be set explicitly via `folder_structure` in the
YAML config.

### Case 1: single_disc
One folder, one disc, files named by track number only.
```
Album Name/
  01 - Track Title.mp3
  02 - Track Title.mp3
```

### Case 2: multi_disc_flat  ← what Apple Music produces
One folder, multiple discs, files prefixed with `D-TT` (disc-track).
```
Album Name/
  1-01 Track 01.mp3
  1-02 Track 02.mp3
  2-01 Track 01.mp3
```

### Case 3: multi_folder
One subfolder per disc inside the album folder, each containing track files.
```
Album Name/
  Disc 1/
    01 Track.mp3
  Disc 2/
    01 Track.mp3
```

### Case 4: multi_folder_top  ← disc folders sit alongside each other at top level
Disc folders are siblings at the top level, named with the album title and disc
number. The YAML file lives in the parent folder or in any of the disc folders.
```
Album Name - Disc 1/
  01 Track.mp3
Album Name - Disc 2/
  01 Track.mp3
```
The disc folders are matched by looking for sibling directories whose names
share a common prefix and contain a disc indicator (`Disc N`, `- N`, etc.).
The YAML `folder` field on each disc can override the folder name explicitly:
```yaml
discs:
  - number: 1
    folder: "Album Name - Disc 1"   # optional; auto-detected if absent
    name: "Awakening"
```

Detection logic (in order):
1. If the working folder contains no audio files but sibling folders share a
   common name prefix with a disc indicator → `multi_folder_top`
2. Else if subdirectories of the working folder contain audio files → `multi_folder`
3. Else if filenames match `^\d-\d+` pattern → `multi_disc_flat`
4. Else → `single_disc`

A single-disc album is treated as a multi-disc album with one disc (N=1).
All downstream logic works on the same internal model regardless of layout.

---

## Folder layout modes

The rule is: **`--output` defaults to the folder containing the YAML**, and
**`--input` defaults to the same**. This means the all-in-one mode requires
no flags at all; only specify what differs from the default.

All folder paths (CLI flags and `input_dir:` in YAML) accept either absolute
or relative paths. Relative paths are resolved from the current working
directory at the time the script is invoked.

The output folder is always overwritten cleanly on each run.

### Mode 1: All-in-one (default)
Everything in one folder — MP3s, YAML, cover, and all outputs sit together.
No flags needed.

```
Album Name/
  album.yaml
  cover.jpg
  1-01 Track.mp3
  ...
  disc1_youtube_chapters.txt
  disc1_audio.mp3     ← temporary, deleted at start of each run
  Album - Disc 1.mp4
```

```bash
./album2yt.py --config album.yaml
```

### Mode 2: Separated — 3 folders
MP3s in their own media folder, config/cover in input, outputs elsewhere.

```
media/
  1-01 Track.mp3
  ...
input/
  album.yaml
  cover.jpg
output/
  disc1_youtube_chapters.txt
  Album - Disc 1.mp4
```

```bash
./album2yt.py --config input/album.yaml --input media/ --output output/
```

### Mode 3: Separated — 2 folders
MP3s in media folder, everything else (config, cover, outputs) combined.

```
media/
  1-01 Track.mp3
  ...
project/
  album.yaml
  cover.jpg
  disc1_youtube_chapters.txt
  Album - Disc 1.mp4
```

```bash
./album2yt.py --config project/album.yaml --input media/ --output project/
```

---

## Album config YAML schema

Each album has one YAML file. Filename convention: `<kebab-case-album-title>.yaml`

```yaml
title: "Album Title"                          # required
artist: "Artist Name"                         # required
folder_structure: auto                        # auto | single_disc | multi_disc_flat | multi_folder | multi_folder_top
input_dir: "/path/to/mp3s"                    # optional; overridden by --input CLI flag
                                              # default: same folder as YAML file
discs:
  - number: 1                                 # required, integer
    name: "Disc Name"                         # required, e.g. "Awakening"
    duration: "69:10"                         # optional, MM:SS or HH:MM:SS
    folder: "Album Name - Disc 1"             # optional; only needed for multi_folder_top
                                              # if auto-detection gets the folder name wrong
    covers:                                   # optional; see Cover images section below
      mode: hold                              # hold | slideshow
      images:
        - file: "cover.jpg"                   # default for whole disc
        - file: "chapter2.jpg"
          from_track: 5                       # switches image at track 5
    tracks:
      - number: 1                             # required, integer
        title: "Full Title - Source Ref"      # required; used for YouTube descriptions
                                              # and as filename if short_title absent
        short_title: "Short Title"            # optional; used for filenames when present
        cover: "track1.jpg"                   # optional; per-track image override
```

### Input folder resolution (priority order)

1. `--input` CLI flag — highest priority, explicit override
2. `folder:` per disc in YAML — used for `multi_folder_top` layout
3. `input_dir:` at album level in YAML — optional absolute path
4. Same folder as the YAML file — default fallback

### title vs short_title

- `title` is the default used everywhere. It is required.
- `short_title` is optional. When present, it is used for:
  - MP3 filename
  - ID3 title tag
- `title` is always used for:
  - YouTube chapter descriptions
  - ffmpeg metadata chapter titles

Resolution logic:
```python
filename_title = track.get("short_title") or track["title"]
youtube_title  = track["title"]
```

Omit `short_title` when the title is already short (e.g. "Invocation").

### Example — album with source references in title

```yaml
title: "Breath of the Eternal"
artist: "Swami Chetanananda"
folder_structure: auto
discs:
  - number: 1
    name: "Awakening"
    duration: "69:10"
    tracks:
      - number: 1
        title: "Peace Mantra - Taittiriya Upanishad 1.1.1"
        short_title: "Peace Mantra"
      - number: 2
        title: "Prayer for Memory and Health - Taittiriya Upanishad 1.4.1"
        short_title: "Prayer for Memory and Health"
```

### Example — album with Sanskrit + English titles

```yaml
title: "Echoes of the Eternal"
artist: "Swami Chetanananda"
folder_structure: auto
discs:
  - number: 1
    name: "Peace"
    duration: "60:42"
    tracks:
      - number: 1
        title: "Madhu vata ritayate - May the winds blow sweetly"
        short_title: "Madhu vata ritayate"
      - number: 2
        title: "Tejo asi tejo mayi dhehi - O Lord, fill me with energy and strength"
        short_title: "Tejo asi tejo mayi dhehi"
```

---

## Cover images

Three ways to specify cover images, from simplest to most complex.

### Single image (default)
Pass via `--cover` CLI flag or place `cover.jpg` in the input folder.
The same image holds for the entire disc.

### Per-section images (hold mode)
Images switch at specified track boundaries and hold until the next switch.
Defined in the YAML under each disc's `covers:` key.

```yaml
discs:
  - number: 1
    covers:
      mode: hold              # image holds for full duration of each section
      images:
        - file: "cover.jpg"   # used from track 1 until next entry
        - file: "part2.jpg"
          from_track: 5       # switches at track 5, holds until track 11
        - file: "finale.jpg"
          from_track: 11      # holds to end of disc
```

### Slideshow mode
A list of images cycles at a fixed time interval, independent of track boundaries.

```yaml
discs:
  - number: 1
    covers:
      mode: slideshow
      interval: 30            # seconds per image
      images:
        - file: "cover1.jpg"
        - file: "cover2.jpg"
        - file: "cover3.jpg"
```

### Per-track image override
Any track can specify its own image, overriding the disc-level cover setting.

```yaml
tracks:
  - number: 3
    title: "Meditation on Aum"
    cover: "aum.jpg"          # overrides disc-level cover for this track only
```

### Cover image resolution
Priority order:
1. Per-track `cover:` in YAML
2. Disc-level `covers:` section in YAML
3. `--cover` CLI flag
4. `cover.jpg` in input folder (default fallback)

All image paths are relative to the input folder unless absolute.
Cover images of any dimensions are accepted — ffmpeg always applies
`-vf "scale=trunc(iw/2)*2:trunc(ih/2)*2"` to round odd dimensions down to
the nearest even number, which is required by the H.264 encoder.

---

## MP3 filename convention

Filename format depends on album type:

**Multi-disc albums** (`multi_disc_flat`, `multi_folder`, `multi_folder_top`):
```
D-TT-<filename_title>.mp3
```

**Single-disc albums** (`single_disc`):
```
TT-<filename_title>.mp3
```

Where `D` = disc number, `TT` = zero-padded track number, and `filename_title`
is `short_title` if present, otherwise `title`.

The dash between the track number and title is included by default. Pass
`--no-title-dash` to use a space instead (matches the Apple Music rip format).

Examples:
```
# Multi-disc (default)
1-01-Peace Mantra.mp3
1-02-Prayer for Memory and Health.mp3

# Multi-disc (--no-title-dash)
1-01 Peace Mantra.mp3
1-02 Prayer for Memory and Health.mp3

# Single-disc (default)
01-Invocation.mp3
02-Immortality of the Soul.mp3

# Single-disc (--no-title-dash)
01 Invocation.mp3
02 Immortality of the Soul.mp3
```

### Rename behaviour

The rename step is **skipped by default if the file already has the correct
target name**. Use `--force-rename` to override. Use `--dry-run` to preview
what would be renamed without making any changes.

Rename skip logic:
```python
if target_path.exists() and not force_rename:
    print(f"Skipping (already named correctly): {target_path.name}")
    continue
```

---

## Pipeline steps

The utility runs one or more steps in order. Steps can be run individually or
in any combination via `--steps`.

| Step | Description |
|------|-------------|
| `rename` | Rename MP3 files and update ID3 title tags |
| `chapters` | Generate ffmpeg concat lists, metadata files, YouTube chapter files |
| `mp4` | Concatenate audio and produce MP4 video(s) |
| `all` | Run all steps in order (default) |

---

## Output files

For each disc N the utility produces:

| File | Description |
|------|-------------|
| `discN_tracks.txt` | ffmpeg concat input list |
| `discN_audio.mp3` | concatenated audio (temporary, deleted at start of next run) |
| `discN_metadata.txt` | ffmpeg metadata with embedded chapter markers |
| `discN_youtube_chapters.txt` | timestamp list for pasting into YouTube description |
| `<Album> - Disc N <Name>.mp4` | final YouTube-ready MP4 |

Output files are written to `--output` folder (default: same as `--input`).

---

## Track duration introspection

Per-track durations are required to compute YouTube chapter timestamps. The
utility reads durations directly from the MP3 files — the YAML `duration:`
field on a disc is an optional total used only for sanity-checking, not for
per-track timing.

### Duration resolution (in order)

1. **ID3 TLEN tag** (v2.3/v2.4) or **TLE tag** (v2.2) — milliseconds stored
   in the file header. Fastest path; present in most properly-tagged files.
2. **MPEG frame header scan** — reads the first sync frame after the ID3 tag
   to extract bitrate and sample rate, then estimates duration from file size.
   Reliable for CBR files (all CD rips are CBR).

```python
def get_track_duration_seconds(path):
    # 1. Try TLEN/TLE from ID3 tag
    # 2. Fall back to MPEG frame header scan
    # Returns integer seconds
```

Duration is read **after** the rename step so it always operates on the
correctly-named files. If duration cannot be determined, the utility raises
an error for that track rather than silently producing wrong timestamps.

### YAML disc duration field

The optional `duration: "69:10"` field on a disc is used only to print a
warning if the sum of introspected track durations differs significantly
(>5 seconds) from the declared total. Useful for catching missing tracks or
ripping errors.

---

## ID3 tag notes

- Ripped files from Apple Music use **ID3v2.2** format (3-byte frame IDs: `TT2` not `TIT2`)
- The rename/tag script handles v2.2, v2.3, and v2.4
- Title tag encoding: Latin-1 (byte 0x00) for v2.2, UTF-8 (byte 0x03) for v2.3/v2.4
- Duration tag: `TLE` (v2.2) or `TLEN` (v2.3/v2.4), value in milliseconds as a string

---

## ffmpeg requirements

- `ffmpeg` must be installed (`brew install ffmpeg`)
- Cover images of any dimensions are handled — odd dimensions are rounded down to even automatically
- Audio is re-encoded to AAC 192k for YouTube compatibility
- Output uses `libx264 -tune stillimage` for efficient static-image video
- Multiple cover images use ffmpeg's `concat` demuxer for image sequencing

---

## CLI reference

```
./album2yt.py --config <yaml> [options]

Required:
  --config FILE         Album config YAML file

Input/output:
  --input DIR           Folder containing MP3 files
                        (default: same folder as YAML, then input_dir in YAML)
  --output DIR          Folder for generated MP4s and chapter files
                        (default: same as --input; working/ subfolder used for intermediates)
  --cover FILE          Cover image for MP4
                        (default: cover.jpg in --input folder)

Pipeline control:
  --steps STEPS         Comma-separated steps to run: rename,chapters,mp4,all (default: all)
  --discs DISCS         Comma-separated disc numbers to process, e.g. 1,3 (default: all)
  --tracks N            Process only first N tracks per disc (default: all)
  --force-rename        Rename files even if already correctly named (default: skip if correct)
  --dry-run             Preview rename changes without touching any files (rename step only)
  --no-title-dash       Use a space instead of a dash between track number and title
                        (default: dash, e.g. "01-Track Title.mp3" → space gives "01 Track Title.mp3")
```

### Usage examples

```bash
# Full pipeline, all discs
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

# Build MP4 for disc 1, first 5 tracks only (useful for testing)
./album2yt.py --config breath-of-the-eternal.yaml --steps chapters,mp4 --discs 1 --tracks 5
```

---

## Podcast mode

Podcast mode produces one MP4 per source MP3 file rather than one MP4 per disc.
Use it when the input folder contains long individual recordings (lectures,
episodes) that each need their own YouTube upload.

Enable by setting `mode: podcast` in the YAML:

```yaml
title: "My Podcast Series"
artist: "Speaker Name"
mode: podcast          # album (default) | podcast
covers:
  mode: hold           # cycles images across files (one image per file, then repeats)
  images:
    - file: "cover1.jpg"
    - file: "cover2.jpg"
    - file: "cover3.jpg"
```

### Output naming

By default, output MP4 filenames are derived from the source MP3 filename
(preserving whatever name is on disk):

```
source:  lecture-01-intro.mp3
output:  lecture-01-intro.mp4
```

Add `--number-outputs` to prefix each file with a sequence number:

```
output:  01 lecture-01-intro.mp4
```

A YAML `title` override on an episode sets the output filename explicitly:

```yaml
episodes:
  - file: "lecture-01-intro.mp3"
    title: "Introduction to Vedanta"
    # output: Introduction to Vedanta.mp4
```

Resolution order (highest to lowest):
1. Episode `title:` in YAML
2. `--number-outputs` prefix + source filename
3. Source filename (default)

### Cover cycling in podcast mode

`hold` mode cycles images **across files** — file 1 gets image 1, file 2 gets
image 2, etc., wrapping around when the list is exhausted. Each file uses one
static image for its full duration.

`slideshow` mode cycles images **within each file** at a fixed interval
(same as album mode). The same slideshow applies to every file.

Per-episode `cover:` overrides both disc-level modes for that episode.

### Podcast YAML schema

```yaml
title: "Podcast Series Title"
artist: "Speaker Name"
mode: podcast
covers:
  mode: hold | slideshow
  interval: 30           # slideshow only: seconds per image
  images:
    - file: "cover1.jpg"
    - file: "cover2.jpg"
episodes:                # optional; omit to process all MP3s in input folder
  - file: "ep01.mp3"
    title: "Episode Title"      # optional; overrides output filename
    cover: "ep01_cover.jpg"     # optional; per-episode image override
```

If `episodes:` is omitted, all MP3 files in the input folder are processed
in filename sort order.

---

## YouTube playlist support

For album uploads, the utility generates files to assist with YouTube playlist
creation. These are produced as part of the `chapters` step.

### Output files

| File | Description |
|------|-------------|
| `youtube_playlist.txt` | Playlist title, description, and ordered video list |
| `discN_youtube_description.txt` | Full description for each disc's YouTube upload, including chapter timestamps |
| `youtube_upload_checklist.txt` | Ordered checklist of uploads with suggested titles and tags |

### Playlist description file (`youtube_playlist.txt`)

```
Playlist: <Album Title> — <Artist>

<Album Title> is a <N>-disc recording of...
[paste your own description here]

Videos in this playlist:
1. <Album> - Disc 1 <Name>
2. <Album> - Disc 2 <Name>
3. <Album> - Disc 3 <Name>
```

### Per-disc description file (`discN_youtube_description.txt`)

```
<Album Title> — Disc N: <Disc Name>
<Artist>

Chapters:
0:00 Track 1 Title
4:32 Track 2 Title
...

[Playlist: <link — paste after upload>]
```

### Upload checklist (`youtube_upload_checklist.txt`)

```
Upload checklist — <Album Title>

[ ] Disc 1: <Album> - Disc 1 <Name>.mp4
    Title:       <Album Title> — Disc 1: <Name>
    Description: copy from disc1_youtube_description.txt
    Tags:        <artist>, <album title>, disc 1, <name>

[ ] Disc 2: ...
```

### Future: automated upload

Automated upload via the YouTube Data API (OAuth, resumable upload, metadata
setting) is planned as a separate `youtube-upload` utility in the `media2stream`
project. The description and checklist files generated here are designed to be
consumed by that utility.

---

## Key files

| File | Description |
|------|-------------|
| `album2yt.py` | Main Python script |
| `make_mp4s.sh` | Legacy bash script (superseded by album2yt.py) |
| `<album>.yaml` | Album config: track list, disc names, folder structure |
| `discN_tracks.txt` | Generated: ffmpeg concat list |
| `discN_metadata.txt` | Generated: ffmpeg chapter metadata |
| `discN_youtube_chapters.txt` | Generated: YouTube description chapters |

---

## Test albums

Two albums are available as test cases in the working folder:

- `breath-of-the-eternal.yaml` — 3 discs, 27 tracks, English titles with source refs
- `echoes-of-the-eternal.yaml` — 3 discs, 102 tracks, Sanskrit + English titles

Both use `folder_structure: auto` and `multi_disc_flat` layout (Apple Music rips).
