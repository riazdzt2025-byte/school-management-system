# প্রম্পট ১৯ / ২৮ — সেশন DB-03 · Permissions ও data isolation

_বিভাগ: মূল ব্যবস্থা · ধরন: নিরাপত্তা · নির্ভরতা: প্রম্পট ১৮ (DB-02)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ১৯ / ২৮ (prompt 19/28) — সেশন DB-03 · নিরাপত্তা · বিভাগ: মূল ব্যবস্থা
   পূর্ববর্তী: প্রম্পট ১৮ / ২৮ (DB-02 — Developer branding) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ২০ / ২৮ (DB-04 — Settings ও CI)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ১৯ / ২৮ (prompt 19/28) — সেশন DB-03 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ২০ / ২৮ (DB-04 — Settings ও CI) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- Single source: `students/permissions.py::_group_permission_map()`; `post_migrate → ensure_default_groups()`; `setup_groups` delegate করে (P0-11)।
- `InstitutionAccess(user, institution, department, is_active)`; department ∈ Office/Exam/Accounts/HR/Audit (Admission → Office alias); `sync_user_department_permissions` login-এ চলে।
- Scoping helpers: `_institutionally_scoped`, `_scoped_institution_ids`, `_get_scoped_object_or_404`, `_resolve_requested_institution`, `_scope_by_allowed_institutions`, `_scope_institution_qs`, `_visible_institutions`, `_selected_institution_for_request`, `_scope_write_queryset`।
- টেস্ট: `students/test_institution_isolation.py` (16 read), `test_institution_write_isolation.py` (52 write), `test_audit_log_scoping.py` (11) — মোট ~৬৮ দাবি।
- খোলা (আগের সেশনের নোট): **SEC-FU-1** — rate-limit counters LocMemCache-এ (per-process, restart-এ হারায়) → shared cache-এ নেওয়া দরকার; **SEC-FU-2** — `sync_user_department_permissions` শুধু Office/Exam/Accounts ম্যাপ করে, তাই HR/Subjects/Audit group InstitutionAccess user-এর কাছে login-এ মুছে যায় (intentional কি না — policy)।
- `_client_ip` right-most XFF entry-তে key করে (SEC-IP fix) — live behaviour owner যাচাই করবেন (P0-7)।

## ২. এই সেশনের চাহিদা

- একটি **guard matrix** তৈরি করা: প্রতিটি view (read/write/bulk/export/print/API) × (login, permission, department, institution scope) — কোথাও ফাঁক থাকলে smallest fix + negative টেস্ট।
- গার্ড থাকা টেস্ট দিয়ে শক্তভাবে পিন করা: anonymous → 302 login, permission ছাড়া → 403, wrong department → 302 dashboard, cross-institution → 404/খালি, direct URL দিয়ে menu-bypass কাজ করবে না।
- **SEC-FU-1** বন্ধ করা: rate-limit counters প্লাগেবল shared cache (env flag, default LocMem = dev, production-এ Redis/DB cache অপশন); lockout থ্রেশহোল্ড অপরিবর্তিত; টেস্টে cache reset/সব worker-এর মতো behaviour।
- **SEC-FU-2** সিদ্ধান্ত: HR/Subjects/Audit group mapping যোগ করা, নাকি intentional সীমা হিসেবে ডকে লিখে রাখা (login-এ strip হলে স্পষ্ট error?)।
- `subject_requirements_json` API, export, print — সব surface-এ scope যাচাই (এগুলো প্রায়ই ভুলে যায়)।

## ৩. যা করতে হবে (ক্রমে)

1. `urlpatterns` থেকে প্রতিটি named route-এর view তুলে একটি matrix বানাও; প্রতিটি entry-র জন্য কোন guard/scoping ব্যবহার হচ্ছে তা কোড থেকে যাচাই করো (সন্দেহ হলে টেস্ট লিখে প্রমাণ)।
2. ফাঁকা গার্ড: fix + negative টেস্ট (জনপ্রতিনিধি নয় — actual HTTP request করে 302/403/404 assert করো)।
3. SEC-FU-1: `RATE_LIMIT_CACHE`/`CACHE_URL` env flag ডিজাইন; শুধু তখনই যোগ করো যখন default আচরণ অপরিবর্তিত থাকে; টেস্ট: counter persist (cache backend), reset behavior, limit exceeded।
4. SEC-FU-2: owner সিদ্ধান্ত অনুযায়ী map প্রসারিত করো বা `docs/`-এ "intentional limitation" লিখো + টেস্ট (login-এ strip হলে user যা হবে তাতেই)।
5. `subject_requirements_json`-সহ প্রতিটি JSON/export endpoint-এ cross-institution request দিয়ে টেস্ট।
6. ফলাফল ম্যাট্রিক্স `docs/prompts/reports/DB-03.md`-এ (প্রমাণ টেবিল) + `docs/PROJECT_STATUS.md`-এর নিরাপত্তা সেকশন হালনাগাদ।

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
python manage.py test students.test_institution_isolation
python manage.py test students.test_institution_write_isolation
python manage.py test students.test_audit_log_scoping
python manage.py test students.test_rate_limiting
python manage.py test students.test_security_settings
python manage.py check
python manage.py makemigrations --check
python manage.py test students
node --test students/js/*.test.js
```

- Baseline ধরা হয় ≈৬২৫ Django + ≈১৪ Node (সেশন ০০-এর যাচাই সেটি নিশ্চিত/সংশোধন করবে)। নতুন টেস্ট যোগ হলে প্রকৃত সংখ্যা ডকে ও স্ট্যাটাস ব্লকে লিখবে।
- কোনো কমান্ড fail করলে লুকাবে না — root cause-সহ লিখবে এবং সেশন বন্ধ করার আগে ঠিক করার চেষ্টা করবে; না পারলে স্ট্যাটাস **🟡 আংশিক**।
- **CI:** PR-এ `.github/workflows/tests.yml` (sqlite + postgres:16 + Node) pass হতে হবে; `gh pr checks <PR>` দিয়ে যাচাই করে ফল PROGRESS.md-এ লিখবে।

## ৬. commit, push ও PR

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `DB-03: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ১৯-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/DB-03.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- SEC-FU-1-এ production cache backend: Redis (বহিঃসেবা, খরচ) নাকি DB cache (কোনো নতুন সেবা নয়) — সুপারিশ: Redis না থাকলে DB cache অপশন।
- SEC-FU-2: HR/Subjects/Audit group map করা হবে কি না (HR user login-এর চাহিদা থাকলে হ্যাঁ)?
- নতুন department-এর permission set চূড়ান্ত (permissions.py-তে এক স্থানে) — owner-নিশ্চিতকরণ।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/DB-03.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
