# প্রম্পট ২৪ / ২৮ — সেশন AT-02 · Calendar/report accuracy

_বিভাগ: Attendance · ধরন: যাচাই + উন্নয়ন · নির্ভরতা: প্রম্পট ২৩ (AT-01)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ২৪ / ২৮ (prompt 24/28) — সেশন AT-02 · যাচাই + উন্নয়ন · বিভাগ: Attendance
   পূর্ববর্তী: প্রম্পট ২৩ / ২৮ (AT-01 — Entry/correction) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ২৫ / ২৮ (EM-01 — Employee/teacher assignment)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ২৪ / ২৮ (prompt 24/28) — সেশন AT-02 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ২৫ / ২৮ (EM-01 — Employee/teacher assignment) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- `attendance_report` (records list, 100/পেজ, `status_choices`) ও `attendance_summary` (date range + rates) দুইটি আলাদা view।
- মডেল: status P/A/L/H; unique per institution+student+date (employee-এর জন্যও); কোনো কেন্দ্রীয় holiday calendar নেই (শুধু প্রতি-রেকর্ড H)।
- কোন দিনের রেকর্ড না থাকলে কী হয় (absent ধরা হবে না) — বর্তমান লজিক পরীক্ষা করে নথিবদ্ধ করতে হবে।
- **Calendar view নেই** — এই সেশনে সেটি যোগ করা হবে (server-rendered, নতুন JS library ছাড়া)।

## ২. এই সেশনের চাহিদা

- (ক) Accuracy: rate-এর denominator কী (P+A+L নাকি শুধু P+A? H বাদ?), date range inclusive boundary, class/section-wise ও employee-wise ভাগ, summary vs report একই source/হিসাব ব্যবহার করে কি না, timezone (`Asia/Dhaka`) অনুযায়ী "আজ" সঠিক, archived ছাত্র বাদ।
- (খ) ভুল/অস্পষ্ট হিসাব থাকলে smallest fix + টেস্ট; সূত্রটি ডকে ও UI-তে লেখা (কে জানে denominator কী)।
- (গ) নতুন **monthly calendar view**: institution/class/section বেছে মাসের গ্রিড — প্রতিটি দিনে রঙ-কোডেড status (P/A/L/H/রেকর্ড নেই), দিনে ক্লিক করলে সেই দিনের correction (AT-01), print-friendly, server-rendered (নতুন JS dependency নয়)।
- (ঘ) মাসিক summary/export (Excel বা CSV) — সারি/কলাম পিন করা ও টেস্ট করা।

## ৩. যা করতে হবে (ক্রমে)

1. নির্ধারিত controlled ডেটা দিয়ে হিসাব টেস্ট করো: শুধু P, P+A+L, কিছু দিন এমট (H সহ), মাসের সীমা, ২৯ ফেব্রুয়ারি, একই দিনে employee+student।
2. summary vs report মিলিয়ে দেখো — একই filter-এ একই সংখ্যা আসে কি না (না হলে এক source-এ নিয়ে আসো)।
3. Calendar view + template যোগ করো: মাস/বছর param, invalid param নিরাপদ, empty state, legend, print CSS; দিনের ক্লিক → AT-01-এর correction link (permission থাকলে)।
4. টেস্ট: boundary date (from=to, মাসের প্রথম/শেষ দিন), month rollover, H-এর প্রভাব, archived ছাত্র বাদ, scoping (অন্য institution-এর class দেখায় না), printed HTML-এ legend/amount সঠিক।
5. ডকে হিসাবের সূত্র লিখো (`docs/` + page help text)।

**সীমা:** নতুন attendance feature (biometric ইত্যাদি) নয়; শুধু calendar ও accuracy।

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
python manage.py test students.test_institution_isolation
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `AT-02: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ২৪-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/AT-02.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- Rate সূত্র: H বাদ দিয়ে (P+A+L) denominator (সুপারিশ: বাদ), L-কে present হিসেবে গণনা না আলাদা?
- Holiday কীভাবে ধরা হবে: প্রতি-রেকর্ড H নাকি institution-level holiday list (এই রিলিজে হয়তো শুধু H)?
- মাসিক summary-তে কোন কলাম লাগবে (owner-সিদ্ধান্ত)? 
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/AT-02.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
