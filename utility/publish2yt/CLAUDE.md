# publish2yt

Manages YouTube publication of MP4 files produced by `album2yt`. Handles
OAuth authentication, video metadata, thumbnails, description templating, and
playlist management via the YouTube Data API v3.

Supports two workflows depending on how videos are uploaded:

- **Automated upload** — the script uploads MP4 files directly via the API
  (`videos.insert`, 1,600 units/video). Full automation but quota-limited to
  ~5–6 videos per day on the default 10,000-unit allowance.

- **Manual upload + API metadata** *(recommended for large series)* — MP4 files
  are uploaded through YouTube Studio by hand; the script then applies metadata
  (title, description, tags, audience, privacy), thumbnails, and playlist
  membership via `videos.update` (50 units/video). All 36 Vedantasara episodes
  fit in a single day's quota.

Part of the `media2stream` project.

---

## What it does

1. Reads a publish config YAML file
2. Authenticates with YouTube via OAuth 2.0 (browser-based first run, token
   cached for subsequent runs)
3. Optionally runs `sync-ids`: lists the channel's recent uploads (including
   private) via the uploads playlist and writes matched video IDs into the YAML
4. For each episode:
   - If no `youtube_id` is set → **upload step**: uploads the MP4 and sets
     metadata in one `videos.insert` call
   - If `youtube_id` is already set (manual upload workflow) → **metadata step**:
     applies metadata via `videos.update`
   - Uploads the thumbnail via `thumbnails.set`
   - Records the `youtube_id` back into the YAML for idempotency
5. Creates or updates a YouTube playlist, adding each uploaded video in order

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

| Step | API call | Units | Description |
|------|----------|-------|-------------|
| `sync-ids` | `channels.list` + `playlistItems.list` | ~2 total | List the channel's uploads (including private) and match each to an episode by title. Writes `youtube_id` into YAML. Run after manual upload in YouTube Studio. |
| `upload` | `videos.insert` | 1,600/video | Upload MP4 and set all metadata in one call. Skips episodes that already have a `youtube_id`. |
| `metadata` | `videos.update` | 50/video | Apply title, description, tags, audience, privacy to existing videos. Requires `youtube_id`. Used in the manual upload workflow. |
| `thumbnail` | `thumbnails.set` | 50/video | Upload and attach thumbnail image. Requires `youtube_id`. |
| `playlist` | `playlists.insert` + `playlistItems.insert` | 50/video | Create playlist and add videos in order. Requires `youtube_id` on each episode. |
| `all` | smart | — | Default. For each episode: runs `upload` if no `youtube_id` is set, otherwise runs `metadata`. Then runs `thumbnail` and `playlist` for all. |

`all` is intentionally smart: episodes without a `youtube_id` are uploaded
automatically; episodes with a `youtube_id` already set (from manual YouTube
Studio upload) have their metadata updated instead. This means you can mix
the two workflows within a single YAML file and a single run.

`thumbnail` and `playlist` always require `youtube_id` to be set (either by
a prior `upload` run or manually). They can be run in isolation after the
fact without re-uploading.

---

## Syncing video IDs from manually uploaded videos

When using the manual upload workflow you don't need to copy-paste video IDs
by hand. The `sync-ids` step queries the authenticated channel's uploads
playlist and matches videos to episodes by title.

### How it works

1. Call `channels.list(part='contentDetails', mine=True)` → retrieves the
   channel's uploads playlist ID (1 unit, one-time)
2. Call `playlistItems.list(playlistId=<uploads_id>, part='snippet', maxResults=50)`
   → pages through all recent uploads, including private videos (1 unit/page)
3. For each episode in the YAML that has no `youtube_id`, find the upload whose
   `snippet.title` matches the expected title (derived from `title_template`)
4. Write the matched `youtube_id` back to the YAML

Using the uploads playlist is preferred over `search.list` because it:
- Costs 1 unit/page vs 100 units/page for `search.list`
- Returns exact titles (no fuzzy search ambiguity)
- Always includes private videos for the authenticated owner

### Matching logic

The expected title for each episode is rendered from `title_template`. The
sync compares this against the `snippet.title` of each upload. Exact match
is required; unmatched episodes are reported as warnings without writing
anything, so the user can investigate.

### API cost

For 50 or fewer uploads: 2 units total (1 for channel lookup + 1 for playlist
page). For more than 50 uploads: 1 additional unit per page of 50.

---

## Idempotency and state tracking

After each successful operation the `youtube_id` is written back into the
publish YAML file under the episode's `youtube_id:` field. Re-running the tool
skips any episode that already has a `youtube_id`, making the process safe to
interrupt and resume.

Similarly, after playlist creation the playlist ID is written back to
`youtube.playlist.id:` in the YAML.

State is stored in-place in the YAML — there is no separate state file.

Force re-processing of an already-processed episode with `--force`.

---

## YouTube quota

The YouTube Data API v3 has a default quota of **10,000 units per day**.

| Operation | Cost |
|---|---|
| `videos.insert` (automated upload) | 1,600 units |
| `videos.update` (metadata only) | 50 units |
| `thumbnails.set` | 50 units |
| `playlists.insert` | 50 units (once per series) |
| `playlistItems.insert` | 50 units |

### Automated upload workflow

| | |
|---|---|
| Per episode | 1,700 units (`insert` + thumbnail + playlist item) |
| Max per day | ~5 episodes |
| 36 episodes | ~7–8 days |

### Manual upload + API metadata workflow *(recommended)*

| | |
|---|---|
| Per episode | 150 units (`update` + thumbnail + playlist item) |
| Max per day | ~66 episodes |
| 36 episodes | **1 day** (5,400 units total, well within limit) |

The tool prints the estimated quota cost before each run and stops gracefully
when the budget for the day is exhausted. Re-run the next day; already-processed
episodes are skipped automatically.

To request a quota increase: Google Cloud Console → APIs → YouTube Data API v3
→ Quotas → Request higher quota.

---

## Upload mechanics (automated workflow)

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
  --steps STEPS         sync-ids,upload,metadata,thumbnail,playlist,all (default: all)
  --episodes LIST       Comma-separated episode numbers to process (default: all)
  --limit N             Process only the first N episodes; useful for testing a step
                        before running against all episodes
  --dry-run             Print what would happen; make no API calls
  --force               Re-process even if youtube_id already set

Auth:
  --client-secrets FILE Path to client_secrets.json
                        (default: ~/.config/publish2yt/client_secrets.json)
  --token FILE          Path to OAuth token cache
                        (default: ~/.config/publish2yt/token.json)
  --reauth              Force re-authentication (clear cached token)
```

### Usage examples

```bash
# --- Manual upload workflow (recommended for large series) ---

# After uploading in YouTube Studio, sync video IDs from the channel
./publish2yt.py --config vedantasara-publish.yaml --steps sync-ids

# Then apply metadata, thumbnails, and playlist in one day
./publish2yt.py --config vedantasara-publish.yaml --steps metadata,thumbnail,playlist

# --- Automated upload workflow ---

# Full pipeline — upload all episodes, set thumbnails, create playlist
./publish2yt.py --config workingdir/vedantasara/vedantasara-publish.yaml

# Dry run — preview what would happen
./publish2yt.py --config vedantasara-publish.yaml --dry-run

# Upload specific episodes only
./publish2yt.py --config vedantasara-publish.yaml --steps upload --episodes 1,2,3

# --- Common operations ---

# Set thumbnails for already-uploaded episodes
./publish2yt.py --config vedantasara-publish.yaml --steps thumbnail

# Create/update playlist using stored youtube_ids
./publish2yt.py --config vedantasara-publish.yaml --steps playlist

# Re-authenticate (e.g. switching YouTube channels)
./publish2yt.py --config vedantasara-publish.yaml --reauth
```

---

## Key files

| File | Description |
|------|-------------|
| `publish2yt.py` | Main Python script |
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

- Deleting existing YouTube videos
- YouTube Analytics / comments
- Batch scheduling (publishing at a future date) — set `privacy: private` first,
  then manually schedule in YouTube Studio
- Non-podcast (album mode) upload — album mode videos are uploaded the same way
  but the playlist structure differs; treat as a future extension
