# প্রম্পট ২০ / ২৮ — সেশন DB-04 · Settings ও CI

_বিভাগ: মূল ব্যবস্থা · ধরন: নিরাপত্তা · নির্ভরতা: প্রম্পট ১৯ (DB-03)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ২০ / ২৮ (prompt 20/28) — সেশন DB-04 · নিরাপত্তা · বিভাগ: মূল ব্যবস্থা
   পূর্ববর্তী: প্রম্পট ১৯ / ২৮ (DB-03 — Permissions ও data isolation) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ২১ / ২৮ (DB-05 — Backup tooling)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ২০ / ২৮ (prompt 20/28) — সেশন DB-04 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ২১ / ২৮ (DB-05 — Backup tooling) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- `school_system/settings.py`: DEBUG default True; DEBUG=False-এ fallback SECRET_KEY নিয়ে boot guard (`ImproperlyConfigured`); `ALLOWED_HOSTS` wildcard থাকলে `students.E016` (check --deploy Error); `CSRF_TRUSTED_ORIGINS`, `TRUST_FORWARDED_PROTO`, `USE_X_FORWARDED_HOST` env parsing; `MAILERS_BACKEND` env-driven (Django 6-এর `mail.E001` fix); `DATABASE_URL` via `dj-database-url`; `EXAM_ABSENT_SUBJECT_FAILS`; `USE_S3` + `E011`/`W010` checks (`students/checks.py`)।
- CI `.github/workflows/tests.yml`: matrix sqlite + `postgres:16`, তিনটি deploy-guard ধাপ (fallback SECRET_KEY fail, wildcard host fail, production-shaped config pass), Node row-action test, backup smoke test (moto S3 সহ)।
- টেস্ট: `students/test_security_settings.py` (৫), `test_rate_limiting.py`, `test_upload_security.py`।
- `.env.example` ও `docs/PRODUCTION_CHECKLIST.md` (৮-দফা live runbook) আছে; live মান এখনো Unverified।

## ২. এই সেশনের চাহিদা

- Settings audit: প্রতিটি env var `.env.example`-এ আছে কি; ভুল/অসম্পূর্ণ মান হলে fail-fast (bool/int parsing নিরাপদ, silent default নয়); কোনো secret log/error message-এ যায় না।
- Production profile hardening (DEV আচরণ অপরিবর্তিত রেখে env-গেটেড): `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`/`SECURE_SSL_REDIRECT` (proxy-এর পেছনে) — প্রয়োজন ও ঝুঁকি বিচার করে smallest নিরাপদ ডিফল্ট (DEBUG=False হলে secure cookies on ইত্যাদি)।
- Logging: DEBUG=False-এ 500 পরিস্থিতিতে stack trace/secret leak হচ্ছে কি না যাচাই; custom error page (405/500) না থাকলে ছোট নিরাপদ page (internal তথ্য ছাড়া)।
- Upload/size limits: `DATA_UPLOAD_MAX_MEMORY_SIZE`, `FILE_UPLOAD_MAX_MEMORY_SIZE` ও photo-র ২MB নিয়মের সাথে সংগতি; খুব বড় POST প্রত্যাখ্যান।
- CI শক্ত করা: এই guard গুলোর টেস্ট CI-তে থাকে; ephemeral মান (কোনো আসল host/secret নয়); Node, backup smoke ও moto S3 ধাপ অটুট; version pin।
- লাইভ Render-এর ৮টি চেক (P0-7) owner-only — এই সেশন সেগুলো শুধু ডকুমেন্ট করবে, লাইভ যাচাই করবে না।

## ৩. যা করতে হবে (ক্রমে)

1. settings-এর সব env var + guard তালিকাভুক্ত করো; `test_security_settings.py`-এ বিদ্যমান কেসের সাথে তুলনা করে ফাঁকা দিক চিহ্নিত করো।
2. `.env.example`-এ নতুন var গুলো যোগ করো (উদাহরণ মান ছাড়া আসল secret নয়)।
3. Production profile hardening যোগ করো env-গেটেড fashion-এ; লোকাল dev (DEBUG=True) আচরণ বদলাবে না — আগে-পরে টেস্ট চালিয়ে প্রমাণ।
4. Error page/logging যাচাই: `DEBUG=False` পরিস্থিতিতে একটা টেস্ট (allowed host সহ) দিয়ে 500 path-এ internal detail leak হচ্ছে কি না দেখা; থাকলে ছোট ফিক্স।
5. CI-তে (থাকলে নেই এমন) guard-এর টেস্ট step যোগ করো — শুধু ephemeral মান দিয়ে; PR-এ ৩টি workflow job pass করতে হবে।
6. `docs/PRODUCTION_CHECKLIST.md` ও `DEPLOY_NOTES.md` হালনাগাদ (নতুন env var, owner-এর live চেক)।

**⚠️ সীমা:** এই সেশনে কোনো live Render env বদলানো যাবে না; কোনো আসল host/secret CI-তে নয়।

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
python manage.py test students.test_security_settings
python manage.py test students.test_upload_security
python manage.py test students.test_media_storage
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `DB-04: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ২০-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/DB-04.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- HSTS/SSL-redirect Render free tier-এ চালু করা হবে কি (proxy header trust যাচাই ছাড়া ঝুঁকি)? সুপারিশ: env flag, ডিফল্ট বন্ধ, ডকুমেন্টেড।
- `DEBUG=False` হলে secure cookies স্বয়ংক্রিয়ভাবে on — হ্যাঁ/না?
- Logging service (Sentry ইত্যাদি) বাইরে রাখা হচ্ছে — এই রিলিজে না, শুধু নোট।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/DB-04.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
