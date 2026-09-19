# প্রম্পট ০৪ / ২৮ — সেশন EX-03 · Group-based Mark Evaluation

_বিভাগ: Exam · ধরন: উন্নয়ন · নির্ভরতা: প্রম্পট ০৩ (EX-02)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ০৪ / ২৮ (prompt 04/28) — সেশন EX-03 · উন্নয়ন · বিভাগ: Exam
   পূর্ববর্তী: প্রম্পট ০৩ / ২৮ (EX-02 — Result/Register roll-order) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ০৫ / ২৮ (EX-04 — নতুন subject / Higher Math workflow)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ০৪ / ২৮ (prompt 04/28) — সেশন EX-03 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ০৫ / ২৮ (EX-04 — নতুন subject / Higher Math workflow) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- `SubjectMarkSetting` (`students/models.py` ~L779-812) = `institution + admission_class + subject + exam_type`, uniqueness ওই চারটি মিলে; **group field নেই**। `MarksConfigMixin` থেকে full marks / CQ / MCQ / practical / weekly test + pass % নিয়ম আসে; row না থাকলে `Subject`-এর global default-এ fallback।
- `is_active` (migration 0034) দিয়ে "এই exam type-এ subjectটি ধরা হবে কি না" নিয়ন্ত্রণ হয়; `mark_evaluation_settings` view (URL `mark-evaluation/`) Office ও Exam — দুটো flyout থেকেই যাওয়া যায়; `_exam_group_selection` helper আছে।
- Group-ভিত্তিক subject তালিকা আসে `SubjectRequirement(institution, admission_class, group, subject, requirement_type, optional_set_key, religion_condition)` + `get_applicable_subjects()` থেকে; SSC Science-এ HMATH MANDATORY (0042), HSC Science-এ OPTIONAL।
- `GROUPED_CLASS_LABELS = ['9','10','11','12']` — class 9-এর নিচে group নেই; এই নিয়ম class-choices validation-এ মানতে হবে।
- বিদ্যমান টেস্ট: `MarksPartsAndPassRulesTests`, `MarkEvaluationActiveSubjectTests`, `students/test_result_analysis.py`, `students/test_new_subject_result_workflow.py`।

## ২. এই সেশনের চাহিদা

- Mark Evaluation পুরোপুরি **group-aware** করা: একই class + exam type-এ SCI / ARTS / HUM আলাদা config পাবে (full marks, parts, pass %), এবং সেই config-ই marks entry ও result computation-এ ব্যবহৃত হবে।
- Backward compatibility: পুরোনো row-এ group খালি থাকলে তা **সব group-এ প্রযোজ্য default** হিসেবে কাজ করবে (migration ডেটা হারাবে না, বিদ্যমান config ভাঙবে না)।
- Validation: full marks > 0; parts (CQ/MCQ/PT/WT) যোগ full marks-এর সাথে সঙ্গতিপূর্ণ (owner-নীতিমালা অনুযায়ী exact বা ≤); pass % 0–100; duplicate (institution+class+exam_type+subject+group) প্রতিরোধ; class <9 হলে group খালি রাখা বাধ্যতামূলক।
- UI: group selector + per-group listing/tabs; কোন subject কোন group-এ active তা একনজরে দেখা; inactive subject marks entry-তে আসবে না এবং result-এ count হবে না (আচরণ অপরিবর্তিত)।
- Config পরিবর্তনে অডিট (`record_audit`) থাকবে; institution scoping ও permission (`change_subject`) অপরিবর্তিত।

## ৩. যা করতে হবে (ক্রমে)

1. বর্তমান behavior-এর baseline টেস্ট লিখো: একই class-এ SCI ও ARTS-এর জন্য আলাদা full marks দেওয়ার চেষ্টা করলে কী হয় (আশা: এখন সম্ভব নয় — সেটিই ঘাটতি হিসেবে প্রমাণ হবে)।
2. মডেল ডিজাইন: `SubjectMarkSetting.group` (`blank=True`, `choices=Student.GROUP_CHOICES`) + uniqueness constraint আপডেট — **নতুন migration** (খালি group = সব group-এর default)।
3. Resolution chain বাস্তবায়ন: group-specific row → খালি-group row → `Subject` global default; এই chain-টি এক ফাংশনে রেখে marks entry ও `result_utils` দুটোতেই ব্যবহার করো (ডুপ্লিকেট logic নয়)।
4. UI: `mark_evaluation_settings` template-এ group selector + listing; Save-এ validation (parts sum, pass %, duplicate, group rule) ও স্পষ্ট error message।
5. Marks entry: group-specific config মান্য করে per-part validation; group-mismatch subject দেখাবে না।
6. টেস্ট: (i) group-specific override কাজ করে, (ii) খালি-group fallback, (iii) inactive subject বাদ, (iv) parts/pass validation negative case, (v) duplicate blocked, (vi) class <9-এ group লাগে না, (vii) institution scoping negative (অন্য institution-এর setting দেখা/বদলানো যায় না)।
7. চালাও §৫; তারপর PR।

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
python manage.py test students.test_subject_assignment_office
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `EX-03: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ০৪-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/EX-03.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- Parts-এর যোগফল full marks-এর সমান হতে হবে (কঠোর) নাকি ≤ হলে চলবে (নমনীয়)? সুপারিশ: কঠোর সমান, তবে owner নীতি বললে তা-ই।
- Weekly test কোন exam type-এ লাগবে (বর্তমান help text অনুযায়ী) — এবং group-ভেদে কি আলাদা? owner নিশ্চিত করবে।
- Group-specific config কি শুধু class 9–12-এ (group থাকা class) সীমাবদ্ধ থাকবে? সুপারিশ: হ্যাঁ।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/EX-03.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
