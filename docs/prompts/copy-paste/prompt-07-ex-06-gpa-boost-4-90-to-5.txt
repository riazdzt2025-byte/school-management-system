# প্রম্পট ০৭ / ২৮ — সেশন EX-06 · GPA 4.90–5.00 → 5.00

_বিভাগ: Exam · ধরন: নতুন নিয়ম · নির্ভরতা: প্রম্পট ০৬ (EX-05)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ০৭ / ২৮ (prompt 07/28) — সেশন EX-06 · নতুন নিয়ম · বিভাগ: Exam
   পূর্ববর্তী: প্রম্পট ০৬ / ২৮ (EX-05 — Missing marks → Absent/Fail) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ০৮ / ২৮ (EX-07 — Ctrl/Cmd+Click correction)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ০৭ / ২৮ (prompt 07/28) — সেশন EX-06 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ০৮ / ২৮ (EX-07 — Ctrl/Cmd+Click correction) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- কোড ইতিমধ্যে আছে বলে দেখা গেছে: `students/result_utils.py` ~L925-930-এ `Decimal('4.90') <= overall_gpa < Decimal('5.00')` হলে overall GPA 5.00, সাথে owner decision (2026-09-17) মন্তব্য; `get_grade`: ≥80% → A+/5.00, ≥70% → A/4.00 …।
- `build_exam_results`-এ GPA = subject gpa_points-এর গড় `round(2)`; তাই boost ঠিক কোন মানে লাগবে তা rounding-নীতির উপর নির্ভর করে (4.895 → 4.90 না 4.89?)।
- টেস্ট: GPA/boost-সম্পর্কিত বিদ্যমান টেস্ট `students/tests.py`-এ আছে (PR #29-এর ৫টি নতুন টেস্টের অংশ) — প্রকৃত নাম খুঁজে নাও।
- doc দাবি: `docs/TASK_BACKLOG.md` → D-GPA "Decided 2026-09-17 — 4.90-4.99 → 5.00 A+ implemented"।

## ২. এই সেশনের চাহিদা

- নতুন নিয়মটি **নির্ভুলভাবে ও সর্বত্র** প্রয়োগ: overall GPA 4.90–4.99 (inclusive lower, exclusive upper) → 5.00/A+; 5.00 ঠিক থাকবে; 4.89 বা তার নিচে boost নয়।
- Rounding নীতিটি স্পষ্ট ও deterministic করা (recommended: `Decimal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)`) এবং টেস্টে পিন করা; Python-এর banker's rounding-এর উপর ভরসা নয়।
- Boost-এর প্রভাবে fail/absent কেস প্রভাবিত হবে না (একটি subject F থাকলে overdue boost নয়); GPA কখনো 5.00 ছাড়াবে না।
- ফলাফল সব view/print/export/rank/analysis-এ একই মান; `position` নির্ধারণ boost-এর পরে সব ছাত্রের একই নিয়মে হবে (relative order ভাঙবে না)।
- ডকুমেন্টেশন: নিয়ম, উদাহরণ ও সীমা (`RESULT_PUBLISHING_GUIDE.md` + `docs/` entry)।

## ৩. যা করতে হবে (ক্রমে)

1. বর্তমান implementation পড়ো এবং rounding-এর প্রকৃত আচরণ পরীক্ষা করো (`Decimal`, `round()`, quantize) — boundary মান: 4.894, 4.895, 4.899, 4.90, 4.949, 4.99, 4.999, 5.00।
2. প্রয়োজন হলে calculation এক ছোট helper-এ নিয়ে সব জায়গায় সেটিই ব্যবহার করো (duplicate নয়)।
3. Boundary + F/absent case + relative-order case-এর টেস্ট লিখো (একই exam-এ একাধিক ছাত্র: 4.95, 5.00, 4.89 — GPA ও position সঠিক)।
4. সব result surface (sheet, detail, card, rank, analysis, export) একই GPA দেখায় তা টেস্ট করো।
5. নিয়মটি গাইডে লিখো: কে পাবে, কখন পাবে না, rounding, উদাহরণ।

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
python manage.py test students.tests -k gpa
python manage.py test students.test_result_analysis
python manage.py test students.tests -k grade
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `EX-06: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ০৭-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/EX-06.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- 4.895 → 4.90 (boost) না 4.89 (no boost)? সুপারিশ: ROUND_HALF_UP → 4.90 → boost; owner একবার লিখিতভাবে নিশ্চিত করবেন।
- GPA display 2 দশমিকেই থাকবে কি না (৫.০০ vs 5.00) — বর্তমান আচরণ রাখার সুপারিশ।
- এক subject A (4.00) রেখে GPA 4.90–4.99 হলে boost প্রযোজ্য কি না — বর্তমান কোড হ্যাঁ; owner নীতি নিশ্চিত করবে।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/EX-06.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
