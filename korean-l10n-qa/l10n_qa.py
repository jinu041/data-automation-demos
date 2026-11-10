# Korean localization QA: checks an English -> Korean string table before it ships.
# Standard library only.
#   python l10n_qa.py sample/strings.csv --glossary sample/glossary.csv --out report.csv
#   python l10n_qa.py --selftest
import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
# {name}, {0}, %s, %1$d, <b>, </b>
PLACEHOLDER = re.compile(r"\{[^{}]*\}|%(?:\d+\$)?[sdif]|</?[A-Za-z][^<>]*>")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# A Korean particle glued to a placeholder. Its right form depends on the word that gets inserted
# (whether it ends in a final consonant), so "{name}이" is wrong for half the names.
PARTICLE = re.compile(r"(\{[^{}]*\}|%(?:\d+\$)?[sdif])(은|는|이|가|을|를|과|와)(?![(가-힣])")
PAIR = {"은": "은(는)", "는": "은(는)", "이": "이(가)", "가": "이(가)",
        "을": "을(를)", "를": "을(를)", "과": "과(와)", "와": "과(와)"}


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def tokens(pattern, s):
    return sorted(pattern.findall(s))


def check(rows, glossary):
    """Returns (key, check, detail) for every problem found. rows: dicts with key, en, ko and optional max_len."""
    issues = []
    variants = defaultdict(set)
    for r in rows:
        key, en, ko = r["key"], r["en"], r.get("ko") or ""
        if not ko.strip():
            issues.append((key, "missing", "no Korean text"))
            continue
        variants[en.strip().lower()].add(ko.strip())
        if ko.strip() == en.strip():
            issues.append((key, "untranslated", "the Korean is the English source"))
        if tokens(PLACEHOLDER, en) != tokens(PLACEHOLDER, ko):
            issues.append((key, "placeholder", f"en {tokens(PLACEHOLDER, en)} / ko {tokens(PLACEHOLDER, ko)}"))
        plain_en, plain_ko = PLACEHOLDER.sub(" ", en), PLACEHOLDER.sub(" ", ko)
        if tokens(NUMBER, plain_en) != tokens(NUMBER, plain_ko):
            issues.append((key, "number", f"en {tokens(NUMBER, plain_en)} / ko {tokens(NUMBER, plain_ko)}"))
        limit = (r.get("max_len") or "").strip()
        if limit and len(ko) > int(limit):
            issues.append((key, "too_long", f"{len(ko)} characters, the UI fits {limit}"))
        if ko != ko.strip() or "  " in ko:
            issues.append((key, "spacing", "leading, trailing or double space"))
        for m in PARTICLE.finditer(ko):
            issues.append((key, "particle", f"{m.group(0)}: write {m.group(1)}{PAIR[m.group(2)]} or rephrase; "
                                           "the right form depends on the inserted word"))
        for term_en, term_ko in glossary:
            if re.search(rf"\b{re.escape(term_en)}(?:s|es)?\b", plain_en, re.I) and term_ko not in ko:
                issues.append((key, "glossary", f"'{term_en}' is '{term_ko}' in the glossary"))
    for r in rows:
        found = variants.get(r["en"].strip().lower(), set())
        if len(found) > 1:
            issues.append((r["key"], "inconsistent", "same English, different Korean: " + " / ".join(sorted(found))))
    return issues


def summary(issues):
    counts = Counter(kind for _, kind, _ in issues)
    keys = {key for key, _, _ in issues}
    return f"{len(issues)} issues in {len(keys)} strings: " + ", ".join(f"{k} {n}" for k, n in counts.most_common())


def write_report(issues, rows, path):
    by_key = {r["key"]: r for r in rows}
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel shows the Korean correctly
        w = csv.writer(f)
        w.writerow(["key", "check", "detail", "en", "ko"])
        for key, kind, detail in issues:
            w.writerow([key, kind, detail, by_key[key]["en"], by_key[key].get("ko") or ""])


EXPECTED = {  # what the sample is built to contain, one problem of each kind
    "resv.title": {"glossary"}, "resv.confirm": {"particle"}, "resident.notice": {"glossary"},
    "maint.eta": {"number"}, "pay.amount": {"particle"}, "door.code": {"placeholder"},
    "settings.lang": {"untranslated"}, "home.title": {"inconsistent"}, "home.title2": {"inconsistent"},
    "help.long": {"too_long"}, "parking.guest": {"spacing"}, "visitor.log": {"missing"},
}


def selftest():
    assert tokens(PLACEHOLDER, "Hi {name}, %1$s <b>x</b>") == sorted(["{name}", "%1$s", "<b>", "</b>"])
    assert PARTICLE.search("{name}가 왔어요") and PARTICLE.search("%s를") and PARTICLE.search("{item}과")
    assert not PARTICLE.search("{n}이상") and not PARTICLE.search("{name}님이") and not PARTICLE.search("{n}개")
    assert tokens(NUMBER, "Pay 1,200 by the 3rd") == ["1,200", "3"]
    rows = read_csv(HERE / "sample" / "strings.csv")
    glossary = [(g["en"], g["ko"]) for g in read_csv(HERE / "sample" / "glossary.csv")]
    issues = check(rows, glossary)
    got = defaultdict(set)
    for key, kind, _ in issues:
        got[key].add(kind)
    assert dict(got) == EXPECTED, dict(got)
    clean = {r["key"] for r in rows} - set(EXPECTED)
    assert clean == {"home.welcome", "pkg.arrived", "pkg.count", "resv.cancel", "maint.request", "pay.due"}, clean
    print("selftest ok:", summary(issues))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check an English -> Korean string table (CSV: key,en,ko[,max_len]).")
    ap.add_argument("strings", nargs="?", type=Path)
    ap.add_argument("--glossary", type=Path, help="CSV with en,ko columns: approved Korean for each English term")
    ap.add_argument("--out", type=Path, default=Path("l10n_report.csv"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.strings:
        ap.error("give a strings CSV, or --selftest")
    rows = read_csv(a.strings)
    glossary = [(g["en"], g["ko"]) for g in read_csv(a.glossary)] if a.glossary else []
    issues = check(rows, glossary)
    write_report(issues, rows, a.out)
    print(summary(issues) if issues else "no issues found")
    print("report:", a.out)
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
