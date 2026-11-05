#!/usr/bin/env bash
#
# প্রথম দিনের ল্যাব — এক কমান্ডে নিজের সিস্টেম চালু করা ও যাচাই করা।
#
# ব্যবহার (রিপোর রুট থেকে):
#     bash scripts/lab_day1.sh
#
# যা করে (ধাপে ধাপে, প্রতিটি ধাপের ফল দেখায়):
#   ১. Python সংস্করণ দেখে প্রয়োজনীয় প্যাকেজ ইনস্টল করে (.venv তৈরি করে)
#   ২. Django-র নিজের সিস্টেম চেক চালায়
#   ৩. ডেটাবেস তৈরি/হালনাগাদ করে (migrate)
#   ৪. খালি ডেটাবেস হলে ৬টি প্রতিষ্ঠানের ফিক্সচার লোড করে
#   ৫. একটি ছোট টেস্ট ফাইল চালিয়ে দেখায় সব সবুজ
#   ৬. এরপর কী করবেন তা ছাপে
#
# নিরাপত্তা: এটি শুধু লোকাল SQLite (db.sqlite3) নিয়ে কাজ করে।
# DATABASE_URL যদি sqlite ছাড়া অন্য কিছু হয়, স্ক্রিপ্ট কিছু না করেই থেমে যাবে।

set -u
cd "$(dirname "$0")/.." || { echo "রিপো ফোল্ডারে ঢোকা গেল না"; exit 1; }

bold(){ printf '\n\033[1m%s\033[0m\n' "$*"; }
ok(){   printf '  \033[32m✔\033[0m %s\n' "$*"; }
info(){ printf '    %s\n' "$*"; }
bad(){  printf '  \033[31m✘\033[0m %s\n' "$*"; }

bold "০) নিরাপত্তা যাচাই"
if [ -n "${DATABASE_URL:-}" ] && [ "${DATABASE_URL#sqlite}" = "$DATABASE_URL" ]; then
  bad "DATABASE_URL একটি বাইরের (non-SQLite) ডেটাবেস দেখাচ্ছে।"
  info "এই স্ক্রিপ্ট শুধু নিজের মেশিনের db.sqlite3 নিয়ে চলে — প্রোডাকশনে চালাবেন না।"
  info "চালাতে হলে: unset DATABASE_URL  (তারপর আবার চেষ্টা করুন)"
  exit 2
fi
ok "লোকাল SQLite — নিরাপদ"

PY="${PY:-python3}"
command -v "$PY" >/dev/null 2>&1 || { bad "python3 পাওয়া গেল না"; exit 3; }
PYVER="$($PY -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "0.0")"
bold "১) Python সংস্করণ: $PYVER"

# Django আগেই আছে কি না দেখা (যেমন Codespaces/devcontainer-এ)
if ! $PY -c 'import django' >/dev/null 2>&1; then
  if [ ! -d .venv ]; then
    info "ভার্চুয়াল এনভায়রনমেন্ট (.venv) তৈরি করছি…"
    "$PY" -m venv .venv || { bad "venv তৈরি হলো না (python3-venv ইনস্টল আছে?)"; exit 4; }
  fi
  # shellcheck disable=SC1091
  . .venv/bin/activate 2>/dev/null || . .venv/Scripts/activate 2>/dev/null || true
  PY="python"
fi

if $PY -c 'import django' >/dev/null 2>&1; then
  ok "Django আগেই ইনস্টল আছে — নতুন করে বসাতে হবে না"
else
  info "প্যাকেজ ইনস্টল করছি (এক-দুই মিনিট লাগতে পারে)…"
  "$PY" -m pip install --quiet --upgrade pip
  if $PY -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
    "$PY" -m pip install --quiet -r requirements.txt || { bad "requirements.txt ইনস্টল ব্যর্থ"; exit 5; }
    ok "requirements.txt থেকে ইনস্টল হয়েছে (Python $PYVER)"
  else
    info "Python $PYVER — Django ৬.১-এর জন্য ৩.১২+ দরকার, তাই Django ৫.২ দিয়ে চলছে (রিপোর README-তে এটা লেখা আছে)"
    "$PY" -m pip install --quiet "Django>=5.2,<6" openpyxl Pillow python-dotenv dj-database-url whitenoise \
      || { bad "প্যাকেজ ইনস্টল ব্যর্থ"; exit 5; }
    ok "Django ৫.২ + প্রয়োজনীয় প্যাকেজ ইনস্টল হয়েছে"
  fi
fi

mkdir -p staticfiles media   # WhiteNoise-এর অপ্রয়োজনীয় সতর্কবার্তা এড়াতে

bold "২) সিস্টেম চেক (Django নিজেই দেখে কোথাও ভুল আছে কি না)"
if $PY manage.py check; then ok "কোনো সমস্যা নেই (0 issues)"; else bad "check ব্যর্থ — উপরের মেসেজটি পড়ুন"; exit 6; fi

bold "৩) ডেটাবেস তৈরি / হালনাগাদ (migrate)"
if $PY manage.py migrate --noinput >/tmp/lab_day1_migrate.log 2>&1; then
  APPLIED="$(grep -c 'Applying' /tmp/lab_day1_migrate.log 2>/dev/null || true)"
  ok "মাইগ্রেশন সম্পন্ন (${APPLIED:-0}টি প্রয়োগ হয়েছে)"
else
  bad "migrate ব্যর্থ — /tmp/lab_day1_migrate.log দেখুন"; tail -5 /tmp/lab_day1_migrate.log; exit 7
fi

bold "৪) প্রতিষ্ঠানের তথ্য (fixture)"
COUNT="$($PY manage.py shell -c "from students.models import Institution; print('COUNT=%d' % Institution.objects.count())" 2>/dev/null | grep -o 'COUNT=[0-9]*' | tail -1 | cut -d= -f2)"
COUNT="${COUNT:-0}"
if [ "$COUNT" = "0" ]; then
  $PY manage.py loaddata students/fixtures/institutions.json >/dev/null 2>&1
  COUNT="$($PY manage.py shell -c "from students.models import Institution; print('COUNT=%d' % Institution.objects.count())" 2>/dev/null | grep -o 'COUNT=[0-9]*' | tail -1 | cut -d= -f2)"
  ok "ফিক্সচার লোড হয়েছে — প্রতিষ্ঠান: ${COUNT:-?}"
else
  ok "প্রতিষ্ঠান আগেই আছে: $COUNT — আবার লোড করলাম না (ডুপ্লিকেট হবে)"
fi

bold "৫) একটি টেস্ট ফাইল চালানো (দেখুন সব সবুজ হয় কি না)"
if $PY manage.py test students.test_navigation --verbosity 1; then
  ok "টেস্ট সবুজ — সিস্টেম ঠিকভাবে কাজ করছে"
else
  bad "টেস্ট ফেল করেছে — উপরের মেসেজটি কপি করে রাখুন"; exit 8
fi

bold "৬) হয়ে গেছে। এখন আপনি যা করতে পারেন:"
info "• সাইট চালু:      $PY manage.py runserver   →  তারপর http://127.0.0.1:8000/"
info "• অ্যাডমিন বানান:  $PY manage.py createsuperuser"
info "• পুরো টেস্ট স্যুট: $PY manage.py test students   (কয়েক মিনিট লাগবে)"
info "• পরের পাঠ:        docs/learning/labs-bn.html → Lab 2 (ORM) ও Lab 11 (ব্যাকআপ ড্রিল)"
printf '\n  \033[1mএই আউটপুটটুকু কপি করে এজেন্টকে পাঠান — পরের ধাপ সেটার উপরেই ঠিক করা হবে।\033[0m\n\n'
