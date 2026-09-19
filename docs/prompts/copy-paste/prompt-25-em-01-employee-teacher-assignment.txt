# প্রম্পট ২৫ / ২৮ — সেশন EM-01 · Employee/teacher assignment

_বিভাগ: Employee · ধরন: যাচাই + উন্নয়ন · নির্ভরতা: প্রম্পট ২৪ (AT-02)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ২৫ / ২৮ (prompt 25/28) — সেশন EM-01 · যাচাই + উন্নয়ন · বিভাগ: Employee
   পূর্ববর্তী: প্রম্পট ২৪ / ২৮ (AT-02 — Calendar/report accuracy) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ২৬ / ২৮ (EM-02 — Leave)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ২৫ / ২৮ (prompt 25/28) — সেশন EM-01 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ২৬ / ২৮ (EM-02 — Leave) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- Employee: `Employee(institution, name, designation, status ACTIVE/INACTIVE/ON_LEAVE, ...)` + `EmployeeStatusLog` + `change_employee_status`/`employee_status_history` + CRUD (`employee_list` paginated, `employee_detail`); টেস্ট: isolation + audit (`test_edit_audit.py`)।
- Exam signature sheet (`signature_sheet.html`) আছে এবং `class_section_summary` আছে — কিন্তু **শিক্ষক↔শ্রেণি/বিভাগ/বিষয় assignment নেই** (ডকের backlog-এ স্পষ্ট ঘাটতি)।
- `Student`/`SubjectRequirement` group-নিয়ম class 9–12-এ প্রযোজ্য, `institution.classes` থেকে class choices আসে।

## ২. এই সেশনের চাহিদা

- (ক) বিদ্যমান employee flows যাচাই: CRUD, status change + history + audit, scoping/isolation, salary sheet-এর সাথে সম্পর্ক, active/inactive filter — প্রমাণসহ (নতুন কোড না থাকলে শুধু টেস্ট যাচাই করে নথিভুক্ত করা)।
- (খ) **Teacher assignment registry** যোগ করা: `TeacherAssignment(employee, institution, admission_class, section, subject, session, is_active)` (নাম owner-নিশ্চিত) —
  - validation: class `institution.classes`-এর মধ্যে, class ≥9 হলে group নিয়ম মানা, subject `SubjectRequirement`-এর সাথে সঙ্গতিপূর্ণ, একই teacher+class+section+subject+session-এ duplicate active নিষিদ্ধ;
  - UI: assign/unassign(form/list), per-employee তালিকা, per class/section/subject তালিকা;
  - permission policy (HR এবং/অথবা Office) server-side; institution scoping;
  - audit: কে কী assignment বদলেছে;
  - integration: `signature_sheet`/`class_section_summary`-তে assigned teacher প্রদর্শন (উপযোগী হলে), কর্মচারীর detail-এ assignment tab।
- (গ) Migration + isolation/validation টেস্ট + owner-নির্দেশিত report (কোন teacher কতটা class নিচ্ছে)।

## ৩. যা করতে হবে (ক্রমে)

1. Employee flows যাচাই টেস্ট চালাও; যেখানে guard/scoping ফাঁকা সেখানে ছোট ফিক্স।
2. `TeacherAssignment` মডেল + migration design করো (institution FK, session, is_active, unique constraint) — destructive কিছু নয়।
3. Forms/views/urls/templates: assignment পেজ (filter by class/section/subject), per-employee তালিকা; permission গার্ড + scoping helper ব্যবহার।
4. Audit `record_audit` যোগ করো; assignment বদলানোর ইতিহাস দেখা যায়।
5. টেস্ট: duplicate block, class/section নিয়ম, group নিয়ম, cross-institution 404, permission ছাড়া 403, unassign-এর পর result/print-এ হালনাগাদ, migration rollback smoke।
6. signature sheet / class summary integration: যেখানে teacher নাম দেখানো যুক্তিসঙ্গত, সেখানে যোগ করো (টেস্ট সহ)।
7. ডকে (HR সেকশন) assignment ধারণা ও ব্যবহার লিখো।

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
python manage.py test students.test_edit_audit
python manage.py test students.test_institution_write_isolation
python manage.py test students.test_navigation
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `EM-01: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ২৫-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/EM-01.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- Assignment granularity: class+section+subject (সুপারিশ) নাকি class+section class-teacher ধারণা (আলাদা field)?
- কে assign করতে পারবে: HR dept না Office না উভয়ই? (permission map-এ কী যোগ হবে)
- Session-wise retention: পুরোনো session-এর assignment ইতিহাস রাখা হবে? সুপারিশ: হ্যাঁ (`is_active=False`, রেকর্ড মুছে ফেলা নয়)।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/EM-01.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
