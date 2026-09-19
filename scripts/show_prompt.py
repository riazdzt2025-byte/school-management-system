#!/usr/bin/env python3
"""Print one session prompt (plus its START block) ready to copy/paste.

Examples
--------
    python3 scripts/show_prompt.py                 # list all 28 prompts
    python3 scripts/show_prompt.py 4               # START block + full prompt 04
    python3 scripts/show_prompt.py 04 --start-only # only the START block
    python3 scripts/show_prompt.py EX-03           # by session id
    python3 scripts/show_prompt.py gpa             # by keyword in the title
    python3 scripts/show_prompt.py 4 --out /tmp/p4.txt

Why: an agent (or you) can answer "give me prompt N" in one step — no searching.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPTS_DIR = HERE.parent / "docs" / "prompts"
BN2ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def parse(path: Path) -> dict:
    first = path.read_text(encoding="utf-8").split("\n")[0]
    m = re.match(r"^#\s+প্রম্পট\s+([০-৯\d]+)\s*/\s*([০-৯\d]+)\s*—\s*সেশন\s+(\S+)\s*·\s*(.+)$", first)
    if not m:
        return {}
    return {"num": int(m.group(1).translate(BN2ASCII)),
            "total": int(m.group(2).translate(BN2ASCII)),
            "sid": m.group(3),
            "title": m.group(4).strip(),
            "path": path}


def all_prompts() -> list[dict]:
    items = []
    for p in sorted(PROMPTS_DIR.glob("prompt-*.md")):
        parsed = parse(p)
        if parsed:
            items.append(parsed)
    return sorted(items, key=lambda x: x["num"])


def resolve(query: str, items: list[dict]) -> dict:
    q = query.strip()
    if re.fullmatch(r"[০-৯\d]+", q):
        num = int(q.translate(BN2ASCII))
        for it in items:
            if it["num"] == num:
                return it
        sys.exit(f"প্রম্পট {num} নেই — ০১…{len(items):02d} এর মধ্যে দিন।")
    for it in items:
        if it["sid"].lower() == q.lower():
            return it
    hits = [it for it in items if q.lower() in it["title"].lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        print(f"'{q}' একাধিক প্রম্পটে মিলেছে: " +
              ", ".join(f"{h['num']:02d} ({h['sid']})" for h in hits), file=sys.stderr)
    sys.exit(f"'{q}' দিয়ে কিছু পাওয়া গেল না — `python3 scripts/show_prompt.py` চালিয়ে তালিকা দেখুন।")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", help="নম্বর (৪/০৪), সেশন আইডি (EX-03), বা শিরোনামের শব্দ")
    ap.add_argument("--start-only", action="store_true", help="শুধু START-ব্লক")
    ap.add_argument("--prompt-only", action="store_true", help="শুধু প্রম্পট")
    ap.add_argument("--out", help="প্রিন্ট না করে এই ফাইলে লিখুন")
    args = ap.parse_args()

    items = all_prompts()
    if not items:
        sys.exit(f"{PROMPTS_DIR} খালি — repo-র সঠিক ফোল্ডারে চালান।")

    if not args.query:
        print("প্রম্পট তালিকা (২৮):\n")
        for it in items:
            print(f"  {it['num']:02d}  {it['sid']:<6} {it['title'][:64]:<64} {it['path'].name}")
        print("\nব্যবহার: python3 scripts/show_prompt.py 4   (বা EX-03 / gpa)")
        return

    item = resolve(args.query, items)
    kick = PROMPTS_DIR / "copy-paste" / "kickoff" / f"prompt-{item['num']:02d}-START.txt"
    body = item["path"].read_text(encoding="utf-8")

    chunks = []
    if not args.prompt_only:
        if kick.exists():
            chunks.append("# ===== START-ব্লক (নতুন সেশনে আগে এটি পেস্ট করুন) =====\n\n"
                          + kick.read_text(encoding="utf-8").rstrip() + "\n")
        else:
            chunks.append("⚠️ START-ব্লক নেই — `python3 scripts/build_prompt_exports.py --variants txt` চালান।\n")
    if not args.start_only:
        chunks.append("# ===== প্রম্পট "
                      f"{item['num']:02d} / {item['total']:02d} — সেশন {item['sid']} =====\n\n"
                      + body.rstrip() + "\n")
    text = "\n".join(chunks)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"লেখা হলো: {args.out} ({len(text)} অক্ষর) — এখান থেকে কপি করুন।")
    else:
        print(text)


if __name__ == "__main__":
    main()
