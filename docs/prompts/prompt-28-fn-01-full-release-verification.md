# প্রম্পট ২৮ / ২৮ — সেশন FN-01 · পুরো release পরীক্ষা ও নির্দেশিকা

_বিভাগ: সমাপনী · ধরন: যাচাই · নির্ভরতা: প্রম্পট ০১–২৭ (সব)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ২৮ / ২৮ (prompt 28/28) — সেশন FN-01 · যাচাই · বিভাগ: সমাপনী
   পূর্ববর্তী: প্রম্পট ২৭ / ২৮ (EM-03 — Payroll controls) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট — / ২৮ (—)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ২৮ / ২৮ (prompt 28/28) — সেশন FN-01 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট — / ২৮ (—) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- এটি চূড়ান্ত সেশন: প্রথম production release-এর আগে সম্পূর্ণ যাচাই + owner-এর জন্য ধাপে ধাপে নির্দেশিকা।
- আগের ২৭টি সেশনের ফলাফল, doc আপডেট ও `docs/prompts/PROGRESS.md` ledger এখন প্রমাণের মূল ভিত্তি — তবে **প্রতিটি দাবি নিজে যাচাই করবে**, ledger-কে সত্য ধরে নেবে না।
- live-only অজানা (যা এই sandbox থেকে যাচাই করা অসম্ভব, owner-এর করণীয়): P0-7 live Render env/config, P0-8-live backup cron/off-box/alert, P1-11-live S3 bucket, D-8 live DB engine।
- পরিচিত ইচ্ছাকৃত বাদ: i18n/Bengali UI strings (P2-3), legacy `StudentSubject` drop (P2-7), Accounts full fee engine / guardian portal / online payment (future backlog), SSC restore (নিষিদ্ধ)।

## ২. এই সেশনের চাহিদা

- (ক) **Fresh environment থেকে পুরো যাচাই**: নতুন venv (Python 3.12 হলে `requirements.txt` / নাহলে documented fallback) → `pip install` → ফাঁকা DB-তে `migrate` → `loaddata institutions.json` → `check` → prod-shaped `check --deploy` (DEBUG=False + real-length SECRET_KEY + আসল host + proxy flags) → `makemigrations --check` → পূর্ণ `test students` → `node --test students/js/*.test.js`।
- (খ) **Route smoke test**: প্রতিটি named route-এ (permission-protected সহ) authenticated/anonymous client দিয়ে GET — কোনো 500 নেই; expected 200/302/403/404 লিপিবদ্ধ; route inventory টেবিল।
- (গ) **Upgrade path drill**: পূর্ববর্তী release-এর DB snapshot (ডিসপোজেবল কপি) → `migrate` → পূর্ণ suite/pass; backup+restore drill-এর সর্বশেষ প্রমাণ সংযুক্ত।
- (ঘ) **Security dark-spot checklist**: isolation matrix (সব read/write/export/print/API), upload limits, rate limits/lockout, headers/cookies, DEBUG leak, repo-তে secret/PII নেই, `git grep` দিয়ে প্রমাণ।
- (ঙ) **Docs consistency audit**: README, PROJECT_STATUS, TASK_BACKLOG, WORK_TRACKER, HANDOFF, prompts PROGRESS — সবাই একই যাচাই করা অবস্থা বলে; কোনো পুরোনো/ভুল দাবি নেই; প্রতিটি দাবির পাশে প্রমাণ।
- (চ) **Owner runbook**: release day-এর ধাপ (backup → owner PR অনুমোদন/merge → Render deploy → live check তালিকা → rollback plan) সহ `docs/RELEASE_CHECKLIST.md`; যেখানে live যাচাই দরকার সেখানে exact steps (concrete URL/command/env var)।
- (ছ) **Risk register**: খোলা decision/ঝুঁকি (i18n, legacy drop, SEC-FU-*, owner-only live items) এক টেবিলে।
- (জ) শেষে পুরো ২৮-প্রম্পট ledger-এর সাপেক্ষে চূড়ান্ত স্ট্যাটাস: কোনটি ✅, কোনটি 🟡, কোনটি ⛔ — এবং release go/no-go সুপারিশ।

## ৩. যা করতে হবে (ক্রমে)

1. §৫-এর সব কমান্ড ক্রমে চালাও (fresh venv, empty DB, migrate, tests); প্রতিটি কমান্ড + ফল + সময় রিপোর্টে লিপিবদ্ধ করো।
2. Route smoke: `students/urls.py` থেকে named URL তালিকা নিয়ে Django test client দিয়ে লুপ; 500 থাকলে root cause ও fix (এই সেশনেই ছোট fix করা যায়, বড় হলে আলাদা সেশন-প্রস্তাব)।
3. Upgrade path: সর্বশেষ snapshot/backup থেকে ডিসপোজেবল DB-তে migrate; migration reverse/rollback ঝুঁকি যাচাই (ইতিমধ্যেই migration rollback টেস্ট আছে — চালাও)।
4. Security checklist: আগের সেশনগুলোর টেস্ট modules একসঙ্গে চালিয়ে (isolation, audit scoping, upload, rate-limit, security settings) + `git grep` secret/PII scan + `git status` clean প্রমাণ।
5. Docs audit: প্রতিটি doc-এর দাবির সাথে প্রমাণ মিলিয়ে অমিল থাকলে সংশোধন (evidence ছাড়া দাবি মুছে ফেলা/Unverified হিসেবে লেখা)।
6. `docs/RELEASE_CHECKLIST.md` (নতুন) + `docs/prompts/reports/FN-01.md` (evidence table, test counts, risk register, go/no-go) তৈরি করো; PROGRESS.md-এ সব সারির চূড়ান্ত অবস্থা হালনাগাদ করো (owner-সিদ্ধান্ত বাকি থাকলে ⛔)।
7. শেষ স্ট্যাটাস ব্লকে লেখো: `✔ শেষ হয়েছে: প্রম্পট ২৮ / ২৮ — সেশন FN-01` + ২৮টির সারসংক্ষেপ (সম্পন্ন/আংশিক/ব্লকড)।

## ৪. সীমা ও নিয়ম (সব প্রম্পটে প্রযোজ্য)

- **branch:** সব কাজ `arena/01a0b7f7-school-management-system`-এ। `main`-এ সরাসরি push নয়, অন্য কোনো branch-এ যাওয়া নয়। শেষে `git push origin arena/01a0b7f7-school-management-system`।
- **PR:** পরিবর্তন থাকলে ওই branch থেকেই PR খুলবে (`gh pr create --base main`), কিন্তু **owner-এর অনুমোদন ছাড়া merge করবে না**। PR বিবরণে যাচাই করা অবস্থা, যাচাই না হওয়া অংশ ও ঝুঁকি আলাদা করে লিখবে।
- **SSC Registration / BoardResult:** পুনরুদ্ধার করা যাবে না (migration 0035 irreversible); `RetiredBoardFeatureTests` pass থাকবে।
- **live/production:** production DB, live Render, credentials, S3/bucket, cron — কিছুই ছোঁয়া বা সক্রিয় করা যাবে না। কোনো password/token chat-এ চাওয়া বা লেখা যাবে না (owner নিজে Render env-এ দেবেন)।
- **git:** `reset --hard`, `git clean`, force-push নয়। pre-existing uncommitted change স্পর্শ করা যাবে না। commit ছোট ও বর্ণনামূলক।
- **migration:** বিদ্যমান migration ফাইলের operations কখনো edit নয়; দরকার হলে **নতুন** append-only migration + `makemigrations --check` clean। destructive migration-এর আগে backup gate (DEVELOPMENT_GUIDE §7)।
- **secret/PII:** `.env`, `db.sqlite3`, `media/`, `backups/`, `.restore-drill/`, আসল কোনো ব্যক্তিগত ডেটা — commit/log/template-এ নয় (`.gitignore` মান্য)। টেস্টে শুধু বানানো (synthetic) ডেটা।
- **smallest coherent change:** এই প্রম্পটের scope-এর বাইরে refactor বা নতুন UI redesign নয়, নাম-পরিবর্তন নয়। নতুন paid service, SMS/email/payment activation, নতুন JS chart লাইব্রেরি — owner approval ছাড়া নয়।
- **প্রমাণ ছাড়া দাবি নিষেধ:** শুধু চালানো টেস্ট/check-এর ফলই "সম্পন্ন" হিসেবে লেখা যাবে; যাচাই না হলে `Unverified` / `Partial` লিখবে (repo নিয়ম: `docs/WORK_TRACKER.md`)।
- **ডকুমেন্টেশন:** প্রতিটি সেশনে সংশ্লিষ্ট doc entry (PROJECT_STATUS / TASK_BACKLOG / HANDOFF) যাচাই করা অবস্থা অনুযায়ী হালনাগাদ, এবং শেষে `docs/prompts/PROGRESS.md`-এ এই প্রম্পটের সারি (স্ট্যাটাস, তারিখ, commit, PR, টেস্ট প্রমাণ) আপডেট।

## ৫. যাচাই ও প্রমাণ (এই সেশনে চালাতে হবে)

**Isolated env (নতুন shell — স্যান্ডবক্সে ডিফল্টভাবে Django নেই):**

```bash
python3 -m venv /tmp/audit_venv && . /tmp/audit_venv/bin/activate
pip install "Django>=5.2,<6" openpyxl Pillow python-dotenv dj-database-url whitenoise psycopg2-binary django-storages boto3
# Python 3.12+ হলে সরাসরি: pip install -r requirements.txt   (Django 6.1)
# টেস্ট DB = throwaway SQLite; কখনো production DB নয়।
```

**Commands (এগুলো চালিয়ে প্রকৃত ফল রিপোর্ট করবে):**

```bash
python manage.py check
SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))') DEBUG=False ALLOWED_HOSTS='school-management-system-27mn.onrender.com' python manage.py check --deploy
python manage.py test students
node --test students/js/*.test.js
bash scripts/backup_smoke_test.sh
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `FN-01: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ২৮-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/FN-01.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- Release go/no-go ও তারিখ — owner।
- কোন খোলা decision ছাড়া release আটকাবে (EM-02 leave, OF-04 chart scope, EM-03 lock নিয়ম, DB-03 SEC-FU-2) — তালিকা করে owner-এর কাছে পেশ করা।
- Live Render-এ ৮-দফা চেক (P0-7) ও backup cron (P0-8-live) কে, কখন করবে — owner-এর অপারেশন সিদ্ধান্ত; agent কখনো নিজে production ছোঁবে না।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/FN-01.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
