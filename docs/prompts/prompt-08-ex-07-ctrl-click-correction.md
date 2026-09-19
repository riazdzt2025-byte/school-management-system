# প্রম্পট ০৮ / ২৮ — সেশন EX-07 · Ctrl/Cmd+Click correction

_বিভাগ: Exam · ধরন: নতুন সুবিধা · নির্ভরতা: প্রম্পট ০৭ (EX-06)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ০৮ / ২৮ (prompt 08/28) — সেশন EX-07 · নতুন সুবিধা · বিভাগ: Exam
   পূর্ববর্তী: প্রম্পট ০৭ / ২৮ (EX-06 — GPA 4.90–5.00 → 5.00) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ০৯ / ২৮ (OF-01 — একটি Guardian Contact)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ০৮ / ২৮ (prompt 08/28) — সেশন EX-07 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ০৯ / ২৮ (OF-01 — একটি Guardian Contact) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- কোড আছে: `students/js/result_cell_shortcut.js` + Node টেস্ট `students/js/result_cell_shortcut.test.js`; `result_sheet.html`-এর subject cell-এ `data-subject-pk` (Religion cell তার নিজের paper-এর pk, REL column নয়) ও `data-group`; container-এ `data-enter-marks-base`।
- Django টেস্ট: `students/test_published_lock_and_cell_shortcut.py`; published-marks lock R1 (PR #30) একই সেশনে এসেছে।
- Ctrl/Cmd+Click করলে target subject-এর `enter_marks` page **নতুন tab**-এ খোলে; plain click/print আচরণ অপরিবর্তিত রাখা হয়েছে।
- অজানা/যাচাইযোগ্য বাকি: `full_rank_list`/`student_result_detail`/`result_card`-এ shortcut নেই; permission না থাকলে link খোলা উচিত নয়; unpublished exam-এ behavior; group-less exam-এ group param; mobile/touch আচরণ।

## ২. এই সেশনের চাহিদা

- বৈশিষ্ট্যটি যাচাই করে আরও নির্ভরযোগ্য করা: সঠিক cell → সঠিক subject + group + exam-এর `enter_marks` URL; other exam/institution-এ যেতে পারে না (server-side scoping অপরিবর্তিত)।
- শর্ত: ব্যবহারকারীর `add_exammark`/`change_exammark` permission থাকলে তবেই target render হবে; না থাকলে cell plain থাকবে (কোনো লুকানো URL নয়)।
- Published lock: unpublished exam-এ shortcut কাজ করবে না (বা exam-publish page/লবিতে ভদ্র বার্তা) — lock ভাঙা যাবে না।
- Plain click, Ctrl/Cmd+Click, Shift+Click, middle-click, print — সব কেস স্পষ্টভাবে নির্ধারিত; Ctrl/Cmd+Click ছাড়া normal click কোনো navigation করবে না (register পড়ার অভিজ্ঞতা নষ্ট হবে না)।
- Accessibility fallback: যারা keyboard shortcut চান না/পারেন না, ওরা যাতে page থেকে enter_marks-এ যেতে পারে (row/cell থেকে visible link বা button) — এটাই আসল নিরাপত্তা নয়, শুধু usability।
- Mobile/touch: দুর্ঘটনাবশত correction page খুলে না যায়।

## ৩. যা করতে হবে (ক্রমে)

1. প্রতিটি result template যাচাই করো: কোনটিতে JS আছে, `data-*` attribute ঠিক আছে কি না; কোথাও `data-group` মিলছে কি না (group-less exam-এ group খালি → behavior নির্ধারণ করো)।
2. permission-gated rendering নিশ্চিত করো (template-এ perms চেক + server-side guard আগে থেকেই আছে কি না দেখো)।
3. Node টেস্ট সম্প্রসারিত করো: plain click no-op, Ctrl/Cmd খোলে, modifier+other key খোলে না, missing data attribute-এ নিরাপদ (no crash)।
4. Django টেস্ট: permission ছাড়া cell-এ data/text অনুপস্থিত; unpublished exam-এ behavior; cross-institution URL tamper → server 404/403 (নিরাপত্তা টেস্ট)।
5. গাইডে শর্টকাটটি লেখো (`RESULT_PUBLISHING_GUIDE.md`): কীভাবে ব্যবহার, কোন পেজে, সীমাবদ্ধতা।

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
node --test students/js/result_cell_shortcut.test.js
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

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `EX-07: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ০৮-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/EX-07.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- শর্টকাটটি শুধু register-এ (সুপারিশ) থাকবে, নাকি detail/card/rank page-এও চালু হবে?
- Mobile-এ আচরণ: বন্ধ রাখা (সুপারিশ) নাকি long-press দিয়ে চালু?
- Permission সেট: শুধু `add_exammark` নাকি `change_exammark` থাকলেও? (repo-র permission মানচিত্র দেখে সিদ্ধান্ত ও নথিভুক্ত করা)।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/EX-07.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
