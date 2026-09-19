#!/usr/bin/env bash
# Download just the docs/prompts bundle from GitHub — works with or without git.
#
#   bash scripts/fetch_prompts.sh                      # branch default → ./prompts-bundle
#   bash scripts/fetch_prompts.sh main out             # অন্য branch / অন্য destination
#   bash scripts/fetch_prompts.sh <branch> <dest> --repo owner/name
#
# নোট: টার্গেট branch এখনো main-এ merge না হলে এই default branch থেকেই নামবে (PR #34 merge হলে main দিলেও চলবে)।
set -euo pipefail

REPO="riazdzt2025-byte/school-management-system"
BRANCH="arena/01a0b7f7-school-management-system"
DEST="prompts-bundle"

args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --repo=*) REPO="${1#*=}"; shift ;;
    *) args+=("$1"); shift ;;
  esac
done
[ "${#args[@]}" -gt 0 ] && BRANCH="${args[0]}"
[ "${#args[@]}" -gt 1 ] && DEST="${args[1]}"

command -v curl >/dev/null 2>&1 || { echo "curl দরকার (অথবা ব্রাউজার থেকে ZIP নামান: https://github.com/$REPO/archive/refs/heads/$BRANCH.zip)"; exit 1; }
command -v tar  >/dev/null 2>&1 || { echo "tar দরকার"; exit 1; }

URL="https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "⬇  নামানো হচ্ছে: $REPO @ $BRANCH"
if ! curl -fsSL "$URL" -o "$TMP/repo.tar.gz"; then
  echo "❌ ডাউনলোড ব্যর্থ। branch-এর নাম ঠিক আছে? (হার্ড-লিংক: https://github.com/$REPO/archive/refs/heads/$BRANCH.zip)"
  exit 1
fi

mkdir -p "$DEST"
# archive-এর ভেতরে প্রথম folder: repo-branch/ — strip করে docs/prompts বের করা হচ্ছে
if ! tar -xzf "$TMP/repo.tar.gz" -C "$TMP" ; then
  echo "❌ tar খুলতে ব্যর্থ"; exit 1
fi
SRC="$(find "$TMP" -maxdepth 1 -mindepth 1 -type d | head -1)/docs/prompts"
if [ ! -d "$SRC" ]; then
  echo "❌ archive-এ docs/prompts নেই — branch ঠিক আছে কি?"; exit 1
fi
rm -rf "$DEST/docs"
mkdir -p "$DEST/docs"
cp -R "$SRC" "$DEST/docs/prompts"

count_md=$(find "$DEST/docs/prompts" -name 'prompt-*.md' | wc -l | tr -d ' ')
count_txt=$(find "$DEST/docs/prompts/copy-paste" -name '*.txt' 2>/dev/null | wc -l | tr -d ' ')
count_docx=$(find "$DEST/docs/prompts/export/docx" -name '*.docx' 2>/dev/null | wc -l | tr -d ' ')

echo "✅ নামানো হলো: $DEST/docs/prompts"
echo "   · প্রম্পট (md): $count_md টি"
echo "   · কপি-পেস্ট (txt): $count_txt টি (kickoff/ সহ)"
echo "   · Word (docx): $count_docx টি"
echo "   · PDF: $DEST/docs/prompts/export/School-Prompts-28-BN.pdf"
echo
echo "শুরু করার দুটি জিনিস:"
echo "  1) $DEST/docs/prompts/copy-paste/kickoff/prompt-01-START.txt"
echo "  2) $DEST/docs/prompts/copy-paste/prompt-01-session-00-baseline.txt"
echo "ledger (কোন প্রম্পট শেষ): $DEST/docs/prompts/PROGRESS.md"
