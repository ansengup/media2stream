#!/usr/bin/env python3
"""
fix_echoes_renames.py — Undo bad renames in Echoes of the Eternal.

The incorrect renames happened because the glob pattern `D-T*.mp3` (e.g. `1-1*.mp3`)
matched two-digit track files (1-10, 1-11 ...) before single-digit ones, causing
track 10/20/30/40 to be renamed with track 1/2/3/4 titles and ID3 tags.

Run with --dry-run first to preview changes, then without to apply.
"""

import sys
from pathlib import Path

from mutagen.id3 import ID3, TIT2, ID3NoHeaderError

FOLDER = Path(
    "/Users/ansengup/Music/Music/Media.localized/Music/"
    "Swami Chetanananda/Echoes of the Eternal"
)

# (current_wrong_name, correct_name, correct_id3_title)
FIXES = [
    # Disc 1 — tracks 10 / 20 / 30 / 40 got track 1/2/3/4 names
    (
        "1-01-Madhu vata ritayate.mp3",
        "1-10-Vratena diksham apnoti.mp3",
        "Vratena diksham apnoti",
    ),
    (
        "1-02-Tejo asi tejo mayi dhehi.mp3",
        "1-20-Apanipado javano grahita.mp3",
        "Apanipado javano grahita",
    ),
    (
        "1-03-Namah paryaya chavaryaya cha.mp3",
        "1-30-Iyam prithivi sarvesham bhutanam madhu.mp3",
        "Iyam prithivi sarvesham bhutanam madhu",
    ),
    (
        "1-04-Trayambakam yajamahe sugandhim.mp3",
        "1-40-Satyena vayu ravati.mp3",
        "Satyena vayu ravati",
    ),
    # Disc 2 — tracks 10 / 20 got track 1/2 names
    (
        "2-01-Anando Brahmeti vyajanat.mp3",
        "2-10-Gavam sarvam gajakshiram.mp3",
        "Gavam sarvam gajakshiram",
    ),
    (
        "2-02-Raso vai sah.mp3",
        "2-20-Tvam shrih tvam ishvari.mp3",
        "Tvam shrih tvam ishvari",
    ),
    # Disc 3 — tracks 10 / 20 got track 1/2 names
    (
        "3-01-Asato ma sad gamaya.mp3",
        "3-10-Janami dharmam na cha me.mp3",
        "Janami dharmam na cha me",
    ),
    (
        "3-02-Dhairyam yasya pita.mp3",
        "3-20-Hiranmayena patrena.mp3",
        "Hiranmayena patrena",
    ),
]


def update_id3_title(path, title):
    try:
        tags = ID3(str(path))
    except ID3NoHeaderError:
        tags = ID3()
    tags["TIT2"] = TIT2(encoding=3, text=title)
    tags.save(str(path))


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no files will be changed\n")

    errors = 0
    for wrong_name, correct_name, correct_title in FIXES:
        src = FOLDER / wrong_name
        dst = FOLDER / correct_name

        if not src.exists():
            print(f"SKIP  not found: {wrong_name}")
            continue

        if dst.exists():
            print(f"WARN  destination already exists, skipping: {correct_name}")
            errors += 1
            continue

        if dry_run:
            print(f"would rename  {wrong_name}")
            print(f"           →  {correct_name}  [ID3: {correct_title}]")
        else:
            src.rename(dst)
            update_id3_title(dst, correct_title)
            print(f"fixed  {wrong_name}")
            print(f"    →  {correct_name}  [ID3: {correct_title}]")

    if not dry_run:
        print("\nNote: original tracks 1–9 for each affected disc are still missing —")
        print("they were not found by the rename tool and were not affected by this fix.")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
