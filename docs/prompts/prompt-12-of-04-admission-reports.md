# প্রম্পট ১২ / ২৮ — সেশন OF-04 · Admission reports

_বিভাগ: Office · ধরন: উন্নয়ন · নির্ভরতা: প্রম্পট ১১ (OF-03)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ১২ / ২৮ (prompt 12/28) — সেশন OF-04 · উন্নয়ন · বিভাগ: Office
   পূর্ববর্তী: প্রম্পট ১১ / ২৮ (OF-03 — Subject Assignment Office subtab) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ১৩ / ২৮ (OF-05 — Student photos)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ১২ / ২৮ (prompt 12/28) — সেশন OF-04 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ১৩ / ২৮ (OF-05 — Student photos) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- ইতিমধ্যে আছে: `admission_funnel_report` + `admission_funnel_export` (PR #32 merged), Office flyout-এ Admission Funnel, Admission list page-এ `📊 Reports` button (PR #33 merged), `class_section_summary`, `download_admission_sheet`।
- Funnel ধাপ: SUBMITTED → OFFICE_APPROVED → ACCOUNT_PENDING → PAYMENT_APPROVED → ENROLLED; REJECTED আলাদা; `?institution=` (bounded) + `?from=`/`?to=` (whole-day inclusive); multi-institution scope হলে export-এ "By Institution" sheet।
- টেস্ট: `students/test_admission_funnel_report.py` (২০টি দাবি করা)।
- অপশনাল / এখনো Missing: `ADM-REPORTS-OPT-1` — capacity vs enrolled (class/section), payment-vs-enrolled trend, date-wise trend chart।

## ২. এই সেশনের চাহিদা

- (ক) বিদ্যমান report-এর সংখ্যা ও সীমা যাচাই: প্রতিটি status count, date-range boundary (from/to inclusive), institution isolation, empty scope, REJECTED আলাদা থাকা, export sheet গুলোর 내용।
- (খ) Owner-অনুমোদিত উন্নয়ন (এই রিলিজে যতটুকু সিদ্ধান্ত হবে): capacity vs enrolled per class/section (`SectionCapacity` vs actual), payment-vs-enrolled ও date-wise trend — **নতুন JS chart লাইব্রেরি ছাড়া** (table/CSS bar/server-rendered SVG), Excel-এ নতুন sheet।
- (গ) ব্যর্থ/ফাঁকা কেস: কোনো data না থাকলে 0 দেখাবে (500 নয়), বড় range-এও performance যুক্তিসঙ্গত (aggregate query, N+1 নয়)।
- (ঘ) Access নীতি অপরিবর্তিত (Office/Accounts + permission), মেনু লুকানো নিরাপত্তা নয় — direct URL server-side guard-এ সুরক্ষিত।

## ৩. যা করতে হবে (ক্রমে)

1. বর্তমান funnel math টেস্ট দিয়ে যাচাই করো (fixture দিয়ে প্রতিটি status-এর সংখ্যা), boundary: একই দিন from=to, from>to, ভবিষ্যতের তারিখ।
2. Capacity হিসাব: কোন class/section-এ কত আসন vs ভর্তি (`SectionCapacity.has_room` প্যাটার্ন reuse) — নতুন helper + টেস্ট (০ আসন, অতিক্রান্ত, capacity row নেই)।
3. Trend: date-bucket boundary ও timezone (Asia/Dhaka) টেস্ট; export sheet-এ সারি/কলাম পিন করো।
4. Empty scope / one-institution / multi-institution — তিন ক্ষেত্রেই render ও export টেস্ট।
5. Scoping/permission negative টেস্ট (scoped clerk অন্য institution-এর `?institution=` দিয়ে scope বাড়াতে পারবে না)।
6. চালাও §৫; ফিচার যোগ হলে guide/doc হালনাগাদ (কীভাবে ব্যবহার, কী বোঝায়)।

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
python manage.py test students.test_admission_funnel_report
python manage.py test students.test_fee_schedule
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

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `OF-04: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ১২-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/OF-04.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- এই রিলিজে কোন নতুন report লাগবে: (খ১) capacity vs enrolled, (খ২) payment-vs-enrolled trend, (খ৩) date-wise trend — তিনটিই, নাকি শুধু একটি?
- Accounts কী পুরো funnel দেখবে নাকি payment stage-সীমিত view — এটি আগের থেকেই খোলা decision; সিদ্ধান্ত না হলে বর্তমান নীতি বহাল।
- Chart না table — সুপারিশ: table + CSS bar (কোনো নতুন dependency নয়)।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/OF-04.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
