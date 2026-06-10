#!/usr/bin/env python3
"""publish2yt — Publish album2yt MP4s to YouTube with metadata, thumbnails, and playlists."""

import argparse
import sys
from datetime import date
from pathlib import Path

import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

DEFAULT_CLIENT_SECRETS = Path.home() / ".config" / "publish2yt" / "client_secrets.json"
DEFAULT_TOKEN = Path.home() / ".config" / "publish2yt" / "token.json"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def authenticate(client_secrets_path, token_path, reauth=False):
    """Return an authenticated YouTube API client. Opens browser on first run."""
    creds = None
    token_path = Path(token_path)

    if not reauth and token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secrets = Path(client_secrets_path)
            if not secrets.exists():
                sys.exit(
                    f"ERROR: client secrets not found: {secrets}\n"
                    "See USAGE.md — 'One-time setup: Google Cloud & OAuth'."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return build("youtube", "v3", credentials=creds)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(config_path):
    config_path = Path(config_path).resolve()
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    cfg["_config_path"] = config_path
    cfg["_config_dir"] = config_path.parent
    return cfg


def _strip_internal(obj):
    """Recursively remove keys starting with '_' (used for runtime-only state)."""
    if isinstance(obj, dict):
        return {k: _strip_internal(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_internal(item) for item in obj]
    return obj


def save_config(cfg):
    """Write cfg back to YAML in-place, stripping internal _keys."""
    config_path = cfg["_config_path"]
    with open(config_path, "w") as f:
        yaml.dump(
            _strip_internal(cfg),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


def resolve_episodes(cfg, input_dir):
    """
    Return the episode list from the publish YAML, album_config, or MP4 auto-discovery.
    Adds a runtime _index to each episode for stable episode_number templating.
    If episodes are not in cfg yet (album_config or auto-discovery path), writes
    them into cfg["episodes"] so save_config persists them on the first run.
    """
    config_dir = cfg["_config_dir"]

    if "episodes" in cfg:
        episodes = cfg["episodes"]
    elif "album_config" in cfg:
        album_path = (config_dir / cfg["album_config"]).resolve()
        with open(album_path) as f:
            album_cfg = yaml.safe_load(f)
        episodes = []
        for ep in album_cfg.get("episodes", []):
            title = ep.get("title") or Path(ep.get("file", "")).stem
            episodes.append({"file": title + ".mp4", "title": title, "youtube_id": None})
        cfg["episodes"] = episodes
    else:
        episodes = [
            {"file": f.name, "title": f.stem, "youtube_id": None}
            for f in sorted(input_dir.glob("*.mp4"))
        ]
        cfg["episodes"] = episodes

    for i, ep in enumerate(episodes):
        ep["_index"] = i

    return episodes


def load_description_template(cfg):
    """Return description template string from file path or inline body."""
    config_dir = cfg["_config_dir"]
    desc = cfg.get("description", {})
    if "template" in desc:
        tmpl_path = (config_dir / desc["template"]).resolve()
        if not tmpl_path.exists():
            print(f"  WARN  description template not found: {tmpl_path}", file=sys.stderr)
            return "{{title}}"
        return tmpl_path.read_text(encoding="utf-8")
    return desc.get("body", "{{title}}")


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def render(template, variables):
    """Replace {{key}} placeholders with values from variables dict."""
    for key, value in variables.items():
        template = template.replace("{{" + key + "}}", str(value) if value else "")
    return template


def make_vars(cfg, episode):
    title = episode.get("title") or Path(episode["file"]).stem
    index = episode.get("_index", 0)
    return {
        "title": title,
        "series_title": cfg.get("title", ""),
        "artist": cfg.get("artist", ""),
        "episode_number": f"{index + 1:02d}",
        "file": Path(episode["file"]).stem,
        "description_extra": episode.get("description_extra") or "",
    }


def _video_body(cfg, episode, description_tmpl):
    """Build the YouTube API resource body for snippet + status."""
    yt = cfg.get("youtube", {})
    vars_ = make_vars(cfg, episode)
    return {
        "snippet": {
            "title": render(yt.get("title_template", "{{title}}"), vars_),
            "description": render(description_tmpl, vars_),
            "tags": yt.get("tags", []),
            "categoryId": str(yt.get("category", 22)),
            "defaultLanguage": yt.get("language", "en"),
        },
        "status": {
            "privacyStatus": yt.get("privacy", "public"),
            "selfDeclaredMadeForKids": yt.get("audience") == "for_kids",
        },
    }


# ---------------------------------------------------------------------------
# Step: sync-ids
# ---------------------------------------------------------------------------

def step_sync_ids(youtube, cfg, episodes, dry_run):
    print("\n=== sync-ids ===")

    channels_resp = youtube.channels().list(part="contentDetails", mine=True).execute()
    uploads_playlist = (
        channels_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    )

    # Page through all uploads, including private videos.
    channel_videos = {}   # title → video_id
    page_token = None
    while True:
        resp = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for item in resp.get("items", []):
            s = item["snippet"]
            channel_videos[s["title"]] = s["resourceId"]["videoId"]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    print(f"  {len(channel_videos)} uploads found on channel")

    title_tmpl = cfg.get("youtube", {}).get("title_template", "{{title}}")
    matched = 0

    for ep in episodes:
        if ep.get("youtube_id"):
            print(f"  skip   {ep['file']} (already has ID)")
            continue
        vars_ = make_vars(cfg, ep)
        expected_title = render(title_tmpl, vars_)
        bare_title = ep.get("title") or Path(ep["file"]).stem
        # Try template title first, then bare episode title (for manually uploaded videos
        # where YouTube Studio used the filename as the title before metadata was applied).
        video_id = channel_videos.get(expected_title) or channel_videos.get(bare_title)
        if video_id:
            matched_on = expected_title if expected_title in channel_videos else bare_title
            print(f"  match  {ep['file']} → {video_id}  (on: {matched_on!r})")
            matched += 1
            if not dry_run:
                ep["youtube_id"] = video_id
                save_config(cfg)
        else:
            print(f"  miss   no upload matches: {expected_title!r} or {bare_title!r}")

    print(f"  {matched} matched")


# ---------------------------------------------------------------------------
# Step: upload
# ---------------------------------------------------------------------------

def step_upload(youtube, cfg, episodes, input_dir, description_tmpl, dry_run, force):
    print("\n=== upload ===")

    for ep in episodes:
        if ep.get("youtube_id") and not force:
            print(f"  skip   {ep['file']} (uploaded: {ep['youtube_id']})")
            continue

        mp4_path = input_dir / ep["file"]
        if not mp4_path.exists():
            print(f"  WARN   not found: {mp4_path}", file=sys.stderr)
            continue

        body = _video_body(cfg, ep, description_tmpl)
        print(f"  upload {ep['file']}")
        print(f"         title: {body['snippet']['title']}")

        if dry_run:
            continue

        media = MediaFileUpload(
            str(mp4_path), mimetype="video/mp4", resumable=True,
            chunksize=10 * 1024 * 1024,
        )
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"\r         {int(status.progress() * 100):3d}%", end="", flush=True)
        print()

        video_id = response["id"]
        print(f"         → https://youtu.be/{video_id}")
        ep["youtube_id"] = video_id
        save_config(cfg)


# ---------------------------------------------------------------------------
# Step: metadata
# ---------------------------------------------------------------------------

def step_metadata(youtube, cfg, episodes, description_tmpl, dry_run, force):
    print("\n=== metadata ===")

    for ep in episodes:
        if not ep.get("youtube_id"):
            print(f"  skip   {ep['file']} (no youtube_id — run sync-ids or upload first)")
            continue

        body = _video_body(cfg, ep, description_tmpl)
        body["id"] = ep["youtube_id"]
        print(f"  update {ep['youtube_id']}  {body['snippet']['title']}")

        if dry_run:
            continue

        youtube.videos().update(part="snippet,status", body=body).execute()


# ---------------------------------------------------------------------------
# Step: thumbnail
# ---------------------------------------------------------------------------

def step_thumbnail(youtube, cfg, episodes, dry_run):
    print("\n=== thumbnail ===")
    config_dir = cfg["_config_dir"]
    default_thumb = cfg.get("thumbnail", {}).get("file")

    for ep in episodes:
        if not ep.get("youtube_id"):
            print(f"  skip   {ep['file']} (no youtube_id)")
            continue

        thumb_file = ep.get("thumbnail") or default_thumb
        if not thumb_file:
            print(f"  skip   {ep['file']} (no thumbnail configured)")
            continue

        thumb_path = (config_dir / thumb_file).resolve()
        if not thumb_path.exists():
            print(f"  WARN   thumbnail not found: {thumb_file}", file=sys.stderr)
            continue

        mime = "image/png" if thumb_path.suffix.lower() == ".png" else "image/jpeg"
        print(f"  thumb  {ep['youtube_id']}  {thumb_path.name}")

        if dry_run:
            continue

        media = MediaFileUpload(str(thumb_path), mimetype=mime)
        youtube.thumbnails().set(videoId=ep["youtube_id"], media_body=media).execute()


# ---------------------------------------------------------------------------
# Step: playlist
# ---------------------------------------------------------------------------

def step_playlist(youtube, cfg, episodes, dry_run):
    print("\n=== playlist ===")
    yt = cfg.get("youtube", {})
    pl = yt.get("playlist", {})

    if not pl.get("enabled", True):
        print("  playlist disabled in config")
        return

    playlist_id = pl.get("id")
    base_vars = {"series_title": cfg.get("title", ""), "artist": cfg.get("artist", "")}

    if not playlist_id:
        pl_title = render(pl.get("title", "{{series_title}} — {{artist}}"), base_vars)
        pl_desc = render(pl.get("description", ""), base_vars)
        print(f"  create playlist: {pl_title}")

        if not dry_run:
            resp = youtube.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {"title": pl_title, "description": pl_desc},
                    "status": {"privacyStatus": yt.get("privacy", "public")},
                },
            ).execute()
            playlist_id = resp["id"]
            print(f"         → https://www.youtube.com/playlist?list={playlist_id}")
            cfg.setdefault("youtube", {}).setdefault("playlist", {})["id"] = playlist_id
            save_config(cfg)

    for ep in episodes:
        if not ep.get("youtube_id"):
            print(f"  skip   {ep['file']} (no youtube_id)")
            continue

        print(f"  add    {ep['youtube_id']}")

        if dry_run or not playlist_id:
            continue

        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": ep["youtube_id"]},
                }
            },
        ).execute()


# ---------------------------------------------------------------------------
# Quota estimate
# ---------------------------------------------------------------------------

def print_quota_estimate(steps, all_episodes, episodes):
    pending = [ep for ep in episodes if not ep.get("youtube_id")]
    done = [ep for ep in episodes if ep.get("youtube_id")]
    cost = 0

    if "sync-ids" in steps:
        cost += 2
    if "upload" in steps:
        cost += len(pending) * 1600
    if "metadata" in steps:
        cost += len(done) * 50
    if "all" in steps:
        cost += len(pending) * 1600 + len(done) * 50
    if "thumbnail" in steps or "all" in steps:
        cost += len(episodes) * 50
    if "playlist" in steps or "all" in steps:
        cost += 50 + len(episodes) * 50

    per_ep = cost // max(len(episodes), 1)
    print(f"Quota estimate: {cost:,} units  ({per_ep} per episode, limit 10,000/day)")
    if cost > 10_000:
        safe = 10_000 // max(per_ep, 1)
        print(f"WARNING: exceeds daily limit — only ~{safe} episode(s) will complete today")


# ---------------------------------------------------------------------------
# Upload log
# ---------------------------------------------------------------------------

def write_upload_log(cfg):
    config_path = cfg["_config_path"]
    log_path = config_path.parent / (config_path.stem + "-log.txt")
    series = cfg.get("title", "")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Upload log — {series} — {date.today()}\n\n")
        for ep in cfg.get("episodes", []):
            vid = ep.get("youtube_id")
            label = "DONE" if vid else "PEND"
            link = f"https://youtu.be/{vid}" if vid else "(not yet uploaded)"
            f.write(f"[{label}]  {ep['file']:<55} {link}\n")

    print(f"\nLog: {log_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Publish album2yt MP4s to YouTube with metadata, thumbnails, and playlists."
    )
    p.add_argument("--config", required=True, metavar="FILE",
                   help="Publish config YAML")

    g = p.add_argument_group("Input")
    g.add_argument("--input", metavar="DIR",
                   help="Folder containing MP4 files (overrides input_dir in YAML)")

    g = p.add_argument_group("Pipeline")
    g.add_argument("--steps", default="all",
                   help="sync-ids,upload,metadata,thumbnail,playlist,all (default: all)")
    g.add_argument("--episodes", metavar="N[,N]",
                   help="1-indexed episode numbers to process, e.g. 1,3,5 (default: all)")
    g.add_argument("--limit", metavar="N", type=int,
                   help="Process only the first N episodes (useful for testing a step)")
    g.add_argument("--dry-run", action="store_true",
                   help="Print what would happen; make no API calls")
    g.add_argument("--force", action="store_true",
                   help="Re-process even if youtube_id is already set")

    g = p.add_argument_group("Auth")
    g.add_argument("--client-secrets", default=str(DEFAULT_CLIENT_SECRETS), metavar="FILE",
                   help=f"Path to client_secrets.json (default: {DEFAULT_CLIENT_SECRETS})")
    g.add_argument("--token", default=str(DEFAULT_TOKEN), metavar="FILE",
                   help=f"Path to OAuth token cache (default: {DEFAULT_TOKEN})")
    g.add_argument("--reauth", action="store_true",
                   help="Force re-authentication (clears cached token)")

    args = p.parse_args()

    cfg = load_config(args.config)
    config_dir = cfg["_config_dir"]

    input_dir = (
        Path(args.input).resolve() if args.input
        else (config_dir / cfg.get("input_dir", "output")).resolve()
    )

    all_episodes = resolve_episodes(cfg, input_dir)

    # Filter to requested episodes (1-indexed)
    if args.episodes:
        indices = {int(n) - 1 for n in args.episodes.split(",")}
        episodes = [ep for ep in all_episodes if ep.get("_index") in indices]
    else:
        episodes = all_episodes

    if args.limit:
        episodes = episodes[:args.limit]

    steps = [s.strip() for s in args.steps.split(",")]

    print_quota_estimate(steps, all_episodes, episodes)
    if args.dry_run:
        print("DRY RUN — no API calls will be made\n")

    youtube = authenticate(args.client_secrets, args.token, args.reauth)
    description_tmpl = load_description_template(cfg)

    try:
        if "sync-ids" in steps:
            step_sync_ids(youtube, cfg, episodes, args.dry_run)

        if "all" in steps:
            pending = [ep for ep in episodes if not ep.get("youtube_id")]
            done = [ep for ep in episodes if ep.get("youtube_id")]
            if pending:
                step_upload(youtube, cfg, pending, input_dir, description_tmpl,
                            args.dry_run, args.force)
            if done:
                step_metadata(youtube, cfg, done, description_tmpl,
                              args.dry_run, args.force)
            step_thumbnail(youtube, cfg, episodes, args.dry_run)
            step_playlist(youtube, cfg, episodes, args.dry_run)
        else:
            if "upload" in steps:
                step_upload(youtube, cfg, episodes, input_dir, description_tmpl,
                            args.dry_run, args.force)
            if "metadata" in steps:
                step_metadata(youtube, cfg, episodes, description_tmpl,
                              args.dry_run, args.force)
            if "thumbnail" in steps:
                step_thumbnail(youtube, cfg, episodes, args.dry_run)
            if "playlist" in steps:
                step_playlist(youtube, cfg, episodes, args.dry_run)

    except HttpError as e:
        if e.status_code == 403:
            details = str(e)
            if "quotaExceeded" in details or "forbidden" in details.lower():
                print(
                    f"\nERROR: quota exceeded or permission denied.\n{e}",
                    file=sys.stderr,
                )
                print(
                    "If quota exceeded, re-run tomorrow — already-processed episodes"
                    " are skipped automatically.",
                    file=sys.stderr,
                )
                write_upload_log(cfg)
                sys.exit(1)
        raise

    write_upload_log(cfg)
    print("\nDone.")


if __name__ == "__main__":
    main()
