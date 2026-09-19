#!/usr/bin/env python3
"""Generate docs/prompts/LINKS.md — direct links to every prompt (fast lookup).

Usage:  python3 scripts/prompt_links.py [--branch <branch>] [--repo owner/name]

Running from a machine that has no GitHub remote still works: pass --repo.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

BN2ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
KEYWORDS = {
    "০০": "baseline checkout verify",
    "EX-01": "import redirect analysis subtab",
    "EX-02": "roll order register result",
    "EX-03": "group mark evaluation setting",
    "EX-04": "higher math subject workflow",
    "EX-05": "absent fail missing marks",
    "EX-06": "gpa boost 4.90 5.00",
    "EX-07": "ctrl click correction shortcut",
    "OF-01": "guardian contact",
    "OF-02": "pagination 100",
    "OF-03": "subject assignment subtab office",
    "OF-04": "admission reports funnel",
    "OF-05": "student photo",
    "OF-06": "public success progress",
    "OF-07": "admission import integrity",
    "OF-08": "archive promotion certificate",
    "DB-01": "dashboard navigation",
    "DB-02": "developer branding",
    "DB-03": "permission data isolation",
    "DB-04": "settings ci",
    "DB-05": "backup tooling",
    "DB-06": "restore drill automation",
    "AT-01": "attendance entry correction",
    "AT-02": "attendance calendar report",
    "EM-01": "teacher assignment employee",
    "EM-02": "leave",
    "EM-03": "payroll control",
    "FN-01": "release verification",
}


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return ""


def parse(path: Path) -> dict:
    first = path.read_text(encoding="utf-8").split("\n")[0]
    m = re.match(r"^#\s+প্রম্পট\s+([০-৯\d]+)\s*/\s*([০-৯\d]+)\s*—\s*সেশন\s+(\S+)\s*·\s*(.+)$", first)
    if not m:
        sys.exit(f"cannot parse {path}")
    num = int(m.group(1).translate(BN2ASCII))
    return {"num": num, "total": int(m.group(2).translate(BN2ASCII)),
            "sid": m.group(3), "title": m.group(4).strip(), "path": path}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default=git("branch", "--show-current") or "main")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--prompts-dir", default="docs/prompts")
    args = ap.parse_args()

    repo = args.repo
    if not repo:
        url = git("remote", "get-url", "origin")
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
        if not m:
            sys.exit("cannot detect the GitHub repo — pass --repo owner/name")
        repo = m.group(1)
    branch = args.branch
    root = Path(args.prompts_dir)

    prompts = sorted((parse(p) for p in root.glob("prompt-*.md")), key=lambda p: p["num"])
    base_blob = f"https://github.com/{repo}/blob/{branch}/{root.as_posix()}"
    base_raw = f"https://raw.githubusercontent.com/{repo}/{branch}/{root.as_posix()}"

    rows, key_rows = [], []
    for p in prompts:
        slug = p["path"].stem
        md = f"{base_blob}/{slug}.md"
        txt = f"{base_blob}/copy-paste/{slug}.txt"
        kick = f"{base_blob}/copy-paste/kickoff/prompt-{p['num']:02d}-START.txt"
        docx = f"{base_blob}/export/docx/{slug}.docx"
        rows.append(f"| {p['num']:02d} | {p['sid']} | {p['title']} | [📄 md]({md}) · "
                    f"[📋 কপি-টেক্সট]({txt}) · [⬇ raw]({base_raw}/copy-paste/{slug}.txt) · "
                    f"[▶ START]({kick}) · [📝 Word]({docx}) |")
        kw = KEYWORDS.get(p["sid"], "")
        key_rows.append(f"| `{p['sid']}` | **{p['num']:02d}** | {kw} | {p['title']} |")

    repo_blob = f"https://github.com/{repo}/blob/{branch}/docs/prompts"
    doc = f"""# LINKS — ২৮টি প্রম্পট (দ্রুত খোঁজার তালিকা)

_repo: `{repo}` · branch: `{branch}` · এই ফাইল তৈরি করে `scripts/prompt_links.py`_

> **দ্রুততম ব্যবহার:** এজেন্টকে বলুন — **“প্রম্পট ০৪ দাও”** (বা `prompt-04`, `EX-03`, `GPA`)।
> এজেন্ট এই ফাইল পড়ে এক ধাপেই সঠিক প্রম্পট + তার START-ব্লক বের করতে পারবে।
> মানুষের জন্য: নিচের টেবিল থেকে সোজা লিংকে ক্লিক করুন।

## ১. সব প্রম্পট এক নজরে (ক্লিকযোগ্য)

| # | সেশন | শিরোনাম | লিংক |
|---|------|---------|------|
{chr(10).join(rows)}

## ২. শব্দ/সেশন ধরে খোঁজা (নম্বর মনে না থাকলে)

| সেশন | # | খুঁজতে শব্দ | শিরোনাম |
|------|---|-------------|---------|
{chr(10).join(key_rows)}

## ৩. বড় ফাইল (একসাথে সব)

| কী | লিংক |
|---|---|
| কপি-পেস্ট (সব ২৮টি, প্লেইন টেক্সট) | [ALL_PROMPTS.txt]({base_blob}/copy-paste/ALL_PROMPTS.txt) · [⬇ raw]({base_raw}/copy-paste/ALL_PROMPTS.txt) |
| কপি-পেস্ট (Markdown, সব) | [ALL_PROMPTS.md]({base_blob}/ALL_PROMPTS.md) |
| **PDF** (কভার + সূচি + ২৮টি, ৮৯ পৃষ্ঠা) | [School-Prompts-28-BN.pdf]({base_blob}/export/School-Prompts-28-BN.pdf) |
| Word (সব একসাথে) | [School-Prompts-28-BN.docx]({base_blob}/export/School-Prompts-28-BN.docx) |
| START-গাইড (নতুন সেশন) | [HANDOFF-START.md]({base_blob}/HANDOFF-START.md) |
| কোন প্রম্পট চলছে/শেষ (ledger) | [PROGRESS.md]({base_blob}/PROGRESS.md) |
| ব্যবহারবিধি ও owner-সিদ্ধান্ত | [README.md]({repo_blob}/README.md) |

## ৪. টার্মিনাল/এজেন্ট থেকে (লিংক ছাড়াও দ্রুত)

```bash
python3 scripts/show_prompt.py            # ২৮টির তালিকা (নম্বর · সেশন · ফাইল)
python3 scripts/show_prompt.py 4          # START-ব্লক + পুরো প্রম্পট ০৪ (কপি-রেডি)
python3 scripts/show_prompt.py EX-03      # সেশন আইডি দিয়ে
python3 scripts/show_prompt.py gpa        # শিরোনামে শব্দ দিয়ে
python3 scripts/show_prompt.py 4 --start-only   # শুধু START-ব্লক
python3 scripts/show_prompt.py 4 --out /tmp/p4.txt   # ফাইলে লিখে দেয়
```

> **কপি করার সহজ পথ:** `কপি-টেক্সট` / `raw` লিংকটা সাদা টেক্সট — খুলে Ctrl+A → Ctrl+C করলেই পুরো প্রম্পট কপি হয়ে যায়।
> (⚠️ `raw.githubusercontent.com` কিছু নেটওয়ার্কে ব্লক থাকতে পারে; তখন `📄 md` বা `📋 কপি-টেক্সট` লিংকটি ব্যবহার করুন।)

## ৫. লিংক ঠিক রাখা

- এই তালিকার লিংকগুলোর branch হলো **`{branch}`**। owner PR merge করার পরে সব লিংক স্থায়ী করতে:
  `python3 scripts/prompt_links.py --branch main`
  (তখন `docs/prompts/LINKS.md`-এ `main` লিংক বসবে, যা চিরস্থায়ী।)
- নতুন প্রম্পট যোগ/নাম বদল হলে আবার একই কমান্ড চালালেই তালিকা হালনাগাদ হয় — হাতে লিংক এডিট করতে হয় না।
"""
    out = root / "LINKS.md"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out} ({len(prompts)} prompts, branch={branch})")


if __name__ == "__main__":
    main()
