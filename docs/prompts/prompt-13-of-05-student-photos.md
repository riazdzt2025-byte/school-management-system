# প্রম্পট ১৩ / ২৮ — সেশন OF-05 · Student photos

_বিভাগ: Office · ধরন: যাচাই + উন্নয়ন · নির্ভরতা: প্রম্পট ১২ (OF-04)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ১৩ / ২৮ (prompt 13/28) — সেশন OF-05 · যাচাই + উন্নয়ন · বিভাগ: Office
   পূর্ববর্তী: প্রম্পট ১২ / ২৮ (OF-04 — Admission reports) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ১৪ / ২৮ (OF-06 — Public success page ও progress)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ১৩ / ২৮ (prompt 13/28) — সেশন OF-05 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ১৪ / ২৮ (OF-06 — Public success page ও progress) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- `Student.photo` optional `ImageField`; form/admin-এ upload চলে। নতুন upload-এর জন্য agreed policy: max 2 MiB, 300×300–4096×4096 inclusive, JPG/JPEG/PNG/GIF।
- New uploads `student_photos/<UUID>.<ext>` opaque storage key পায়; existing media keys migrate/backfill হয় না। Storage filesystem অথবা configured `USE_S3` `Storage` API দিয়ে চলে; private S3 signed URLs default।
- Student add/edit form upload/preview/clear; admission forms-এ **কোনো photo field হবে না**।
- Active/archived list + student detail + ID/result-card/print surfaces photo/fallback দেখায়। List rendering-এর N+1 query regression test আছে।
- Archive/TC student row থাকাকালীন retention; per-student clear, institution-scoped active/archived bulk clear, hard-purge-এ post-commit storage deletion। Remote delete failure retry queue নেই—review/merge gate হিসেবে report-এ লিখতে হবে।

## ২. Owner-এর acceptance scope (সিদ্ধান্ত নেওয়া হয়েছে)

- (ক) Upload/replace/clear secure; max 2 MiB, dimensions inclusive 300×300–4096×4096, existing formats unchanged; filenames opaque/path-safe; filesystem + S3-compatible `Storage` behavior test; permission/isolation unchanged।
- (খ) Student list thumbnail + accessible fallback; detail portrait; ID card, single/class result card ও print/result detail-এ photo; query-count regression।
- (গ) Admission form-এ ছবি নেওয়া **স্পষ্টভাবে out of scope** — public/internal কোনোটিতে নয়; admission photo migration/transfer হবে না।
- (ঘ) Photo archive/TC-তে থাকবে; per-student clear + institution-scoped bulk cleanup (active ও archived); hard purge-এ stored photo delete; lifecycle, permission/isolation regression tests।

## ৩. বাস্তবায়ন ও যাচাইয়ের ক্রম

1. Baseline upload/storage/isolation tests চালিয়ে বর্তমান behavior নথিবদ্ধ করো।
2. Model validator + opaque UUID upload path যোগ করো; form/admin path, size, extension, image content ও dimension limits টেস্ট করো।
3. Replace/clear/hard-purge storage cleanup post-commit schedule করো; archive/TC save-এ ফাইল retain প্রমাণ করো।
4. List/detail/ID/single-result/class-result/print display + fallback; bulk cleanup active ও archived list-এ; institution-scope/permission/audit tests।
5. Local filesystem ও dummy S3 storage/key/signing behavior পরীক্ষা; live bucket কখনো নয়।
6. §৫-এর focused/full suites, `check`, `makemigrations --check`, Node চালাও; unverified CI/browser/live অংশ আলাদা করে report করো।

## ৪. সীমা ও নিয়ম (সব প্রম্পটে প্রযোজ্য)

- **branch:** সব কাজ `arena/1805a6ab-school-management-system`-এ। `main`-এ সরাসরি push নয়, অন্য কোনো branch-এ যাওয়া নয়। শেষে `git push origin arena/1805a6ab-school-management-system`।
- **PR/merge:** ওই branch থেকেই PR খুলবে (`gh pr create --base main`)। Merge কেবল সব CI/local checks সবুজ এবং কোনো unresolved risk/policy ambiguity না থাকলে; risk থাকলে merge নয়, কারণ ও owner-এর করণীয় লিখবে। PR body-তে verified/unverified/risks আলাদা থাকবে।
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
python manage.py test students.test_upload_security
python manage.py test students.test_media_storage
python manage.py test students.test_institution_write_isolation
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- OF-05-এর আগের local baseline ছিল ৮২৬ Django + ২৯ Node; এই implementation-এর final verified সংখ্যা ৮৫২ Django + ২৯ Node। নতুন run-এ প্রকৃত সংখ্যা report/PROGRESS-এ লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `OF-05: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/1805a6ab-school-management-system`।
- `gh pr create --base main --head arena/1805a6ab-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- কোনো residual storage/privacy/CI risk থাকলে merge করবে না; risk মিটলে এবং সব checks সবুজ থাকলেই user-এর conditional merge instruction প্রয়োগ করবে।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ১৩-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/OF-05.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত (২০২৬-১০-০৬-এ রেকর্ড)

- Admission forms (public ও internal): **photo নেওয়া হবে না**।
- File policy: **max 2 MiB**, min **300×300**, max **4096×4096 px**, boundary inclusive; JPG/JPEG/PNG/GIF রাখা হবে।
- Retention: student record থাকলে archive/TC-তেও photo থাকবে; per-student clear ও institution-scoped bulk cleanup থাকবে; hard purge-এ storage file delete হবে।

এই সিদ্ধান্তে policy blocker নেই। নতুন অস্পষ্টতা বা storage failure-retry policy উঠলে merge নয়—`docs/prompts/reports/OF-05.md` ও `PROGRESS.md`-এ ঝুঁকি লিখে owner review চাইবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
