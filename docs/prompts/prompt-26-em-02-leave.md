# প্রম্পট ২৬ / ২৮ — সেশন EM-02 · Leave

_বিভাগ: Employee · ধরন: শর্তসাপেক্ষ (owner decision) · নির্ভরতা: প্রম্পট ২৫ (EM-01)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ২৬ / ২৮ (prompt 26/28) — সেশন EM-02 · শর্তসাপেক্ষ (owner decision) · বিভাগ: Employee
   পূর্ববর্তী: প্রম্পট ২৫ / ২৮ (EM-01 — Employee/teacher assignment) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ২৭ / ২৮ (EM-03 — Payroll controls)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ২৬ / ২৮ (prompt 26/28) — সেশন EM-02 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ২৭ / ২৮ (EM-03 — Payroll controls) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- বর্তমানে `Employee.status`-এ `ON_LEAVE` আছে এবং `EmployeeStatusLog`-এ status পরিবর্তনের ইতিহাস থাকে, কিন্তু **কোনো leave request/approval/balance/workflow নেই**।
- Attendance-এ `L` = Late (ছুটি নয়) এবং `H` = Holiday — তাই ছুটির দিন attendance/report-এ কীভাবে আসবে তা এখন অনির্ধারিত।
- Payroll: `SalarySheet(employee, month, amount, date, status)` — unpaid leave-এর কোনো deduction যুক্তি নেই, এবং থাকলেও সেটি কর্তৃপক্ষের সিদ্ধান্ত ছাড়া স্বয়ংক্রিয় হওয়া উচিত নয়।
- ⚠️ এই সেশন **শর্তসাপেক্ষ**: owner-এর লিখিত নিয়ম ছাড়া কোনো মডেল/কোড লেখা যাবে না।

## ২. এই সেশনের চাহিদা

- **প্রথম কাজ: owner-সিদ্ধান্ত সংগ্রহ** (প্রশ্নগুলো §৮-এ) — ছুটির ধরন, paid/unpaid, entitlement/balance, approval chain, attendance-এ প্রভাব, payroll-এ প্রভাব, half-day, carry-forward।
- সিদ্ধান্ত এলে সীমিত (bounded) বাস্তবায়ন:
  - `LeaveRequest(employee, leave_type, from_date, to_date, days, reason, status PENDING/APPROVED/REJECTED, decided_by, decided_at, decision_remarks)`;
  - validation: date range, overlap প্রতিরোধ, entitlement/balance (নিয়ম অনুযায়ী), half-day (নিয়ম থাকলে);
  - UI: apply/approve/reject/list/filter; approver permission (HR/Principal);
  - integration: approved ছুটির দিন attendance-এ `L`/নির্ধারিত status বা rate-exclusion (owner-নীতি), payroll-এ শুধু **advisory** (silent money change নয়);
  - audit trail প্রতিটি অবস্থান্তরে; institution scoping; migration + টেস্ট (overlap, balance, approval chain negative, cross-institution 404)।
- সিদ্ধান্ত না এলে: **কোনো কোড নয়** — শুধু `docs/prompts/reports/EM-02-decision-request.md` (বিকল্প + সুপারিশ + প্রভাব) এবং PROGRESS.md-এ `⛔ ব্লকড (owner decision)`; email/SMS notification কোনো অবস্থাতেই নয়।

## ৩. যা করতে হবে (ক্রমে)

1. Owner-প্রশ্নগুলো গুছিয়ে (বিকল্প + সুপারিশ + প্রভাব) সেশন-রিপোর্টে লিখে সিদ্ধান্ত চাও।
2. সিদ্ধান্ত পেলে: মডেল+মাইগ্রেশন → service/validation → forms/views/urls/templates → permission/audit → টেস্ট (happy + negative) → ডক।
3. Attendance/payroll integration শুধু owner-নীতির সীমার ভেতরে; payroll-এ deduction হলে সেটি আলাদা **সিদ্ধান্ত + টেস্ট + ডকুমেন্টেশন** ছাড়া কোথাও নয়।
4. সিদ্ধান্ত না পেলে: স্ট্যাটাস ব্লকে `⛔ ব্লকড`, কোনো ফাইল বদল নয় (ডক ছাড়া), পরের প্রম্পট চালানো যাবে কি না owner-এর উপর ছাড়ো।
5. সবশেষে ডকে "কারা ছুটি অনুমোদন করে, কীভাবে attendance-এ আসে, payroll-এ কী প্রভাব" স্পষ্ট লিখো।

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
python manage.py test students.test_edit_audit
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `EM-02: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ২৬-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/EM-02.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- Leave type: casual/sick/earned/maternity/others — কোনগুলো এই রিলিজে?
- Paid/unpaid নীতিমালা ও entitlement/balance (বার্ষিক কত দিন, carry-forward?)
- Approve কে করবে: HR, Principal নাকি দু'ধাপে?
- Attendance-এ approved leave কী (status `L`? আলাদা মাত্রা? rate থেকে বাদ?)
- Payroll-এ unpaid leave-এর প্রভাব: শুধু তথ্য দেখানো, নাকি deduction (কে অনুমোদন করবে)?
- Half-day ও ছুটির balance-year (ক্যালেন্ডার নাকি জুলাই-জুন) — owner নীতি।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/EM-02.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
