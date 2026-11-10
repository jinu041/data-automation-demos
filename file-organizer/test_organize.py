# Builds a messy folder in a temp dir, then checks the dry run, --apply and --undo end to end.
# Run: python test_organize.py
import contextlib
import csv
import datetime as dt
import io
import os
import tempfile
from pathlib import Path

import organize

FILES = {  # path: (content, modified date)
    "photo.jpg": (b"IMG-A", "2026-03-15"),
    "photo copy.JPG": (b"IMG-A", "2026-04-01"),       # same bytes as photo.jpg, newer -> set aside
    "report.pdf": (b"PDF-1", "2026-03-20"),
    "sub/report.pdf": (b"PDF-2", "2026-03-25"),       # same name, different file -> "report (2).pdf"
    "notes.txt": (b"TXT", "2026-03-21"),              # "notes.txt" already exists in the target
    "보고서.hwp": ("한글".encode(), "2026-05-02"),
    "data.xlsx": (b"XLSX", "2026-05-03"),
    "song.mp3": (b"MP3", "2026-06-01"),
    "unknown.xyz": (b"???", "2026-06-02"),
    ".hidden": (b"H", "2026-06-03"),                  # skipped
    ".git/config": (b"GIT", "2026-06-04"),            # inside a hidden folder: skipped even with --recursive
}
EXPECTED = {
    "photo.jpg": "Images/2026-03/photo.jpg",
    "photo copy.JPG": "_duplicates/photo copy.JPG",
    "report.pdf": "Documents/2026-03/report.pdf",
    "sub/report.pdf": "Documents/2026-03/report (2).pdf",
    "notes.txt": "Documents/2026-03/notes (2).txt",
    "보고서.hwp": "Documents/2026-05/보고서.hwp",
    "data.xlsx": "Spreadsheets/2026-05/data.xlsx",
    "song.mp3": "Audio/2026-06/song.mp3",
    "unknown.xyz": "Other/2026-06/unknown.xyz",
}


def run(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        organize.main([str(a) for a in args])
    return out.getvalue()


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


with tempfile.TemporaryDirectory() as tmp:
    src, dest = Path(tmp) / "Downloads", Path(tmp) / "Sorted"
    for rel, (data, day) in FILES.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        t = dt.datetime.fromisoformat(day + "T12:00").timestamp()
        os.utime(p, (t, t))
    old = dest / "Documents/2026-03/notes.txt"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"OLD")
    before_src, before_dest = snapshot(src), snapshot(dest)

    out = run(src, "--dest", dest, "--recursive")
    assert "dry run: nothing moved" in out and "9 files:" in out, out
    assert snapshot(src) == before_src and snapshot(dest) == before_dest, "dry run must not move anything"

    out = run(src, "--dest", dest, "--recursive", "--apply")
    after = snapshot(dest)
    for rel, target in EXPECTED.items():
        assert after.get(target) == FILES[rel][0], (rel, target, sorted(after))
    assert after["Documents/2026-03/notes.txt"] == b"OLD", "an existing file must never be overwritten"
    assert set(snapshot(src)) == {".hidden", ".git/config"}, snapshot(src)
    logs = list(dest.glob("_organize_log_*.csv"))
    assert len(logs) == 1
    with open(logs[0], newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 9 and [r["duplicate"] for r in rows].count("yes") == 1

    out = run("--undo", logs[0])
    assert "undone: 9 files" in out, out
    assert snapshot(src) == before_src, "every file must be back with its original content"
    left = {p.relative_to(dest).as_posix() for p in dest.rglob("*")}
    assert left == {"Documents", "Documents/2026-03", "Documents/2026-03/notes.txt", logs[0].name}, left

    # Two runs in the same second must not share (and overwrite) one undo log
    first = organize.apply([], dest)
    first.write_text("from,to,duplicate\nkeep,me,\n", encoding="utf-8-sig")
    second = organize.apply([], dest)
    assert second != first and "keep,me" in first.read_text(encoding="utf-8-sig"), (first, second)

print("all checks passed: dry run, apply (types, months, duplicates, name clashes, Korean names), undo")
