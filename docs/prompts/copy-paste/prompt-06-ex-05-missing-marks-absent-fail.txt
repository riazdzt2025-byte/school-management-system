# প্রম্পট ০৬ / ২৮ — সেশন EX-05 · Missing marks → Absent/Fail

_বিভাগ: Exam · ধরন: নিয়ম সংশোধন (policy) · নির্ভরতা: প্রম্পট ০৫ (EX-04)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ০৬ / ২৮ (prompt 06/28) — সেশন EX-05 · নিয়ম সংশোধন (policy) · বিভাগ: Exam
   পূর্ববর্তী: প্রম্পট ০৫ / ২৮ (EX-04 — নতুন subject / Higher Math workflow) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ০৭ / ২৮ (EX-06 — GPA 4.90–5.00 → 5.00)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ০৬ / ২৮ (prompt 06/28) — সেশন EX-05 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ০৭ / ২৮ (EX-06 — GPA 4.90–5.00 → 5.00) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- একক source: `students/result_utils.py::compute_subject_result` + `EXAM_ABSENT_SUBJECT_FAILS` (env, default True) — assigned subject-এ কোনো mark না থাকলে F + 0 counted, cell-এ dash; সব subject blank হলে `overall_gpa=None`, grade `ABSENT`, status `No Marks` (Fail নয়, rank নয়)।
- Entered `0` আর blank আলাদা জিনিস (`ExamMark.marks_obtained` None vs 0); optional/religion `not_applicable` কখনো count হয় না; TC/DISCONTINUED register থেকে বাদ।
- ডকুমেন্টেড decision: `docs/TASK_BACKLOG.md` → D-MIS = "blank → F, AB দেখানো, TC/DISCONTINUED বাদ"।
- টেস্ট: `AbsentSubjectRulesTests` (৫টি), `MarksPartsAndPassRulesTests` (`test_a_student_entered_nowhere_has_no_row`, `test_configured_but_blank_part_is_a_failed_part`)।
- সন্দেহের জায়গা (এই সেশনে যাচাই): প্রতিটি result view/print/export কি হুবহু একই source ব্যবহার করে, নাকি কোথাও আলাদা হিসাব (duplicate logic) আছে; AB/dash token সব জায়গায় একই কি না।

## ২. এই সেশনের চাহিদা

- নিয়মটি স্পষ্ট ও সর্বত্র অভিন্ন: assigned subject-এ mark না থাকলে = **Absent + Fail (0)**, `EXAM_ABSENT_SUBJECT_FAILS=True` default; সব blank = No Marks (rank-এ নেই); entered 0 = Fail (counted, dash নয়)।
- সব result surface (result sheet, summary, detail, card, full rank list, top 10, analysis pages, print/PDF, Excel export) একই `result_utils` নিয়ম মানে — কোনো ভিউ নিজে হিসাব করবে না; duplicate logic থাকলে সরিয়ে এক source-এ আনা।
- Display token consistency: dash / `AB` / `F` কোথায় আসবে তা এক টেবিলে নথিভুক্ত ও টেস্টে পিন করা (একই তথ্যের দুই রকম প্রদর্শন নয়)।
- `EXAM_ABSENT_SUBJECT_FAILS=False` path-ও টেস্টে থাকবে (excluded + dash), যাতে env বদলালে আচরণ প্রমাণিত থাকে।
- কোনো মান/নীতি নিজে থেকে বদলানো নয় — শুধু অসঙ্গতি ঠিক করা; নীতি বদলাতে হলে owner-সিদ্ধান্ত।

## ৩. যা করতে হবে (ক্রমে)

1. প্রতিটি result view/template inventory করে দেখো কে `build_exam_results`/`compute_subject_result` ব্যবহার করে আর কে নিজে mark aggregate করে (grep: `marks_obtained`, `sum(`, `avg`, `gpa` in views/templates)।
2. একটি ম্যাট্রিক্স টেবিল বানাও: surface × (blank treatment, zero treatment, all-blank, optional, TC) — যেখানে অসঙ্গতি, সেখানে smallest fix।
3. নিয়ম ও প্রদর্শন টেবিল docs-এ লিখো (`RESULT_PUBLISHING_GUIDE.md` + সংশ্লিষ্ট doc-এ)।
4. টেস্ট: partially-entered exam (কিছু subject blank) → F + counted; single blank part; blank vs 0; optional/religion not_applicable; TC/DISCONTINUED বাদ; একই exam-এ সব view-তে একই GPA/status; `EXAM_ABSENT_SUBJECT_FAILS=False` regression।
5. চালাও §৫; স্ট্যাটাস ব্লকে যাচাই করা surface-এর সংখ্যা লেখো।

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
python manage.py test students.test_result_analysis
python manage.py test students.test_new_subject_result_workflow
python manage.py test students.tests -k absent
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `EX-05: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ০৬-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/EX-05.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- Cell-এ blank mark দেখানো হবে `AB` নাকি dash (বর্তমান), আর status column-এ কী — owner নীতি নিশ্চিত করে ডকে চূড়ান্ত করা।
- Partially-entered exam-এ blank subjects GPA-তে 0 হিসেবে ধরা হবে কি না — বর্তমান নিয়ম (হ্যাঁ, F) owner-নিশ্চিত করবে।
- `EXAM_ABSENT_SUBJECT_FAILS` live production মান P0-7 চেকলিস্টে যাচাই করতে হবে (এই sandbox থেকে সম্ভব নয়)।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/EX-05.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
