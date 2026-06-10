# publish2yt

Uploads YouTube-ready MP4 files (produced by `album2yt`) to YouTube via the
YouTube Data API v3. Handles authentication, video metadata, thumbnails,
description templating, and playlist management.

Part of the `media2stream` project.

---

## What it does

1. Reads a publish config YAML file
2. Authenticates with YouTube via OAuth 2.0 (browser-based first run, token
   cached for subsequent runs)
3. For each episode MP4:
   - Checks if already uploaded (skips if `youtube_id` already recorded)
   - Uploads the MP4 using YouTube's resumable upload protocol
   - Applies title, description (from template), tags, category, audience setting
   - Sets thumbnail image
   - Records the returned `youtube_id` back into the YAML for idempotency
4. Creates or updates a YouTube playlist, adding each uploaded video in order

---

## Integration with album2yt

`publish2yt` is designed as a downstream consumer of `album2yt` podcast mode
output. The typical working directory layout is:

```
workingdir/<series>/
  <series>.yaml                  ← album2yt config
  <series>-publish.yaml          ← publish2yt config  (this utility's input)
  images/
    cover.jpg
  output/                        ← album2yt output (publish2yt's input)
    01 Episode Title.mp4
    02 Episode Title.mp4
    ...
```

The publish YAML can reference the album2yt config to inherit the episode list
and series metadata, or define episodes independently.

---

## Authentication

YouTube uploads require OAuth 2.0 (API keys do not support uploads).

### Setup (one time)
1. Create a project in Google Cloud Console
2. Enable the YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop application)
4. Download the client secrets JSON file

### Token storage
- Client secrets: `~/.config/publish2yt/client_secrets.json` (default) or
  `--client-secrets FILE`
- Cached OAuth token: `~/.config/publish2yt/token.json` (default) or
  `--token FILE`

First run opens a browser for the OAuth consent flow. Subsequent runs use the
cached token (auto-refreshed when expired).

### Required OAuth scopes
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/youtube`

---

## Publish config YAML schema

Filename convention: `<kebab-case-series-title>-publish.yaml`

```yaml
title: "Vedantasara"              # series title; used in playlist name and templates
artist: "Swami Chetanananda"      # speaker name; used in templates and tags

# Optional: path to the album2yt config to inherit the episode list from.
# If absent, episodes are listed explicitly below or auto-discovered from input_dir.
album_config: "vedantasara.yaml"

input_dir: "output"               # folder containing MP4s; relative to this YAML file.
                                  # Default: "output" subfolder beside the YAML.

youtube:
  privacy: public                 # public | private | unlisted  (default: public)
  audience: not_for_kids          # not_for_kids | for_kids      (default: not_for_kids)
  category: 22                    # YouTube category ID (default: 22 — People & Blogs)
                                  # Common IDs: 22 People & Blogs, 27 Education,
                                  #             29 Nonprofits & Activism
  language: en                    # video language code (default: en)
  tags:                           # tags applied to every video
    - "Vedanta"
    - "Vedantasara"
    - "Swami Chetanananda"
    - "Advaita Vedanta"

  title_template: "{{title}} | {{artist}}"
  # Template for the YouTube video title.
  # Variables: {{title}}, {{artist}}, {{series_title}}, {{episode_number}}
  # Default: "{{title}}" (uses the episode title as-is)

  playlist:
    enabled: true                 # create/update a playlist (default: true)
    title: "{{series_title}} — {{artist}}"  # playlist name template
    description: ""               # playlist description (plain text or template)
    id: null                      # existing playlist ID; if set, skips creation

thumbnail:
  file: "images/VedantaSara.jpeg" # default thumbnail for all episodes; relative to YAML

description:
  template: "templates/description.txt"
  # Path to a plain-text template file. Mutually exclusive with `body`.
  # Relative to the YAML file.

  # OR inline body:
  # body: |
  #   {{title}}
  #
  #   {{artist}} expounds on the Vedantasara...
  #
  #   Part of the series: {{series_title}}
  #   Subscribe: [link]

episodes:
  # Optional explicit list. If absent and album_config is set, the episode list
  # is read from the album2yt YAML. If neither, all MP4s in input_dir are used
  # in filename sort order.
  - file: "01 Vedantasara Texts 1.mp4"
    title: "Vedantasara Texts 1 | Swami Chetanananda"
    youtube_id: null              # written back after successful upload
    thumbnail: null               # optional per-episode image override
    description_extra: null       # optional text appended after the common description

  - file: "02 Vedantasara Texts 2 to 3.mp4"
    title: "Vedantasara Texts 2 to 3 | Swami Chetanananda"
    youtube_id: null
```

### Episode list resolution (priority order)

1. `episodes:` list in publish YAML — explicit, highest priority
2. `album_config:` — reads `episodes:` from the referenced album2yt YAML; derives
   `file:` from the episode `title:` (matching the MP4 filename that album2yt produced)
3. All `*.mp4` files in `input_dir` in filename sort order — auto-discovery fallback

### title_template variables

| Variable | Value |
|---|---|
| `{{title}}` | Episode title from YAML or derived from filename |
| `{{series_title}}` | Top-level `title:` field |
| `{{artist}}` | Top-level `artist:` field |
| `{{episode_number}}` | Zero-padded index (01, 02, …) within the publish run |
| `{{file}}` | Source MP4 filename without extension |

The same variables are available in `description` templates and `playlist.title`.

---

## Description template

Templates are plain-text files with `{{variable}}` placeholders. Variables are
the same set as `title_template` above, plus `{{description_extra}}` (the
per-episode `description_extra:` field if set, else empty string).

### Example template (`templates/description.txt`)

```
{{title}}

Swami Chetanananda's teachings on the Vedantasara, a classical
Advaita Vedanta text by Sadananda Yogendra Saraswati.

Part of the playlist: {{series_title}} — {{artist}}
[Add playlist link after upload]
{{description_extra}}
```

### Inline body

The `description.body:` field accepts the same template syntax. Use either
`template:` (external file) or `body:` (inline), not both.

---

## Thumbnail

All image paths are resolved relative to the YAML file first, then relative
to `input_dir`. Thumbnails must be ≤ 2 MB, JPEG or PNG, and ≤ 1280×720 px
(recommended 1280×720, 16:9 aspect ratio).

Priority order:
1. Per-episode `thumbnail:` in YAML
2. Top-level `thumbnail.file:` in YAML
3. No thumbnail set (YouTube auto-generates one)

Thumbnails are uploaded separately via `thumbnails.set` after the video is
uploaded. This requires the channel to have thumbnail upload permission (usually
granted after phone verification or sufficient channel history).

---

## Pipeline steps

| Step | API calls | Description |
|------|-----------|-------------|
| `upload` | `videos.insert` | Upload MP4s and set title, description, tags, audience |
| `thumbnail` | `thumbnails.set` | Upload and set thumbnail images |
| `playlist` | `playlists.insert`, `playlistItems.insert` | Create playlist and add videos |
| `all` | all of the above | Run all steps in order (default) |

Steps can be combined: `--steps upload,thumbnail`. The `upload` step must
precede `thumbnail` and `playlist` on first run (needs the `youtube_id`).
Subsequent runs can run `thumbnail` or `playlist` alone using the stored IDs.

---

## Idempotency and state tracking

After each successful upload the `youtube_id` is written back into the publish
YAML file under the episode's `youtube_id:` field. Re-running the tool skips
any episode that already has a `youtube_id`, making the process safe to
interrupt and resume.

Similarly, after playlist creation the playlist ID is written back to
`youtube.playlist.id:` in the YAML.

State is stored in-place in the YAML — there is no separate state file.

Force re-upload of an already-uploaded episode with `--force`.

---

## YouTube quota

The YouTube Data API v3 has a default quota of **10,000 units per day**.

| Operation | Cost |
|---|---|
| `videos.insert` (upload) | 1,600 units |
| `thumbnails.set` | 50 units |
| `playlists.insert` | 50 units |
| `playlistItems.insert` | 50 units |

**Per episode cost:** 1,700 units (upload + thumbnail + add to playlist)  
**Max uploads per day (default quota):** ~5 episodes

For 36 episodes, uploads will span approximately **7–8 days**.

The tool prints the estimated quota cost before each run and stops gracefully
when the remaining daily quota would not cover the next upload. Re-run the
next day; already-uploaded episodes are skipped automatically.

To request a quota increase: Google Cloud Console → APIs → YouTube Data API v3
→ Quotas → Request higher quota.

---

## Upload mechanics

YouTube requires **resumable uploads** for video files. The upload protocol:

1. `POST` to `videos.insert` with metadata — YouTube returns a resumable upload URI
2. `PUT` chunks (minimum 256 KB, last chunk may be smaller) to the upload URI
3. On network failure: query the upload URI for bytes received, resume from
   that offset

The tool uses the Google API client library's built-in `MediaFileUpload` with
`resumable=True` and `chunksize` defaulting to 10 MB.

---

## Output

The publish YAML is modified in-place after each successful operation:
- `episodes[n].youtube_id` — set after successful video upload
- `youtube.playlist.id` — set after playlist creation

A human-readable upload log is written to `<series>-upload-log.txt` in the
same folder as the YAML:

```
Upload log — Vedantasara — 2026-06-09

[DONE]  01 Vedantasara Texts 1       → https://youtu.be/XXXXXXXXXXX
[DONE]  02 Vedantasara Texts 2 to 3  → https://youtu.be/YYYYYYYYYYY
[SKIP]  03 ...                       (already uploaded)
```

---

## CLI reference

```
./publish2yt.py --config <yaml> [options]

Required:
  --config FILE         Publish config YAML

Input:
  --input DIR           Folder containing MP4 files (overrides input_dir in YAML)

Pipeline control:
  --steps STEPS         upload,thumbnail,playlist,all (default: all)
  --episodes LIST       Comma-separated episode numbers to process (default: all)
  --dry-run             Print what would be uploaded; make no API calls
  --force               Re-upload even if youtube_id already set

Auth:
  --client-secrets FILE Path to client_secrets.json
                        (default: ~/.config/publish2yt/client_secrets.json)
  --token FILE          Path to OAuth token cache
                        (default: ~/.config/publish2yt/token.json)
  --reauth              Force re-authentication (clear cached token)
```

### Usage examples

```bash
# Full pipeline — upload all episodes, set thumbnails, create playlist
./publish2yt.py --config workingdir/vedantasara/vedantasara-publish.yaml

# Dry run — preview what would be uploaded
./publish2yt.py --config vedantasara-publish.yaml --dry-run

# Upload only (skip thumbnail and playlist steps)
./publish2yt.py --config vedantasara-publish.yaml --steps upload

# Upload specific episodes only
./publish2yt.py --config vedantasara-publish.yaml --episodes 1,2,3

# Set thumbnails for already-uploaded episodes
./publish2yt.py --config vedantasara-publish.yaml --steps thumbnail

# Create/update playlist using already-recorded youtube_ids
./publish2yt.py --config vedantasara-publish.yaml --steps playlist

# Force re-upload of episode 3 even if it has a youtube_id
./publish2yt.py --config vedantasara-publish.yaml --episodes 3 --force

# Re-authenticate (e.g. switching YouTube channels)
./publish2yt.py --config vedantasara-publish.yaml --reauth
```

---

## Key files

| File | Description |
|------|-------------|
| `publish2yt.py` | Main Python script (not yet implemented) |
| `<series>-publish.yaml` | Publish config: episode list, metadata, templates |
| `templates/description.txt` | Optional description template |
| `~/.config/publish2yt/client_secrets.json` | OAuth client secrets (not committed) |
| `~/.config/publish2yt/token.json` | Cached OAuth token (not committed) |
| `<series>-upload-log.txt` | Generated: human-readable upload history |

---

## Dependencies

```
google-api-python-client>=2.100
google-auth-httplib2>=0.1
google-auth-oauthlib>=1.0
PyYAML>=6.0
```

---

## Out of scope

- Editing or deleting existing YouTube videos
- YouTube Analytics / comments
- Batch scheduling (publishing at a future date) — set `privacy: private` first,
  then manually schedule in YouTube Studio
- Non-podcast (album mode) upload — album mode videos are uploaded the same way
  but the playlist structure differs; treat as a future extension
