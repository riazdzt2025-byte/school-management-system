# প্রম্পট ০৫ / ২৮ — সেশন EX-04 · নতুন subject / Higher Math workflow

_বিভাগ: Exam · ধরন: যাচাই + উন্নয়ন · নির্ভরতা: প্রম্পট ০৪ (EX-03)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ০৫ / ২৮ (prompt 05/28) — সেশন EX-04 · যাচাই + উন্নয়ন · বিভাগ: Exam
   পূর্ববর্তী: প্রম্পট ০৪ / ২৮ (EX-03 — Group-based Mark Evaluation) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ০৬ / ২৮ (EX-05 — Missing marks → Absent/Fail)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ০৫ / ২৮ (prompt 05/28) — সেশন EX-04 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ০৬ / ২৮ (EX-05 — Missing marks → Absent/Fail) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- **তিন-স্তরের Higher Math প্রমাণ আগে থেকেই docs-এ আছে** — এই সেশনে তিনটিই আবার নিজে যাচাই করতে হবে: (১) curriculum: `students/curriculum_data.py`-তে `HMATH`; `SSC_GROUPS['SCI']`-তে MANDATORY, `HSC_GROUPS['SCI']`-তে OPTIONAL (`sci_4th`); (২) DB: migration `0042_higher_math_mandatory_science.py` (SSC 9/09/10 → MANDATORY, reverse → OPTIONAL) + `seed_subjects` / `seed_subject_requirements` কমান্ড; (৩) assigned: `SubjectRequirement` rows + `subject_requirement_list` page (Office CRUD, inline "নতুন subject" তৈরি, quick-type, auto-fill)।
- Marks path: `mark_evaluation_settings` → `enter_marks` / `import_exam_marks` → `result_utils.build_exam_results` → result views। `Subject` global default (full_marks/CQ/MCQ/practical + pass rule) fallback হিসেবে কাজ করে।
- টেস্ট: `students/test_new_subject_result_workflow.py`, `students/test_subject_assignment_office.py`, `students/test_result_analysis.py::test_ssc_higher_math_is_mandatory`।

## ২. এই সেশনের চাহিদা

- End-to-end workflow যাচাই করা: নতুন subject তৈরি → class/group-এ assign (MANDATORY/OPTIONAL/CONDITIONAL) → mark evaluation config → marks entry/import → result — প্রতিটি ধাপে প্রমাণসহ।
- ঘাটতি বন্ধ করা: (ক) যেসব subject-এর `SubjectMarkSetting` row নেই তাদের marks entry/result Subject default-এ fallback করবে এবং **UI-তে স্পষ্ট notice/warning** দেখাবে (silent 0/dash নয়); (খ) assigned subject inactive করার পর তার পুরোনো `ExamMark` কী হবে — owner-নীতিমালা অনুযায়ী block (message) বা exclude, কিন্তু আচরণ স্পষ্ট ও টেস্টে পিন করা; (গ) optional/conditional subject selection (`StudentSubjectChoice`, `optional_set_key`, `religion_condition`) না থাকলে result-এ `not_applicable` আচরণ যাচাই।
- তিন-স্তরের consistency একটি টেস্টে পিন করা (curriculum ↔ migration ↔ assigned), যাতে ভবিষ্যতে কেউ এক স্তর বদলে দিলে টেস্ট fail করে।

## ৩. যা করতে হবে (ক্রমে)

1. প্রথমে তিন স্তর যাচাই করে প্রমাণ লেখো (grep + shell-এ `manage.py shell` বা টেস্ট দিয়ে প্রমাণ: curriculum dict, migration 0042-এর data operation, `SubjectRequirement` row)।
2. নতুন subject-এর জন্য "কোন ধাপগুলো লাগে" walk-through টেস্ট: subject create → assign → mark setting (লাগলে) → marks → result; কোন ধাপ বাদ পড়লে কী হয় তা assert করো।
3. fallback warning/notice যোগ করো (smallest change — template notice + test), যাতে কাজ না থামিয়ে ব্যবহারকারী জানে।
4. inactive/capacity/assignment-পরিবর্তনের নিয়ম owner-সিদ্ধান্ত অনুযায়ী কোড+টেস্টে পিন করো (সিদ্ধান্ত না এলে শুধু ডকুমেন্ট + `⛔` নোট)।
5. HMATH প্রতি স্তরে MANDATORY (SSC SCI 9/09/10) — টেস্ট চলমান রাখো; HSC-তে OPTIONAL আচরণও।
6. চালাও §৫; রিপোর্টে তিন-স্তরের প্রমাণ টেবিল।

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
python manage.py test students.test_new_subject_result_workflow
python manage.py test students.test_subject_assignment_office
python manage.py test students.test_result_analysis
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `EX-04: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ০৫-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/EX-04.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- ইতিমধ্যে entered `ExamMark` থাকা subject inactive/remove করলে: block + স্পষ্ট message (সুপারিশ) নাকি allow + result থেকে বাদ?
- Optional subject-এর ক্ষেত্রে ছাত্রের choice না থাকলে: result-এ সম্পূর্ণ বাদ (বর্তমান আচরণ) নাকি "choice pending" warning — owner নিশ্চিত করবে।
- Class 9-এর নিচে grouping নেই — নতুন subject যোগ করার সময় এ নিয়ম শুধু UI-তে নাকি forms/API-তেও (সুপারিশ: উভয়ই)।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/EX-04.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
