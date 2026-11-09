# Scans files (including inside .xlsx/.docx zips) for strings that must not be published.
# Usage: python leak_scan.py <folder> word1 word2 ...   (exit code 1 if anything is found)
import sys
import zipfile
from pathlib import Path

root, words = Path(sys.argv[1]), sys.argv[2:]
needles = [(w, w.encode(enc)) for w in words for enc in ("utf-8", "utf-16-le")]
found = []
for p in sorted(root.rglob("*")):
    if not p.is_file() or ".git" in p.parts:
        continue
    blobs = [p.read_bytes()]
    if p.suffix in (".xlsx", ".docx", ".pptx"):
        with zipfile.ZipFile(p) as z:
            blobs = [z.read(n) for n in z.namelist()]
    hits = sorted({w for w, n in needles for b in blobs if n.lower() in b.lower()})
    if hits:
        found.append(f"{p.relative_to(root)}: {hits}")
print("\n".join(found) or "clean")
sys.exit(1 if found else 0)
