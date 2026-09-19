# প্রম্পট ০১ / ২৮ — সেশন ০০ · সর্বশেষ checkout থেকে বাকি কাজ নির্ধারণ (baseline)

_বিভাগ: প্রাথমিক · ধরন: যাচাই · নির্ভরতা: —_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ০১ / ২৮ (prompt 01/28) — সেশন ০০ · যাচাই · বিভাগ: প্রাথমিক
   পূর্ববর্তী: — (এটি প্রথম প্রম্পট; আগের কোনো সেশন নেই)
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ০২ / ২৮ (EX-01 — Import redirect ও Analysis subtab)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ০১ / ২৮ (prompt 01/28) — সেশন ০০ → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ০২ / ২৮ (EX-01 — Import redirect ও Analysis subtab) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- বর্তমান checkout: branch `arena/01a0b7f7-school-management-system`, base `f64194a` = `origin/main` (Merge PR #33; PR #32 ও #33 দুটোই MERGED)।
- আগের সেশনগুলোর দাবি: ৬২৫ Django + ১৪ Node টেস্ট pass, `check` 0 issue, `makemigrations --check` clean — কিন্তু **এই checkout-এ নিজে চালিয়ে যাচাই করা হয়নি**, তাই সব দাবিই এখন "Unverified"।
- স্যান্ডবক্স: Python 3.11.2, Node v22.22.3, Django ইনস্টল নেই। `requirements.txt` পিন করে `Django==6.1` (Python 3.12+), তাই README-এর documented fallback লাগবে (`Django>=5.2,<6`)।
- ডকুমেন্টেশন শেষ হালনাগাদ ২০২৬-০৯-১৭ (`44cbcc3`) — অর্থাৎ এই checkout (`f64194a`) থেকে পিছিয়ে; নতুন release plan-এর জন্য তাজা baseline দরকার।
- পরিকল্পনার ২৮টি সেশনের মধ্যে বেশ কিছু আইটেম ইতিমধ্যে কোডে থাকতে পারে — উদাহরণ: GPA boost (`students/result_utils.py` ~L925-930), pagination 100 (`student_list`/`archived_students`/`employee_list`/`attendance_report`), guardian contact unification (`0039`–`0042`), admission funnel report (`admission_funnel_report` + export), Ctrl/Cmd+Click (`students/js/result_cell_shortcut.js`)। এগুলো নতুন করে বানানো এই সেশনের কাজ নয় — খুঁজে বের করে "ইতিমধ্যে আছে" বলা এবং ঘাটতি চিহ্নিত করা কাজ।

## ২. এই সেশনের চাহিদা

- এই checkout-এর প্রকৃত অবস্থা যাচাই করে **২৮-সেশন পরিকল্পনার প্রতিটি আইটেমকে** `Complete / Partial / Missing / Unverified` শ্রেণীতে ফেলা, প্রমাণসহ (ফাইল:লাইন, ভিউ/ফাংশন নাম, টেস্ট নাম)।
- কী কী ইতিমধ্যে সম্পন্ন, কী আসলে বাকি, কোনটি owner-সিদ্ধান্ত ছাড়া শুরু করা যাবে না — এই তিনটি তালিকা পরিষ্কার করা।
- পরিকল্পনার পরের সেশনগুলো যাতে ভুল দাবির উপর দাঁড়িয়ে অপ্রয়োজনীয় কাজ না করে, সেজন্য প্রতিটি আইটেমের "এখনকার অবস্থা → দরকার কি না" সংক্ষেপে লেখা।
- এই সেশন **শুধু যাচাই ও ডকুমেন্টেশন** — কোনো ফিচার কোড, migration বা live কাজ নয়।

## ৩. যা করতে হবে (ক্রমে)

1. `git fetch origin --prune`, `git status`, `git rev-parse HEAD origin/main`, `git log --oneline -3` — branch ও base নিশ্চিত করা (কোনো checkout/reset নয়)।
2. §৫-এর isolated venv বানিয়ে (Django 5.2.x fallback) `check`, `check --deploy` (dev: ~৬ warning প্রত্যাশিত), `makemigrations --check`, পূর্ণ `test students`, `node --test students/js/*.test.js` চালানো; প্রকৃত সংখ্যা ও সময় লিপিবদ্ধ করা।
3. Inventory করা: `students/urls.py` (সব route), `students/views.py` (guard/scoping helper), `students/models.py` + `students/migrations/*` (শেষ leaf 0043 কি না), templates (কোনটি `school_system/templates` override করছে), `students/test_*.py` (২৩টি ফাইল), `.github/workflows/tests.yml`।
4. ২৮টি সেশনের প্রতিটির জন্য verdict লেখা — বিশেষভাবে যাচাই করবে: EX-01 (import redirect stay-on-page আছে কি), EX-02 (numeric roll order কোথায় কোথায়), EX-03 (`SubjectMarkSetting`-এ group field আছে কি — মনে হচ্ছে নেই), EX-05 (`EXAM_ABSENT_SUBJECT_FAILS` default ও AB display), EX-06 (GPA boost boundary), EX-07 (shortcut কোন কোন page-এ), OF-01…OF-08 (প্রতিটির code প্রমাণ), DB-01…DB-06, AT-01/02 (calendar view নেই বলে অনুমান — যাচাই করো), EM-01/02/03 (teacher assignment/leave/closed-period নেই বলে অনুমান — যাচাই করো), FN-01।
5. ফলাফল লেখা: `docs/prompts/reports/০০-baseline.md` (বিস্তারিত matrix + প্রমাণ), `docs/prompts/PROGRESS.md`-এ সারি ০১ হালনাগাদ, এবং `docs/PROJECT_STATUS.md`-এ একটি সংক্ষিপ্ত dated section (Verification) + `docs/TASK_BACKLOG.md`-এর remaining list সংশোধন।
6. কোনো আইটেম ইতিমধ্যে সম্পন্ন হলে PROGRESS.md-এর নোটে লিখবে `যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে`।

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
python manage.py check
python manage.py check --deploy   # DEBUG=True সহ dev expectation লিপিবদ্ধ করতে
python manage.py test students --verbosity 1
node --test students/js/*.test.js
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `০০: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ০১-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/০০.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- এই সেশনে নতুন policy সিদ্ধান্ত নয়। যদি কোনো পরিকল্পিত আইটেম ইতিমধ্যে সম্পন্ন/অপ্রযোজ্য দেখায়, শুধু তা ledger-এ লেখা হবে — কেউ নিজে থেকে নিয়ম বদলাবে না।
- baseline-এ কোনো টেস্ট fail করলে তার root cause লিখবে এবং সেসম্পর্কে owner-প্রশ্ন তুলবে (এই সেশন ঠিক করার সেশন নয়, তবে fail লুকানো যাবে না)।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/০০.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
