# প্রম্পট ১৫ / ২৮ — সেশন OF-07 · Admission/import integrity

_বিভাগ: Office · ধরন: যাচাই · নির্ভরতা: প্রম্পট ১৪ (OF-06)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ১৫ / ২৮ (prompt 15/28) — সেশন OF-07 · যাচাই · বিভাগ: Office
   পূর্ববর্তী: প্রম্পট ১৪ / ২৮ (OF-06 — Public success page ও progress) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ১৬ / ২৮ (OF-08 — Archive/promotion/certificates)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ১৫ / ২৮ (prompt 15/28) — সেশন OF-07 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ১৬ / ২৮ (OF-08 — Archive/promotion/certificates) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- Admission state machine: `office_approve_application`, `office_reject_application`, `office_handoff_application`, `accounts_approve_payment` (payment approve-এ `Student` তৈরি, auto `MoneyReceipt RC-<year>-<code>`, mandatory subject auto-assign, `Fee` pre-fill + warning, capacity `SectionCapacity.has_room`, `next_step`)।
- Student import: `import_students` + `download_import_template` — capacity skip (P1-7), zero-padding tolerance '09'↔'9' (P1-8), group rule (class <9-এ group নেই), scoped clerk-এর জন্য institution বাধ্যতামূলক (SEC-IMPORT), row-level error report।
- Marks import: `import_exam_marks` + per-subject template; blank vs 0 পার্থক্য (`ExamMark` part columns)।
- আগের সেশনগুলোতে অনেক negative টেস্ট (50+ isolation, money validation, rate-limit) আছে — এই সেশনটি **integrity audit** (happy path + boundary + failure), নতুন ফিচার নয়।

## ২. এই সেশনের চাহিদা

- Admission transitions: অবৈধ transition block হয় কি (যেমন office approve ছাড়া payment approve নয়, reject-এর পরে আর পরিবর্তন নয়, দুইবার enrol নয় — `enrolled_student` OneToOne), অংশগ্রহণকারী actor/সময়/remarks সংরক্ষিত, প্রতিটি transition-এ `AuditLog` row।
- Capacity: শেষ আসন দুজন একসাথে approve করলে কী হয় (race) — transaction/locking আচরণ পরীক্ষা করে স্পষ্ট fault-tolerable নিয়ম (block + message) এবং টেস্ট।
- Receipt: `RC-…` collision-safety, Payment approve-এর সাথে receipt/student creation-এর atomicity (মাঝপথে fail হলে অর্ধেক ডেটা নয়)।
- Import: duplicate student id/roll, invalid class/section, capacity, group rule, '09' vs '9', guardian contact খালি, scoped clerk institution, partial failure (transaction) ও row-level error message — সব টেস্ট।
- Marks import: অজানা ছাত্র, ভুল subject/exam match, full marks ছাড়িয়ে যাওয়া মান, blank vs 0, ভুল file format — প্রতিটি ক্ষেত্রে স্পষ্ট error, silent data loss নয়।

## ৩. যা করতে হবে (ক্রমে)

1. প্রতিটি flow-এর জন্য একটি matrix বানাও: ধাপ × (happy, boundary, invalid, unauthorized, cross-institution) — কোথায় টেস্ট আছে, কোথায় নেই।
2. ফাঁকা কেসগুলোর জন্য টেস্ট লিখো; যদি টেস্ট fail করে, root cause বের করে smallest fix করো (transaction/locking/validation)।
3. Atomicity যাচাই: payment approve-এ exception হলে student/receipt না তৈরি (`transaction.atomic` + টেস্ট)।
4. Import-এর row-level error message ও report output-এ কত row যোগ হলো/বাদ পড়ল তা assert করো।
5. ফলাফল `docs/prompts/reports/OF-07.md`-এ ম্যাট্রিক্সসহ লেখো; fix থাকলে PR-এ আলাদা করে উল্লেখ করো।

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
python manage.py test students.test_import_capacity
python manage.py test students.test_auto_receipts
python manage.py test students.test_institution_write_isolation
python manage.py test students.test_guardian_contact
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `OF-07: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ১৫-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/OF-07.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- Capacity race: block করে message দেখানো (সুপারিশ) নাকি waitlist? — owner।
- Duplicate roll/student-id: reject (সুপারিশ) নাকি warn করে allow (school নীতি)?
- Fee mismatch: বর্তমানে warn; block করতে হবে কি না — পেমেন্ট-প্রবাহ বিবেচনায় owner সিদ্ধান্ত।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/OF-07.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
