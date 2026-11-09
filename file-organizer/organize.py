# Sorts a messy folder into <type>/<YYYY-MM>/ folders, sets exact duplicates aside and writes an undo log.
# Standard library only. Nothing is ever deleted, and nothing moves until you add --apply.
#   python organize.py Downloads --dest Sorted              # dry run: prints the plan
#   python organize.py Downloads --dest Sorted --apply      # moves files, writes Sorted/_organize_log_<time>.csv
#   python organize.py --undo Sorted/_organize_log_<time>.csv
import argparse
import csv
import datetime as dt
import hashlib
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

TYPES = {
    "Images": "jpg jpeg png gif webp heic bmp tif tiff svg",
    "Documents": "pdf doc docx hwp hwpx txt md rtf odt",
    "Spreadsheets": "xls xlsx xlsm csv ods",
    "Presentations": "ppt pptx key odp",
    "Archives": "zip rar 7z tar gz",
    "Audio": "mp3 wav m4a flac aac ogg",
    "Video": "mp4 mov avi mkv webm",
    "Code": "py js ts html css json java cpp c h sql ps1 sh",
}
EXT = {e: kind for kind, exts in TYPES.items() for e in exts.split()}
DUPES = "_duplicates"


def kind(path):
    return EXT.get(path.suffix.lower().lstrip("."), "Other")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def free_name(target, taken):
    """target, or 'name (2).ext', 'name (3).ext' ... if that path exists or is already planned."""
    n, cand = 2, target
    while cand.exists() or cand in taken:
        cand = target.with_name(f"{target.stem} ({n}){target.suffix}")
        n += 1
    return cand


def plan(src, dest, by, recursive):
    files = sorted((p for p in (src.rglob("*") if recursive else src.iterdir())
                    if p.is_file() and not p.name.startswith(".") and dest not in p.parents),
                   key=lambda p: (p.stat().st_mtime, str(p)))  # oldest first, so the oldest copy is the one kept
    moves, seen, taken = [], set(), set()
    for p in files:
        digest = sha256(p)
        dup = digest in seen  # same bytes as a file already planned: keep the first, set this one aside
        seen.add(digest)
        month = dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m")
        folder = dest / (DUPES if dup else {"type": kind(p), "month": month, "type-month": f"{kind(p)}/{month}"}[by])
        target = free_name(folder / p.name, taken)
        taken.add(target)
        moves.append((p, target, dup))
    return moves


def apply(moves, dest):
    dest.mkdir(parents=True, exist_ok=True)
    log = dest / f"_organize_log_{dt.datetime.now():%Y%m%d-%H%M%S}.csv"
    with open(log, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["from", "to", "duplicate"])
        for src, dst, dup in moves:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            w.writerow([src, dst, "yes" if dup else ""])
            f.flush()  # the log stays complete even if a later move fails
    return log


def undo(log):
    with open(log, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    clash = [r["from"] for r in rows if Path(r["from"]).exists()]
    if clash:
        sys.exit(f"undo stopped, these original paths are taken again: {clash[:5]}")
    for r in reversed(rows):
        Path(r["from"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(r["to"], r["from"])
    home = Path(log).resolve().parent
    for d in sorted({Path(r["to"]).parent for r in rows}, key=lambda p: len(p.parts), reverse=True):
        while d != home and home in d.parents and d.exists() and not any(d.iterdir()):
            d.rmdir()  # only folders this run created and left empty
            d = d.parent
    print(f"undone: {len(rows)} files moved back")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sort files into folders by type and month. Dry run unless --apply.")
    ap.add_argument("src", nargs="?", type=Path)
    ap.add_argument("--dest", type=Path, help="target folder (default: <src>/Sorted)")
    ap.add_argument("--by", choices=["type", "month", "type-month"], default="type-month")
    ap.add_argument("--recursive", action="store_true", help="also take files from subfolders")
    ap.add_argument("--apply", action="store_true", help="move the files (otherwise just print the plan)")
    ap.add_argument("--undo", type=Path, metavar="LOG")
    a = ap.parse_args(argv)
    if a.undo:
        return undo(a.undo)
    if not a.src or not a.src.is_dir():
        ap.error("give a folder to sort")
    src = a.src.resolve()
    dest = (a.dest or src / "Sorted").resolve()
    moves = plan(src, dest, a.by, a.recursive)
    for s, d, dup in moves:
        print(f"{'DUP ' if dup else ''}{s.relative_to(src)} -> {d.relative_to(dest)}")
    counts = Counter("duplicates" if dup else d.relative_to(dest).parts[0] for _, d, dup in moves)
    print(f"{len(moves)} files: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    if not a.apply:
        print("dry run: nothing moved. Add --apply to move the files.")
        return
    log = apply(moves, dest)
    try:
        log = os.path.relpath(log)
    except ValueError:  # log on another drive (Windows): keep the full path
        pass
    print(f"moved {len(moves)} files. Undo with: python organize.py --undo \"{log}\"")


if __name__ == "__main__":
    main()
