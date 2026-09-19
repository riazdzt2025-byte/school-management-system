# প্রম্পট ২৩ / ২৮ — সেশন AT-01 · Entry/correction

_বিভাগ: Attendance · ধরন: যাচাই + উন্নয়ন · নির্ভরতা: প্রম্পট ২২ (DB-06)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ২৩ / ২৮ (prompt 23/28) — সেশন AT-01 · যাচাই + উন্নয়ন · বিভাগ: Attendance
   পূর্ববর্তী: প্রম্পট ২২ / ২৮ (DB-06 — Restore drill ও automation) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ২৪ / ২৮ (AT-02 — Calendar/report accuracy)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ২৩ / ২৮ (prompt 23/28) — সেশন AT-01 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ২৪ / ২৮ (AT-02 — Calendar/report accuracy) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- Entry flow: `mark_attendance` (form: date, class, section, mark_type student/employee) → `mark_attendance_bulk(date, class, section, type)` — প্রতি student/employee-এর জন্য `update_or_create` + audit + `_require_department(('Office','Exam'))` + institution scope।
- Model: `AttendanceRecord(institution, student/employee, date, status P/A/L/H, remarks, created_by, created_at)`; unique constraint per institution+student/date এবং per institution+employee/date; `attendance_report` (paginated 100), `attendance_summary` (date range + rates)।
- টেস্ট: attendance-সম্পর্কিত টেস্ট `students/tests.py`-এ + isolation negative টেস্ট (cross-institution mark refusal)।
- **Correction workflow নেই** (একবার mark করার পর per-record edit/audit দৃশ্যমান নয়) — এই সেশনের উন্নয়ন।

## ২. এই সেশনের চাহিদা

- (ক) Entry যাচাই: student vs employee mode, class/section নিয়ম (`institution.classes`), একই দিনে আবার mark করলে update-in-place (duplicate নয়), remarks, ভবিষ্যতের তারিখ প্রত্যাখ্যান, খালি section হ্যান্ডলিং, cross-institution refusal, permission/anonymous negative — সব টেস্ট।
- (খ) **Correction workflow**: পূর্বে-marked দিন/শ্রেণির রেকর্ড দেখে সংশোধন করার পথ — কোন ছাত্র/employee-এর কোন দিনের status/remarks বদলাবে তা স্পষ্ট (এক রেকর্ডে inline edit বা নির্বাচিত correction form); কে, কখন, আগের মান কী ছিল — সব `AuditLog`-এ।
- (গ) Correction-এর সীমা/policy: কত দিন পিছিয়ে সংশোধন করা যাবে, কে করতে পারবে (Office/Exam — যারা mark করতে পারে), holiday-এর দিন) — owner সিদ্ধান্ত অনুযায়ী; নীতি ডকে।
- (ঘ) ভবিষ্যতের তারিখ/নিষিদ্ধ দিনে mark ব্লক (server-side, UI লুকানো নয়)।

## ৩. যা করতে হবে (ক্রমে)

1. বিদ্যমান entry flow-এর প্রতিটি কেস টেস্ট দিয়ে যাচাই করো (উপরে তালিকাভুক্ত); fail/অস্পষ্ট আচরণ ঠিক করো।
2. Correction view + form + URL যোগ করো (smallest): একটি রেকর্ড নির্বাচন → status/remarks বদল → `record_audit`-এ আগের/নতুন মান; bulk mark-এর audit প্যাটার্ন অনুসরণ করো।
3. Report page থেকে প্রতিটি রেকর্ডে "Correct" link (permission-gated) — শুধু দৃশ্যমান নয়, direct URL-এও guard।
4. টেস্ট: correction audit row, তারিখ-সীমা (policy window) বাইরে block, অন্য institution-এর record-এ 404, permission ছাড়া 403, future date block, correction-এর পর report/summary-তে হালনাগাদ মান।
5. `attendance_report`-এ filter (date range/class/section/status) ও correction link থাকলে টেস্ট করো; print/CSV থাকলে এই সেশনে না-ও হতে পারে (AT-02-তে)।

**সীমা:** attendance-এর গণিত (rates) AT-02-এর কাজ; এখানে data entry/correction।

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
python manage.py test students.tests -k attendance
python manage.py test students.test_institution_write_isolation
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `AT-01: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ২৩-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/AT-01.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- কে correction করতে পারবে: Office + Exam উভয়ই নাকি যিনি mark করেছিলেন? সুপারিশ: যাদের daily mark permission আছে তারাই, কিন্তু audit সবসময়।
- Correction window (যেমন ৭/৩০ দিন) — owner নীতি?
- ভবিষ্যতের তারিখ সম্পূর্ণ নিষিদ্ধ নাকি নির্দিষ্ট role করতে পারবে?
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/AT-01.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
