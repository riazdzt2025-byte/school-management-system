# প্রম্পট ০২ / ২৮ — সেশন EX-01 · Import redirect ও Analysis subtab

_বিভাগ: Exam · ধরন: সংশোধন · নির্ভরতা: প্রম্পট ০১ (baseline)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ০২ / ২৮ (prompt 02/28) — সেশন EX-01 · সংশোধন · বিভাগ: Exam
   পূর্ববর্তী: প্রম্পট ০১ / ২৮ (০০ — সর্বশেষ checkout থেকে বাকি কাজ নির্ধারণ (baseline)) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ০৩ / ২৮ (EX-02 — Result/Register roll-order)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ০২ / ২৮ (prompt 02/28) — সেশন EX-01 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ০৩ / ২৮ (EX-02 — Result/Register roll-order) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- `students/views.py::import_exam_marks` সফল import-এর পর `redirect(import_page_url)` করে (দেখা গেছে ~L3700-3735 region-এ) — অর্থাৎ "একই exam/subject/group-এর import page-এ থাকা" একবার ঠিক করা হয়েছিল (PR #29 দাবি)। এটি এখনো ঠিক আছে কি না regression test দিয়ে প্রমাণ করতে হবে।
- Sidebar: `students/templates/students/base.html` ~L234-243-এ **আলাদা "Result Analysis" flyout group** (৫টি link: Subject Fail List, Multi-term Results, Merit Slides, Result Cards (Class), Section Arrangement), কিন্তু Exam flyout (~L220-232) এ Enter Marks / Exam List / Mark Evaluation আছে — **কোনো Analysis entry নেই**।
- Result Analysis views: `result_analysis_subject_fail`, `result_analysis_multi_term`, `result_analysis_merit_slides`, `result_analysis_result_cards`, `section_arrangement` + `_require_result_analysis_department` guard, `can_result_analysis` context flag, `students/test_result_analysis.py`, nav টেস্ট `students/test_navigation.py`।
- অর্থাৎ "Analysis subtab" চাহিদার বর্তমান অবস্থা: পেজগুলো আছে, কিন্তু **Exam সেকশনের ভেতরে subtab হিসেবে নেই** — এটি এই সেশনের সংশোধন।

## ২. এই সেশনের চাহিদা

- (ক) Marks import শেষে ব্যবহারকারী **একই exam + subject (+group)**-এর import পেজে ফেরে — আচরণ নিশ্চিত করা এবং test দিয়ে পিন করা (regression guard)।
- (খ) **Exam সেকশনের ভেতরে Analysis subtab**: Exam flyout থেকে Result Analysis-এর ৫টি পেজেই যাওয়া যায়, permission-gated (per-view guard অপরিবর্তিত থাকবে)। পুরোনো আলাদা "Result Analysis" group-এর linkগুলো যেন ভেঙে না যায় — ডিফল্ট সিদ্ধান্ত: দুটো entry point-ই থাকবে (একই named URL), নতুন কোনো view/template বানানো নয়।
- (গ) Cross-link: `exam_list` পেজ থেকে Analysis subtab-এ দৃশ্যমান entry, এবং প্রতিটি result page-এর header-এ প্রাসঙ্গিক Analysis পেজের link (ব্যবহারযোগ্যতার উন্নতি)।
- (ঘ) কোনো dead link, `NoReverseMatch` বা permission ফাঁক থাকবে না — প্রতিটি link `reverse()` করা নামযুক্ত URL এবং server-side guard-ই নিরাপত্তা দেবে (মেনু লুকানো নিরাপত্তা নয়)।

## ৩. যা করতে হবে (ক্রমে)

1. প্রথমে যাচাই: `import_exam_marks`-এর POST সফল হলে redirect কোথায় যায় — বর্তমান আচরণ test দিয়ে লিখে ফেলো (subject/group param সংরক্ষিত থাকে কি)।
2. `test_navigation.py`-এর বিদ্যমান convention পড়ে নাও (কীভাবে nav entry + permission gate টেস্ট করা হয়)।
3. Exam flyout-এ "Analysis" nested link ব্লক যোগ করো — ৫টি existing named URL, `can_result_analysis` / perms গেট; HTML/CSS `nav-group`/`flyout` প্যাটার্ন অনুসরণ করে (নতুন JS নয়)।
4. `exam_list` + result page গুলোতে cross-link যোগ করো (শুধু permission থাকলে)।
5. টেস্ট যোগ করো: (i) import POST → redirect URL-এ একই exam + subject (+group), (ii) Exam flyout-এ Analysis links authorized user-এর জন্য উপস্থিত, unauthorized/anonymous-এর জন্য অনুপস্থিত, (iii) প্রতিটি Analysis URL direct hit-এ guard আগের মতোই (403/302), (iv) দুটো entry point একই named URL-এ যায়।
6. চালাও §৫-এর কমান্ড; তারপর PR।

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
python manage.py test students.test_published_lock_and_cell_shortcut
python manage.py test students.test_result_analysis
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

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `EX-01: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ০২-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/EX-01.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- Placement: Exam flyout-এ সরাসরি ৫টি Analysis link (সুপারিশ, নতুন view লাগে না) নাকি Exam-এর ভেতরে একটি ছোট Analysis landing page (নতুন view + টেস্ট বেশি)? ডিফল্ট = সরাসরি link; owner ভিন্ন কিছু চাইলে লেখো।
- পুরোনো আলাদা "Result Analysis" sidebar group রাখা হবে (সুপারিশ: রাখা, যাতে কেউ বিভ্রান্ত না হয়) নাকি Exam-এর ভেতরে merge? রাখার পক্ষে সুপারিশ, কিন্তু owner-সিদ্ধান্ত চূড়ান্ত।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/EX-01.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
