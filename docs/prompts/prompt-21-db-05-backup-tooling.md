# প্রম্পট ২১ / ২৮ — সেশন DB-05 · Backup tooling

_বিভাগ: মূল ব্যবস্থা · ধরন: নতুন ব্যবস্থা · নির্ভরতা: প্রম্পট ২০ (DB-04)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ২১ / ২৮ (prompt 21/28) — সেশন DB-05 · নতুন ব্যবস্থা · বিভাগ: মূল ব্যবস্থা
   পূর্ববর্তী: প্রম্পট ২০ / ২৮ (DB-04 — Settings ও CI) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ২২ / ২৮ (DB-06 — Restore drill ও automation)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ২১ / ২৮ (prompt 21/28) — সেশন DB-05 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ২২ / ২৮ (DB-06 — Restore drill ও automation) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- বিদ্যমান tooling: `manage.py backup_data`, `restore_backup`, `check_backups`, `fetch_backup`, `copy_media_to_storage`; scripts `scripts/backup.sh`, `restore.sh`, `backup_cron.sh` (healthcheck ping), `backup_smoke_test.sh` (`--postgres`, `--s3-endpoint`); `render.cron.yaml`; manifest + SHA; optional openssl/age encryption; optional S3 off-box copy; retention gate।
- টেস্ট: `students/test_backup_tooling.py` (docs-এ ৭২টি দাবি করা) + CI-তে backup smoke (sqlite + postgres) ও moto S3।
- Docs: `docs/BACKUP_AND_RESTORE.md`, `docs/BACKUP_RESTORE_GUIDE.md`, `docs/DATA_SAFETY_STATUS.md`, `docs/OWNER_RENDER_OPS_TUTORIAL.md`।
- Live অজানা (owner-only): Render cron আসলে চলছে কি না, off-box copy ও alert কাজ করে কি না, `P0B_BACKUP_ROOT` persistent কি না — P0-8-live।
- পরিচিত সীমা: Render cron-এর filesystem ephemeral, এবং cron থেকে web service DB-তে পৌঁছানো যাবে কি না তা live-নির্ভর।

## ২. এই সেশনের চাহিদা

- (ক) Tooling local-এ প্রমাণসহ যাচাই: sqlite + postgres (disposable) + moto S3-এ backup creation, encryption, off-box copy, manifest/SHA, restore verify, retention prune।
- (খ) যা আছে তা সম্পূর্ণ কিনা দেখা: DB snapshot + media archive + manifest (app/migration leaf version, record counts, SHA, timestamp, encryption metadata)।
- (গ) ঘাটতি বন্ধ (owner-নীতির ভিত্তিতে): retention/prune command বা flag; off-box copy retry + verify; failure-এ alert/healthcheck; freshness threshold configurable; `check_backups` exit code গুলো ডকুমেন্টেড ও টেস্টেড।
- (ঘ) Render-Backup পথ সিদ্ধান্ত ও ডকুমেন্টেশন: cron FS ephemeral → backup কোথায় যাবে (off-box bucket vs web service-এর মাধ্যমে dump); যে পথটি বেছে নেওয়া হবে, শুধু সেটিই "documented path" হিসেবে থাকবে ও রানবুকে ধাপ থাকবে।
- (ঙ) Destructive migration-এর আগে "fresh backup বাধ্যতামূলক" নিয়মটি কীভাবে বাস্তবে প্রয়োগ হবে (pre-flight check/runbook step) তা লেখা।

**সীমা:** production DB/backups-এ হাত নয়; সব drill disposable target-এ।

## ৩. যা করতে হবে (ক্রমে)

1. `./scripts/backup_smoke_test.sh` (sqlite) এবং `--postgres <disposable>` + `--s3-endpoint` (moto) চালিয়ে প্রকৃত ফল লিপিবদ্ধ করো।
2. Manifest ও verify ধাপ inspect করো: কী কী যাচাই হয়, কী বাদ পড়ে (record counts কোন table-এর, media file count, migration leaf)।
3. ঘাটতি (retention/retry/alert/threshold) বাস্তবায়ন করো — smallest change, বিদ্যমান CLI/স্ক্রিপ্ট signature ভেঙে নয় (backward compatible flag)।
4. নতুন/পরিবর্তিত behaviour-এর টেস্ট (fail path সহ: বড়/ক্ষতিগ্রস্ত archive, wrong key, off-box failure)।
5. runbook আপডেট: `docs/BACKUP_AND_RESTORE.md`-এ ০ থেকে ধাপ (backup → verify → off-box → restore drill → destructive migration gate) + `docs/DATA_SAFETY_STATUS.md`-এ status।
6. owner-এর জন্য ১ পৃষ্ঠার "করণীয়" তালিকা (Render env var, bucket, cron, alert destination) — কোনো secret নিজে লিখবে না।

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
python manage.py test students.test_backup_tooling
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

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `DB-05: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ২১-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/DB-05.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- Retention window (daily কত দিন, weekly কত সপ্তাহ) ও disk budget?
- Encryption key কোথায় থাকবে (owner-এর offline/age key নাকি Render env) — কী হারালে restore অসম্ভব, সেটি স্পষ্ট।
- Off-box destination: S3/R2/B2 (কোনটি) এবং কে alert পাবে (ইমেইল/Telegram ইত্যাদি)।
- `P0B_BACKUP_ROOT` persistent disk-এ থাকবে নাকি সম্পূর্ণ bucket-নির্ভর?
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/DB-05.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
