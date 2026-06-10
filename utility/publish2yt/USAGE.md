# publish2yt — Usage Guide

Uploads YouTube-ready MP4 files (produced by `album2yt`) to YouTube via the
YouTube Data API v3. Sets video metadata, thumbnails, and creates a playlist.

---

## Prerequisites

- Python 3.10+
- A Google account with a YouTube channel
- Google Cloud project with the YouTube Data API v3 enabled

---

## One-time setup: Google Cloud & OAuth

These steps create the credentials that allow the tool to upload on your behalf.

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a
   new project (or select an existing one).

2. Enable **YouTube Data API v3**: APIs & Services → Library → search
   "YouTube Data API v3" → Enable.

3. Create OAuth credentials: APIs & Services → Credentials → Create Credentials
   → OAuth client ID → Application type: **Desktop app** → Download JSON.

4. Save the downloaded file as:
   ```
   ~/.config/publish2yt/client_secrets.json
   ```

5. First run opens a browser for consent. After you approve, a token is cached
   at `~/.config/publish2yt/token.json` and subsequent runs are automatic.

---

## Choosing a workflow

There are two ways to get videos onto YouTube. The choice depends on how many
videos you are publishing and whether you have already uploaded them manually.

### Manual upload + API metadata *(recommended for series)*

Upload MP4 files in YouTube Studio by hand (no API quota used for uploads),
then use this script to apply metadata, thumbnails, and the playlist.

| | |
|---|---|
| API cost per video | ~150 units |
| 36-episode series | ~5,400 units — fits in one day |

```
1. Upload MP4s in YouTube Studio (set to Private)
2. Run: publish2yt --steps sync-ids   ← finds video IDs automatically
3. Run: publish2yt --steps metadata,thumbnail,playlist
```

### Automated upload

The script uploads MP4 files directly.

| | |
|---|---|
| API cost per video | ~1,700 units |
| 36-episode series | ~61,000 units — ~7–8 days |

```
1. Run: publish2yt   ← uploads, sets metadata, thumbnail, playlist in one run
```

---

## Quick start (manual workflow)

Given an `album2yt` podcast output at `workingdir/vedantasara/output/`:

```
workingdir/vedantasara/
  vedantasara.yaml              ← album2yt config (already exists)
  vedantasara-publish.yaml      ← create this (publish2yt config)
  images/
    VedantaSara.jpeg
  output/
    01 Vedantasara Texts 1.mp4
    02 Vedantasara Texts 2 to 3.mp4
    ...
```

1. Upload MP4s in YouTube Studio, setting each to **Private**.
2. Sync the video IDs back to the YAML automatically:
   ```bash
   ./publish2yt.py --config workingdir/vedantasara/vedantasara-publish.yaml --steps sync-ids
   ```
   The script lists the channel's recent uploads (including private videos) and
   matches them to episodes by title, writing `youtube_id` into the YAML.
3. Apply metadata, thumbnails, and create the playlist:
   ```bash
   ./publish2yt.py --config workingdir/vedantasara/vedantasara-publish.yaml \
     --steps metadata,thumbnail,playlist
   ```

---

## Publish config YAML

### Minimal example

```yaml
title: "Vedantasara"
artist: "Swami Chetanananda"
album_config: "vedantasara.yaml"   # inherit episode list from album2yt config

youtube:
  privacy: public
  audience: not_for_kids
  tags:
    - "Vedanta"
    - "Swami Chetanananda"

thumbnail:
  file: "images/VedantaSara.jpeg"

description:
  body: |
    {{title}}

    Swami Chetanananda's teachings on the Vedantasara, a classical
    Advaita Vedanta text by Sadananda Yogendra Saraswati.

    Part of the series: {{series_title}} — {{artist}}
```

### Full example with all options

```yaml
title: "Vedantasara"
artist: "Swami Chetanananda"
album_config: "vedantasara.yaml"
input_dir: "output"              # folder containing MP4s (default: output/)

youtube:
  privacy: public                # public | private | unlisted
  audience: not_for_kids         # not_for_kids | for_kids
  category: 22                   # 22 People & Blogs, 27 Education, 29 Nonprofits
  language: en
  tags:
    - "Vedanta"
    - "Vedantasara"
    - "Swami Chetanananda"
    - "Advaita Vedanta"

  title_template: "{{title}} | {{artist}}"

  playlist:
    enabled: true
    title: "{{series_title}} — {{artist}}"
    description: "Complete teachings on the Vedantasara by Swami Chetanananda."

thumbnail:
  file: "images/VedantaSara.jpeg"

description:
  template: "templates/description.txt"   # external file (see below)

episodes:                        # optional explicit list (see Episode list section)
  - file: "01 Vedantasara Texts 1.mp4"
    title: "Vedantasara Texts 1 | Swami Chetanananda"
    youtube_id: null             # filled in automatically after upload
  - file: "02 Vedantasara Texts 2 to 3.mp4"
    title: "Vedantasara Texts 2 to 3 | Swami Chetanananda"
    youtube_id: null
```

---

## Episode list

There are three ways to specify which videos to upload:

**1. Explicit list in publish YAML** (highest priority)

```yaml
episodes:
  - file: "01 Vedantasara Texts 1.mp4"
    title: "Vedantasara Texts 1 | Swami Chetanananda"
```

**2. Inherit from album2yt config**

```yaml
album_config: "vedantasara.yaml"
# Reads the `episodes:` list from vedantasara.yaml and maps each episode title
# to the corresponding MP4 filename in input_dir.
```

**3. Auto-discover** (fallback)

If neither `episodes:` nor `album_config:` is set, all `*.mp4` files in
`input_dir` are processed in filename sort order.

### Per-episode overrides

Any field can be overridden per episode:

```yaml
episodes:
  - file: "05 Special Episode.mp4"
    title: "Special Episode Title | Swami Chetanananda"
    thumbnail: "images/special-cover.jpg"   # overrides default thumbnail
    description_extra: |                    # appended to common description
      This special episode covers...
    youtube_id: null
```

---

## Description templates

Write a plain-text file with `{{variable}}` placeholders:

```
workingdir/vedantasara/
  templates/
    description.txt
```

**Available variables:**

| Variable | Value |
|---|---|
| `{{title}}` | Episode title |
| `{{series_title}}` | Top-level `title:` |
| `{{artist}}` | Top-level `artist:` |
| `{{episode_number}}` | Zero-padded number (01, 02, …) |
| `{{file}}` | MP4 filename without extension |
| `{{description_extra}}` | Per-episode extra text (empty if not set) |

**Example `description.txt`:**

```
{{title}}

{{artist}} expounds on the {{series_title}}, a classical Advaita Vedanta text
by Sadananda Yogendra Saraswati.

These teachings were recorded at the Movement Center, Portland, Oregon.

Part of the playlist: {{series_title}} — {{artist}}
https://youtube.com/playlist?list=<paste playlist link after creation>
{{description_extra}}
Subscribe: [your channel link]
```

You can also write the description inline in the YAML using `description.body:`:

```yaml
description:
  body: |
    {{title}}

    {{artist}} expounds on the {{series_title}}...
```

Use `template:` (file) or `body:` (inline), not both.

---

## Thumbnails

Set a default thumbnail for all episodes:

```yaml
thumbnail:
  file: "images/VedantaSara.jpeg"
```

Override per episode:

```yaml
episodes:
  - file: "01 ..."
    thumbnail: "images/ep01-special.jpg"
```

**Thumbnail requirements:**
- Format: JPEG or PNG
- Maximum file size: 2 MB
- Recommended: 1280×720 px, 16:9 aspect ratio

**Note:** Thumbnail upload (`thumbnails.set`) requires the YouTube channel to
have thumbnail upload permission. New channels may need to verify via phone
number in YouTube Studio first.

---

## Playlist

By default the tool creates a YouTube playlist named
`"<series_title> — <artist>"` and adds each uploaded video in order.

```yaml
youtube:
  playlist:
    enabled: true
    title: "{{series_title}} — {{artist}}"
```

To add to an **existing playlist** instead of creating a new one:

```yaml
youtube:
  playlist:
    id: "PLxxxxxxxxxxxxxxxxxxxx"
```

After playlist creation, the tool writes the playlist ID back to the YAML
under `youtube.playlist.id` so it is reused on subsequent runs.

To skip playlist creation entirely:

```yaml
youtube:
  playlist:
    enabled: false
```

---

## Privacy and audience

```yaml
youtube:
  privacy: public        # public | private | unlisted
  audience: not_for_kids
```

Use `privacy: private` to upload without making videos publicly visible, then
schedule or publish manually in YouTube Studio.

The `audience: not_for_kids` setting marks videos as not targeted at children,
complying with COPPA. Most spiritual/educational content should use this.

---

## Pipeline steps

| Step | What it does | Requires `youtube_id`? |
|------|-------------|------------------------|
| `sync-ids` | Looks up private/public videos on your channel by title and writes `youtube_id` into the YAML. | No |
| `upload` | Uploads MP4 files via API. Skips episodes that already have a `youtube_id`. | No |
| `metadata` | Updates title, description, tags, audience, privacy on existing videos. | Yes |
| `thumbnail` | Uploads and sets thumbnail images. | Yes |
| `playlist` | Creates the playlist and adds videos in order. | Yes |
| `all` | Smart default: `upload` for episodes without an ID, `metadata` for those with one, then `thumbnail` and `playlist` for all. | — |

```bash
# Manual upload workflow
./publish2yt.py --config vedantasara-publish.yaml --steps sync-ids
./publish2yt.py --config vedantasara-publish.yaml --steps metadata,thumbnail,playlist

# Automated upload workflow
./publish2yt.py --config vedantasara-publish.yaml   # runs all steps

# Update metadata only (e.g. to fix a description)
./publish2yt.py --config vedantasara-publish.yaml --steps metadata

# Add thumbnails after the fact
./publish2yt.py --config vedantasara-publish.yaml --steps thumbnail

# Rebuild the playlist
./publish2yt.py --config vedantasara-publish.yaml --steps playlist
```

---

## Idempotency: safe to re-run

After each successful upload the tool writes the YouTube video ID back into
the YAML:

```yaml
episodes:
  - file: "01 Vedantasara Texts 1.mp4"
    youtube_id: "dQw4w9WgXcQ"     ← written automatically
```

Re-running skips any episode that already has a `youtube_id`. You can safely
interrupt and resume — only unfinished episodes are processed.

To re-process an already-processed episode (e.g. to update its metadata):
```bash
./publish2yt.py --config vedantasara-publish.yaml --steps metadata --episodes 1 --force
```

---

## YouTube quota limits

The YouTube Data API v3 has a default quota of 10,000 units per day.

| Workflow | API cost per video | 36 episodes |
|---|---|---|
| Automated upload (`videos.insert`) | ~1,700 units | ~7–8 days |
| Manual upload + API metadata (`videos.update`) | ~150 units | **1 day** |

The manual upload workflow is strongly recommended for any series longer than
5 episodes. Upload the MP4s through YouTube Studio, run `sync-ids` to collect
the video IDs, then apply metadata, thumbnails, and the playlist via API — all
36 episodes fit comfortably within one day's quota.

The tool prints the estimated quota cost before each run and stops gracefully
when the budget for the day is exhausted. Re-run the next day — already-processed
episodes are skipped automatically.

To increase your daily quota: Google Cloud Console → APIs & Services →
YouTube Data API v3 → Quotas → Request higher quota.

---

## CLI reference

```
./publish2yt.py --config <yaml> [options]

Required:
  --config FILE     Publish config YAML

Input:
  --input DIR       Folder containing MP4 files (overrides input_dir in YAML)

Pipeline control:
  --steps STEPS     sync-ids,upload,metadata,thumbnail,playlist,all (default: all)
  --episodes LIST   Comma-separated episode numbers to process (default: all)
  --limit N         Process only the first N episodes; use to test a step on a
                    small batch before running against all episodes
  --dry-run         Preview what would happen; make no API calls
  --force           Re-process even if youtube_id is already set

Auth:
  --client-secrets FILE  Path to client_secrets.json
                         (default: ~/.config/publish2yt/client_secrets.json)
  --token FILE           Path to OAuth token cache
                         (default: ~/.config/publish2yt/token.json)
  --reauth               Force re-authentication (clear cached token)
```

### Examples

```bash
# --- Manual upload workflow (recommended) ---

# After uploading in YouTube Studio, find and record the video IDs
./publish2yt.py --config vedantasara-publish.yaml --steps sync-ids

# Apply metadata, thumbnails, and playlist (all 36 episodes, one day)
./publish2yt.py --config vedantasara-publish.yaml --steps metadata,thumbnail,playlist

# --- Automated upload workflow ---

# Upload everything via API (runs all steps)
./publish2yt.py --config workingdir/vedantasara/vedantasara-publish.yaml

# Preview without making any API calls
./publish2yt.py --config vedantasara-publish.yaml --dry-run

# Upload only specific episodes
./publish2yt.py --config vedantasara-publish.yaml --steps upload --episodes 1,2,3

# --- Testing ---

# Test metadata+thumbnail+playlist on the first 3 episodes before running all 36
./publish2yt.py --config vedantasara-publish.yaml --steps metadata,thumbnail,playlist --limit 3

# Dry-run the same to preview without any API calls
./publish2yt.py --config vedantasara-publish.yaml --steps metadata,thumbnail,playlist --limit 3 --dry-run

# --- Fixes and corrections ---

# Update the description on all episodes (already uploaded)
./publish2yt.py --config vedantasara-publish.yaml --steps metadata

# Re-apply metadata to one episode, overwriting what's there
./publish2yt.py --config vedantasara-publish.yaml --steps metadata --episodes 5 --force

# Re-authenticate (e.g. switching YouTube channels)
./publish2yt.py --config vedantasara-publish.yaml --reauth
```
