# প্রম্পট ১৭ / ২৮ — সেশন DB-01 · Dashboard/navigation

_বিভাগ: Dashboard · ধরন: যাচাই + উন্নয়ন · নির্ভরতা: প্রম্পট ১৬ (OF-08)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ১৭ / ২৮ (prompt 17/28) — সেশন DB-01 · যাচাই + উন্নয়ন · বিভাগ: Dashboard
   পূর্ববর্তী: প্রম্পট ১৬ / ২৮ (OF-08 — Archive/promotion/certificates) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ১৮ / ২৮ (DB-02 — Developer branding)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ১৭ / ২৮ (prompt 17/28) — সেশন DB-01 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ১৮ / ২৮ (DB-02 — Developer branding) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- `dashboard` view + template override `school_system/templates/students/dashboard.html` (`DIRS` override প্যাটার্ন); quick-links card (P2-6) permission-gated।
- Sidebar: `students/templates/students/base.html` — ৭টি nav-group (Office, Attendance, Exam, Result Analysis, Accounts, Employees + Dashboard) + flyout + mobile drawer + collapse (Ctrl+B, localStorage) + print-এ hidden; institution selector session-নির্ভর।
- টেস্ট: `students/test_navigation.py`, কিছু dashboard সংখ্যার টেস্ট `students/tests.py`-এ।
- যাচাই দরকার: dashboard-এর প্রতিটি সংখ্যা আসল queryset-এর সাথে মেলে কি (active only? scoped?), N+1 query, empty state, nav entry → named URL গুলো ঠিক আছে কি (কোনো 404/NoReverseMatch নেই)।

## ২. এই সেশনের চাহিদা

- Dashboard-এর প্রতিটি stat যাচাই ও পিন করা: active ছাত্র সংখ্যা (archived বাদ), class/gender distribution, admission in-progress, আজকের attendance, month-এর receipt/voucher/salary totals, pending items — সব নির্বাচিত institution-এ scoped (admin unscoped হলে aggregate)।
- Performance: প্রতি stat-এ aggregate query (Python-এ loop করে গণনা নয়), `select_related`/`annotate` ব্যবহার; পেজে N+1 নেই।
- Empty state ও zero-division নিরাপদ (কোনো 500 নয়)।
- Navigation: প্রতিটি nav entry → বিদ্যমান named URL, permission-gated, active state সঠিক, mobile drawer/collapse কাজ করে, print-এ sidebar hidden; EX-01-এর Analysis subtab এখানে সংহত।
- Cross-link: dashboard → report/analysis পেজে প্রাসঙ্গিক লিংক (permission থাকলে)।

**নোট:** এটি integration-সেশন — নতুন design/theme নয়; বিদ্যমান UI-র নির্ভুলতা ও সংগতি।

## ৩. যা করতে হবে (ক্রমে)

1. Dashboard view-এর প্রতিটি context value ও template-এর সব সংখ্যা তালিকাভুক্ত করো; প্রতিটির queryset পড়ে সঠিকতা assert করা টেস্ট লেখো (fixture: কিছু archived, দুই institution, মাস-সীমা)।
2. Scoping যাচাই: scoped clerk-এর dashboard-এ শুধু তার institution-এর সংখ্যা; admin-এ সবার।
3. Query count মাপো (`assertNumQueries` বা debug toolbar/SQLite log) — স্পষ্ট N+1 থাকলে ঠিক করো।
4. Nav inventory টেস্ট: প্রতিটি menu entry `reverse()` করে name যাচাই + unauthorized user-এর জন্য লুকানো + direct URL guard (আগের নিয়ম)।
5. Empty নীতি: institution-এ কোনো ডেটা না থাকলে শূন্য দেখাবে, ভাঙবে না।

**বিশেষ নোট:** এই সেশনে visual redesign নয় — সংখ্যা/লিংক/performance।

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
python manage.py test students.test_navigation
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

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `DB-01: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ১৭-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/DB-01.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- Dashboard-এ কোন কার্ডগুলো আগে (priority) — owner পছন্দ; সুপারিশ: Attendance/Admission/Fees।
- Institution selector-এর default: last selected (session) নাকি first allowed — বর্তমান আচরণ রাখার সুপারিশ।
- Quick links-এ নতুন entry (Analysis/Reports) যোগ হবে কি না — permission-gated হলে সুপারিশ: হ্যাঁ।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/DB-01.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
