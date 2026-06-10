#!/usr/bin/env python3
"""album2yt — Convert ripped CD albums to YouTube-ready MP4s with chapter markers."""

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, ID3NoHeaderError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hms(seconds):
    """Format seconds as H:MM:SS or M:SS."""
    s = int(seconds)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_duration(text):
    """Parse MM:SS or HH:MM:SS string → float seconds."""
    parts = [int(p) for p in text.strip().split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def get_duration(path):
    """Return track duration in seconds (float) via mutagen."""
    audio = MP3(str(path))
    if audio.info.length <= 0:
        raise ValueError(f"Cannot determine duration: {path}")
    return audio.info.length


def run_ffmpeg(*args):
    """Run ffmpeg, printing stderr and raising on failure."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + [str(a) for a in args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed (exit {result.returncode})")


# Scale to 1920x1080, preserving aspect ratio, with black letterbox/pillarbox padding.
SCALE = (
    "scale=1920:1080:force_original_aspect_ratio=decrease,"
    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black"
)


# ---------------------------------------------------------------------------
# Config loading and I/O resolution
# ---------------------------------------------------------------------------

def load_config(config_path):
    config_path = Path(config_path).resolve()
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    cfg["_config_dir"] = config_path.parent
    return cfg


def resolve_io(cfg, input_arg, output_arg, cover_arg):
    """Resolve --input/--output/--cover into absolute Paths."""
    config_dir = cfg["_config_dir"]

    if input_arg:
        input_dir = Path(input_arg).resolve()
    elif "input_dir" in cfg:
        input_dir = Path(cfg["input_dir"]).resolve()
    else:
        input_dir = config_dir

    output_dir = Path(output_arg).resolve() if output_arg else config_dir

    if cover_arg:
        default_cover = Path(cover_arg).resolve()
    else:
        candidate = input_dir / "cover.jpg"
        default_cover = candidate if candidate.exists() else None

    return input_dir, output_dir, default_cover


# ---------------------------------------------------------------------------
# Folder structure detection
# ---------------------------------------------------------------------------

_DISC_RE = re.compile(
    r'(?:disc|disk|cd|part)[\s_-]*(\d+)|[\s_-](\d+)\s*$', re.IGNORECASE
)


def detect_structure(cfg, input_dir):
    """Auto-detect or return declared folder_structure."""
    declared = cfg.get("folder_structure", "auto")
    if declared != "auto":
        return declared

    audio = [f for f in input_dir.glob("*.mp3")
             if not re.match(r'^disc\d+_audio\.mp3$', f.name)]

    if not audio:
        siblings = [d for d in input_dir.parent.iterdir() if d.is_dir()]
        if any(_DISC_RE.search(d.name) for d in siblings):
            return "multi_folder_top"

    subdirs_with_audio = [
        d for d in input_dir.iterdir()
        if d.is_dir() and list(d.glob("*.mp3"))
    ]
    if subdirs_with_audio:
        return "multi_folder"

    if audio and all(re.match(r'^\d+-\d+', f.name) for f in audio):
        return "multi_disc_flat"

    return "single_disc"


def resolve_disc_folders(cfg, input_dir, structure):
    """Return {disc_number: Path} for every disc in config."""
    result = {}
    for disc in cfg.get("discs", []):
        n = disc["number"]
        if structure in ("single_disc", "multi_disc_flat"):
            result[n] = input_dir
        elif structure == "multi_folder":
            if "folder" in disc:
                result[n] = (input_dir / disc["folder"]).resolve()
            else:
                result[n] = _find_subfolder(input_dir, n) or input_dir
        else:  # multi_folder_top
            if "folder" in disc:
                result[n] = (input_dir.parent / disc["folder"]).resolve()
            else:
                result[n] = _find_sibling_folder(input_dir, n) or input_dir
    return result


def _find_subfolder(parent, disc_number):
    for d in parent.iterdir():
        if d.is_dir():
            m = re.search(r'(\d+)', d.name)
            if m and int(m.group(1)) == disc_number:
                return d
    return None


def _find_sibling_folder(ref_dir, disc_number):
    for d in ref_dir.parent.iterdir():
        if not d.is_dir():
            continue
        m = _DISC_RE.search(d.name)
        if m:
            num = int(m.group(1) or m.group(2))
            if num == disc_number:
                return d
    return None


# ---------------------------------------------------------------------------
# File finding
# ---------------------------------------------------------------------------

def find_track_file(disc_folder, disc_number, track_number, structure):
    """
    Locate the MP3 for a disc+track using regex to avoid prefix ambiguity.

    Glob patterns like `1-1*.mp3` incorrectly match `1-10`, `1-11`, etc.
    Instead we scan the folder and require a non-digit character immediately
    after the track number, e.g. `1-1-` or `1-01 ` but NOT `1-10-`.
    The pattern `D-0?T[^0-9]` allows optional leading zero (1-01 or 1-1).
    """
    all_mp3s = sorted(f for f in disc_folder.iterdir() if f.suffix.lower() == ".mp3")

    if structure == "multi_disc_flat":
        regexes = [
            re.compile(rf"^{disc_number}-0?{track_number}[^0-9]"),
        ]
    elif structure in ("multi_folder", "multi_folder_top"):
        regexes = [
            re.compile(rf"^{disc_number}-0?{track_number}[^0-9]"),  # post-rename
            re.compile(rf"^0?{track_number}[^0-9]"),                 # pre-rename
        ]
    else:  # single_disc
        regexes = [
            re.compile(rf"^0?{track_number}[^0-9]"),
        ]

    for rx in regexes:
        matches = [f for f in all_mp3s if rx.match(f.name)]
        if matches:
            return matches[0]

    raise FileNotFoundError(
        f"No file for disc {disc_number} track {track_number} in {disc_folder}"
    )


# ---------------------------------------------------------------------------
# Rename step
# ---------------------------------------------------------------------------

def _target_filename(disc_number, track_number, title, structure, no_title_dash):
    sep = "-" if not no_title_dash else " "
    if structure == "single_disc":
        return f"{track_number:02d}{sep}{title}.mp3"
    return f"{disc_number}-{track_number:02d}{sep}{title}.mp3"


def _update_title_tag(path, title):
    try:
        tags = ID3(str(path))
    except ID3NoHeaderError:
        tags = ID3()
    tags["TIT2"] = TIT2(encoding=3, text=title)
    tags.save(str(path))


def step_rename(cfg, disc_folders, structure, discs_filter, force_rename,
                no_title_dash, dry_run=False):
    label = "rename (dry run)" if dry_run else "rename"
    print(f"\n=== {label} ===")
    for disc in cfg.get("discs", []):
        n = disc["number"]
        if discs_filter and n not in discs_filter:
            continue
        folder = disc_folders[n]
        for track in disc["tracks"]:
            filename_title = track.get("short_title") or track["title"]
            target_name = _target_filename(
                n, track["number"], filename_title, structure, no_title_dash
            )
            target_path = folder / target_name

            if target_path.exists() and not force_rename:
                print(f"  skip   {target_name}")
                continue

            try:
                src = find_track_file(folder, n, track["number"], structure)
            except FileNotFoundError as e:
                print(f"  WARN   {e}", file=sys.stderr)
                continue

            if src == target_path:
                print(f"  skip   {target_name}")
                continue

            if dry_run:
                print(f"  would  {src.name} → {target_name}")
            else:
                src.rename(target_path)
                _update_title_tag(target_path, filename_title)
                print(f"  rename {src.name} → {target_name}")


# ---------------------------------------------------------------------------
# Image schedule helpers (used by chapters and mp4 steps)
# ---------------------------------------------------------------------------

def _resolve_image(file_str, disc_folder, config_dir):
    """Resolve an image path: absolute as-is, else disc_folder, else config_dir."""
    p = Path(file_str)
    if p.is_absolute():
        return p
    candidate = disc_folder / p
    if candidate.exists():
        return candidate
    return config_dir / p


def build_image_schedule(disc, disc_folder, default_cover, track_durations,
                         album_covers=None, config_dir=None):
    """
    Return [(image_path, duration_secs), ...] covering all tracks in
    track_durations. Handles single image, hold mode, slideshow, and
    per-track overrides.

    Disc-level covers take priority over album-level covers.
    """
    config_dir = config_dir or disc_folder
    covers_cfg = disc.get("covers") or album_covers
    tracks = [t for t in disc["tracks"] if t["number"] in track_durations]

    per_track = {
        t["number"]: _resolve_image(t["cover"], disc_folder, config_dir)
        for t in tracks if "cover" in t
    }

    if not covers_cfg and not per_track:
        total = sum(track_durations.values())
        return [(default_cover, total)]

    if covers_cfg and covers_cfg.get("mode") == "slideshow":
        total = sum(track_durations.values())
        return _slideshow_schedule(covers_cfg, disc_folder, config_dir, total)

    return _hold_schedule(tracks, covers_cfg, disc_folder, config_dir,
                          default_cover, track_durations, per_track)


def _hold_schedule(tracks, covers_cfg, disc_folder, config_dir,
                   default_cover, track_durations, per_track):
    section_changes = {}
    if covers_cfg and covers_cfg.get("mode") == "hold":
        for entry in covers_cfg.get("images", []):
            from_t = entry.get("from_track", 1)
            section_changes[from_t] = _resolve_image(entry["file"], disc_folder, config_dir)

    current_image = default_cover
    schedule = []  # [[Path, float], ...]

    for track in sorted(tracks, key=lambda t: t["number"]):
        tnum = track["number"]
        if tnum in section_changes:
            current_image = section_changes[tnum]
        image = per_track.get(tnum, current_image)
        dur = track_durations.get(tnum, 0.0)
        if schedule and schedule[-1][0] == image:
            schedule[-1][1] += dur
        else:
            schedule.append([image, dur])

    return [(p, d) for p, d in schedule]


def _slideshow_schedule(covers_cfg, disc_folder, config_dir, total_duration):
    interval = covers_cfg.get("interval", 30)
    images = [_resolve_image(e["file"], disc_folder, config_dir)
              for e in covers_cfg.get("images", [])]
    if not images:
        return []
    schedule = []
    remaining = total_duration

    # Intro image: shown once at the start, not included in the cycling rotation.
    intro_cfg = covers_cfg.get("intro")
    if intro_cfg and remaining > 0:
        intro_path = _resolve_image(intro_cfg["file"], disc_folder, config_dir)
        intro_dur = min(float(intro_cfg.get("duration", interval)), remaining)
        schedule.append([intro_path, intro_dur])
        remaining -= intro_dur

    idx = 0
    while remaining > 0:
        img = images[idx % len(images)]
        dur = min(float(interval), remaining)
        if schedule and schedule[-1][0] == img:
            schedule[-1][1] += dur
        else:
            schedule.append([img, dur])
        remaining -= dur
        idx += 1
    return [(p, d) for p, d in schedule]


def _write_image_concat(schedule, path):
    """Write an ffmpeg image concat file from a schedule list."""
    with open(path, "w") as f:
        for img, dur in schedule:
            f.write(f"file '{img}'\nduration {dur:.3f}\n")
        # ffmpeg concat demuxer requires the last file listed again without duration
        if schedule:
            f.write(f"file '{schedule[-1][0]}'\n")


# ---------------------------------------------------------------------------
# Chapters step
# ---------------------------------------------------------------------------

def _write_concat_list(path, track_files):
    with open(path, "w") as f:
        for p in track_files:
            f.write(f"file '{p}'\n")


def _write_chapter_metadata(path, tracks, track_durations):
    with open(path, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        offset = 0.0
        for t in sorted(tracks, key=lambda x: x["number"]):
            dur = track_durations.get(t["number"], 0.0)
            start_ms = int(offset * 1000)
            end_ms = int((offset + dur) * 1000)
            f.write(
                f"\n[CHAPTER]\nTIMEBASE=1/1000\n"
                f"START={start_ms}\nEND={end_ms}\ntitle={t['title']}\n"
            )
            offset += dur


def _write_yt_chapters(path, tracks, track_durations):
    with open(path, "w", encoding="utf-8") as f:
        offset = 0.0
        for t in sorted(tracks, key=lambda x: x["number"]):
            f.write(f"{hms(offset)} {t['title']}\n")
            offset += track_durations.get(t["number"], 0.0)


def _read_blurb(file_str, config_dir):
    """Read a description blurb text file. Resolves relative to config_dir."""
    if not file_str:
        return None
    p = Path(file_str)
    resolved = p if p.is_absolute() else config_dir / p
    if not resolved.exists():
        print(f"  WARN  blurb file not found: {resolved}")
        return None
    return resolved.read_text(encoding="utf-8").strip()


def _write_disc_description(path, cfg, disc, track_durations, tracks,
                             header=None, footer=None):
    with open(path, "w", encoding="utf-8") as f:
        if header:
            f.write(header + "\n\n")
        f.write(f"{cfg['title']} — Disc {disc['number']}: {disc['name']}\n")
        f.write(f"{cfg['artist']}\n\nChapters:\n")
        offset = 0.0
        for t in sorted(tracks, key=lambda x: x["number"]):
            f.write(f"{hms(offset)} {t['title']}\n")
            offset += track_durations.get(t["number"], 0.0)
        f.write("\nPlaylist Link:\n")
        if footer:
            f.write("\n" + footer + "\n")


def _write_playlist(path, cfg):
    discs = cfg.get("discs", [])
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Playlist: {cfg['title']} — {cfg['artist']}\n\n")
        f.write(f"{cfg['title']} is a {len(discs)}-disc recording of...\n")
        f.write("[paste your own description here]\n\nVideos in this playlist:\n")
        for d in discs:
            f.write(f"{d['number']}. {cfg['title']} - Disc {d['number']} {d['name']}\n")


def _write_checklist(path, cfg):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Upload checklist — {cfg['title']}\n\n")
        for d in cfg.get("discs", []):
            n, name = d["number"], d["name"]
            mp4 = f"{cfg['title']} - Disc {n} {name}.mp4"
            f.write(f"[ ] Disc {n}: {mp4}\n")
            f.write(f"    Title:       {cfg['title']} — Disc {n}: {name}\n")
            f.write(f"    Description: copy from disc{n}_youtube_description.txt\n")
            f.write(f"    Tags:        {cfg['artist']}, {cfg['title']}, disc {n}, {name}\n\n")


def step_chapters(cfg, disc_folders, structure, output_dir, discs_filter, tracks_limit):
    print("\n=== chapters ===")
    output_dir.mkdir(parents=True, exist_ok=True)

    config_dir = cfg["_config_dir"]
    yt_cfg = cfg.get("youtube", {})
    header = _read_blurb(yt_cfg.get("description_header"), config_dir)
    footer = _read_blurb(yt_cfg.get("description_footer"), config_dir)

    for disc in cfg.get("discs", []):
        n = disc["number"]
        if discs_filter and n not in discs_filter:
            continue

        folder = disc_folders[n]
        tracks = disc["tracks"][:tracks_limit] if tracks_limit else disc["tracks"]

        track_files = []
        track_durations = {}
        for t in sorted(tracks, key=lambda x: x["number"]):
            path = find_track_file(folder, n, t["number"], structure)
            track_durations[t["number"]] = get_duration(path)
            track_files.append(path)

        if "duration" in disc:
            declared = parse_duration(disc["duration"])
            actual = sum(track_durations.values())
            if abs(actual - declared) > 5:
                print(
                    f"  WARN  disc {n}: declared {disc['duration']}, "
                    f"actual {hms(actual)} (diff {abs(actual - declared):.0f}s)"
                )

        def out(name):
            return output_dir / name

        _write_concat_list(out(f"disc{n}_tracks.txt"), track_files)
        _write_chapter_metadata(out(f"disc{n}_metadata.txt"), tracks, track_durations)
        _write_yt_chapters(out(f"disc{n}_youtube_chapters.txt"), tracks, track_durations)
        _write_disc_description(
            out(f"disc{n}_youtube_description.txt"), cfg, disc, track_durations, tracks,
            header=header, footer=footer
        )
        for name in [
            f"disc{n}_tracks.txt",
            f"disc{n}_metadata.txt",
            f"disc{n}_youtube_chapters.txt",
            f"disc{n}_youtube_description.txt",
        ]:
            print(f"  wrote {name}")

    _write_playlist(output_dir / "youtube_playlist.txt", cfg)
    _write_checklist(output_dir / "youtube_upload_checklist.txt", cfg)
    print("  wrote youtube_playlist.txt")
    print("  wrote youtube_upload_checklist.txt")


# ---------------------------------------------------------------------------
# MP4 step
# ---------------------------------------------------------------------------

def _disc_cover(disc, disc_folder, fallback, album_covers=None, config_dir=None):
    """Resolve the base cover image for a disc (before per-track overrides).
    Disc-level covers take priority over album-level covers."""
    config_dir = config_dir or disc_folder
    covers_cfg = disc.get("covers") or album_covers
    if covers_cfg:
        images = covers_cfg.get("images", [])
        if images:
            p = _resolve_image(images[0]["file"], disc_folder, config_dir)
            if p.exists():
                return p
    return fallback


def step_mp4(cfg, disc_folders, structure, output_dir, default_cover,
             discs_filter, tracks_limit):
    print("\n=== mp4 ===")
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = output_dir / "working"
    tmp_dir.mkdir(exist_ok=True)

    for disc in cfg.get("discs", []):
        n = disc["number"]
        if discs_filter and n not in discs_filter:
            continue

        folder = disc_folders[n]
        tracks = disc["tracks"][:tracks_limit] if tracks_limit else disc["tracks"]

        track_durations = {}
        for t in sorted(tracks, key=lambda x: x["number"]):
            path = find_track_file(folder, n, t["number"], structure)
            track_durations[t["number"]] = get_duration(path)

        # Concatenate audio tracks
        concat_path = output_dir / f"disc{n}_tracks.txt"
        if not concat_path.exists():
            sys.exit(f"ERROR: {concat_path} not found — run the chapters step first")
        audio_path = tmp_dir / f"disc{n}_audio.mp3"
        if audio_path.exists():
            audio_path.unlink()
        run_ffmpeg("-f", "concat", "-safe", "0", "-i", concat_path,
                   "-c", "copy", audio_path)
        print(f"  concat → {audio_path.name}")

        meta_path = output_dir / f"disc{n}_metadata.txt"
        if not meta_path.exists():
            sys.exit(f"ERROR: {meta_path} not found — run the chapters step first")

        album_covers = cfg.get("covers")
        config_dir = cfg["_config_dir"]
        cover = _disc_cover(disc, folder, default_cover, album_covers, config_dir)
        if cover is None:
            sys.exit(
                f"ERROR: no cover image for disc {n}. "
                f"Use --cover or place cover.jpg in {folder}"
            )

        schedule = build_image_schedule(disc, folder, cover, track_durations,
                                        album_covers, config_dir)
        mp4_path = output_dir / f"{cfg['title']} - Disc {n} {disc['name']}.mp4"

        if len(schedule) == 1:
            run_ffmpeg(
                "-loop", "1", "-i", schedule[0][0],
                "-i", audio_path,
                "-i", meta_path,
                "-map_metadata", "2",
                "-vf", SCALE,
                "-c:v", "libx264", "-tune", "stillimage",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest", mp4_path,
            )
        else:
            img_concat = tmp_dir / f"disc{n}_images.txt"
            _write_image_concat(schedule, img_concat)
            run_ffmpeg(
                "-f", "concat", "-safe", "0", "-i", img_concat,
                "-i", audio_path,
                "-i", meta_path,
                "-map_metadata", "2",
                "-vf", SCALE,
                "-c:v", "libx264", "-tune", "stillimage",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest", mp4_path,
            )

        print(f"  wrote {mp4_path.name}")


# ---------------------------------------------------------------------------
# Podcast mode
# ---------------------------------------------------------------------------

def run_podcast(cfg, input_dir, output_dir, default_cover, number_outputs,
                tracks_limit=None):
    print("\n=== podcast ===")
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = output_dir / "working"
    tmp_dir.mkdir(exist_ok=True)

    episodes = cfg.get("episodes")
    if episodes:
        items = [(input_dir / ep["file"], ep) for ep in episodes]
    else:
        items = [(f, {}) for f in sorted(input_dir.glob("*.mp3"))]

    if tracks_limit:
        items = items[:tracks_limit]

    covers_cfg = cfg.get("covers", {})
    config_dir = cfg["_config_dir"]
    cover_images = [_resolve_image(e["file"], input_dir, config_dir)
                    for e in covers_cfg.get("images", [])]
    cover_mode = covers_cfg.get("mode", "hold")

    total = len(items)
    for idx, (src, ep_meta) in enumerate(items, start=1):
        if ep_meta.get("title"):
            out_name = ep_meta["title"] + ".mp4"
        elif number_outputs:
            out_name = f"{idx:02d} {src.stem}.mp4"
        else:
            out_name = src.stem + ".mp4"
        out_path = output_dir / out_name

        print(f"  [{idx}/{total}] converting {out_name} ...")

        if ep_meta.get("cover"):
            cover = input_dir / ep_meta["cover"]
        elif cover_images and cover_mode == "hold":
            cover = cover_images[(idx - 1) % len(cover_images)]
        elif cover_mode == "slideshow" and cover_images:
            cover = None  # handled via schedule below
        else:
            cover = default_cover or (input_dir / "cover.jpg")

        if cover is None:
            # Slideshow mode for this episode
            dur = get_duration(src)
            schedule = _slideshow_schedule(covers_cfg, input_dir, config_dir, dur)
            img_concat = tmp_dir / f"pod_{idx:02d}_images.txt"
            _write_image_concat(schedule, img_concat)
            run_ffmpeg(
                "-f", "concat", "-safe", "0", "-i", img_concat,
                "-i", src,
                "-vf", SCALE,
                "-c:v", "libx264", "-tune", "stillimage",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest", out_path,
            )
        else:
            run_ffmpeg(
                "-loop", "1", "-i", cover,
                "-i", src,
                "-vf", SCALE,
                "-c:v", "libx264", "-tune", "stillimage",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest", out_path,
            )

        print(f"  {src.name} → {out_name}")

    _cleanup_intermediates(output_dir)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _cleanup_intermediates(output_dir):
    """Remove intermediate files produced during a run, keeping only final outputs."""
    import shutil
    working = output_dir / "working"
    if working.exists():
        shutil.rmtree(working)
    for pattern in ("disc*_tracks.txt", "disc*_metadata.txt"):
        for f in output_dir.glob(pattern):
            f.unlink()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Convert ripped CD albums to YouTube-ready MP4s with chapter markers."
    )
    p.add_argument("--config", required=True, metavar="FILE",
                   help="Album config YAML file")

    g = p.add_argument_group("Input/output")
    g.add_argument("--input", metavar="DIR",
                   help="Folder containing MP3 files")
    g.add_argument("--output", metavar="DIR",
                   help="Folder for generated files (default: same as YAML)")
    g.add_argument("--cover", metavar="FILE",
                   help="Cover image (default: cover.jpg in input folder)")

    g = p.add_argument_group("Pipeline")
    g.add_argument("--steps", default="all",
                   help="rename,chapters,mp4,all (default: all)")
    g.add_argument("--discs", metavar="N[,N]",
                   help="Comma-separated disc numbers to process (default: all)")
    g.add_argument("--tracks", metavar="N", type=int,
                   help="Process only the first N tracks per disc")
    g.add_argument("--force-rename", action="store_true",
                   help="Rename files even if already correctly named")
    g.add_argument("--dry-run", action="store_true",
                   help="(rename step) Show what would be renamed without making changes")
    g.add_argument("--no-title-dash", action="store_true",
                   help="Use a space instead of dash between track number and title")
    g.add_argument("--number-outputs", action="store_true",
                   help="(podcast) Prefix output filenames with a sequence number")

    args = p.parse_args()

    cfg = load_config(args.config)
    input_dir, output_dir, default_cover = resolve_io(
        cfg, args.input, args.output, args.cover
    )

    steps_raw = [s.strip() for s in args.steps.split(",")]
    steps = ["rename", "chapters", "mp4"] if "all" in steps_raw else steps_raw

    discs_filter = None
    if args.discs:
        discs_filter = {int(d) for d in args.discs.split(",")}

    if cfg.get("mode") == "podcast":
        run_podcast(cfg, input_dir, output_dir, default_cover, args.number_outputs,
                    args.tracks)
        return

    structure = detect_structure(cfg, input_dir)
    print(f"Structure: {structure}")
    disc_folders = resolve_disc_folders(cfg, input_dir, structure)

    if "rename" in steps:
        step_rename(cfg, disc_folders, structure, discs_filter,
                    args.force_rename, args.no_title_dash, args.dry_run)

    if "chapters" in steps:
        step_chapters(cfg, disc_folders, structure, output_dir,
                      discs_filter, args.tracks)

    if "mp4" in steps:
        step_mp4(cfg, disc_folders, structure, output_dir, default_cover,
                 discs_filter, args.tracks)
        _cleanup_intermediates(output_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
