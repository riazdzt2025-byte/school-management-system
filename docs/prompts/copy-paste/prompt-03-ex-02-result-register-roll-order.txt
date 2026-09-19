# প্রম্পট ০৩ / ২৮ — সেশন EX-02 · Result/Register roll-order

_বিভাগ: Exam · ধরন: সংশোধন · নির্ভরতা: প্রম্পট ০২ (EX-01)_

> **ব্যবহার:** নীচের সম্পূর্ণ অংশ (এই শিরোনামসহ) কপি করে এজেন্টকে দিন। এজেন্টকে উত্তর শুরুর ও শেষের স্ট্যাটাস ব্লক অবশ্যই দেখাতে হবে, যাতে বোঝা যায় কত নম্বরের প্রম্পট চলছে এবং কত নম্বরের প্রম্পট শেষ হয়েছে।

---

## ০. স্ট্যাটাস ব্লক (বাধ্যতামূলক)

উত্তরের **প্রথম লাইনেই** হুবহু এই কাঠামোয় লিখবে (কোণ-বন্ধনী পূরণ করে):

```
▶ চলছে: প্রম্পট ০৩ / ২৮ (prompt 03/28) — সেশন EX-02 · সংশোধন · বিভাগ: Exam
   পূর্ববর্তী: প্রম্পট ০২ / ২৮ (EX-01 — Import redirect ও Analysis subtab) → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড / ⏭️ চালানো হয়নি>
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ০৪ / ২৮ (EX-03 — Group-based Mark Evaluation)
```

উত্তরের **একদম শেষে** (সংক্ষিপ্ত ফলাফলের পরে) লিখবে:

```
✔ শেষ হয়েছে: প্রম্পট ০৩ / ২৮ (prompt 03/28) — সেশন EX-02 → <✅ সম্পন্ন / 🟡 আংশিক / ⛔ ব্লকড>
   প্রমাণ: <ফোকাসড টেস্ট> · পূর্ণ suite <n> Django + <m> Node · check <result>
   Commit: <sha> · PR: #<n> (<state>) · ডক আপডেট: <files>
   পরের প্রম্পট: প্রম্পট ০৪ / ২৮ (EX-03 — Group-based Mark Evaluation) — এক লাইনে কী বাকি
```

## ১. প্রেক্ষাপট (এই checkout-এ যাচাই করা অবস্থা)

- `result_sheet` (Class Performance Register) numeric roll order-এ sort করে (`roll_no is None` শেষে, tie-break name/pk), merit `position` অপরিবর্তিত — আগের সেশনে ঠিক করা (c17a45a দাবি), কিন্তু অন্য output-এ এখনো যাচাই হয়নি।
- `Student.roll_no` = `IntegerField(null=True, blank=True)` (`students/models.py` ~L227) → string-sort-এর ক্লাসিক বাগ (`'10' < '2'`) template-side `|dictsort` বা unordered queryset-এ ফিরে আসতে পারে।
- যাচাই বাকি: `result_summary` (exam_result_summary), `full_rank_list` (merit — ইচ্ছাকৃত), `top_10` (merit), `student_result_detail`, `result_card`, `class_section_summary`, `section_arrangement`, `result_analysis_result_cards`, `download_student_list` (Excel), `signature_sheet`, seat-plan print, attendance report class-wise list, এবং print CSS।
- নিয়ম (এই সেশনে আনুষ্ঠানিকভাবে লিখে ফেলা হবে): **register/roll-ভিত্তিক output = numeric roll order (roll_no, তারপর name, তারপর pk; roll_no None সবার শেষে); merit/rank output = position order।**

## ২. এই সেশনের চাহিদা

- প্রতিটি list/export/print-এর ordering নির্ধারণ করে যেখানে দরকার সেখানে numeric roll order প্রয়োগ করা, এবং যেখানে merit order ইচ্ছাকৃত সেখানে তা অপরিবর্তিত রাখা।
- Ordering determinism: একই roll-এ দুইজন থাকলে stable tie-break; pagination/exports-এ page জুড়ে duplicate/skip নেই।
- Group/section/institution filter, permission ও scoping আগের মতোই থাকবে; কোনো মান/গণনা বদলাবে না — শুধু ক্রম।
- সেশন-শেষে একটি সংক্ষিপ্ত "ordering matrix" (output → order rule → কোথায় enforced) রিপোর্টে ও সংশ্লিষ্ট view docstring-এ লেখা।

## ৩. যা করতে হবে (ক্রমে)

1. সব list/export/print output-এর inventory করো (view + template) এবং প্রতিটির বর্তমান ordering কোডে খুঁজে বের করো (`order_by`, `sorted`, `dictsort`, queryset default ordering)।
2. যেখানে ভুল/অনিশ্চিত সেখানে smallest fix: numeric roll sort helper (থাকলে reuse) — যেমন `sorted(qs, key=lambda s: (s.roll_no is None, s.roll_no or 0, s.name.lower(), s.pk))` বা `order_by(F('roll_no').asc(nulls_last=True), 'name', 'pk')`।
3. খেয়াল রাখো: `full_rank_list`/`top_10` merit order-এ থাকবে (ইচ্ছাকৃত), শুধু register/roll output numeric — কোড না ভেঙে টেস্ট দিয়ে দুটোই পিন করো।
4. Roll number 2, 10, 100, None — এই চারটি কেস দিয়ে প্রতিটি সংশ্লিষ্ট output-এ টেস্ট লেখো (string-sort trap ধরা পড়বে)।
5. Excel/print export-এ একই ক্রম যাচাই করো।
6. চালাও §৫-এর কমান্ড + নতুন টেস্ট; রিপোর্টে ordering matrix লেখো।

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
python manage.py test students.test_published_lock_and_cell_shortcut
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

- প্রতিটি কারণের জন্য ছোট commit; message-এ session ID (যেমন `EX-02: <সংক্ষিপ্ত>`)।
- `git add` করার আগে `git status` দিয়ে নিশ্চিত হবে যে `.env`/`db.sqlite3`/`media/`/`backups/` ঢুকছে না।
- `git push origin arena/01a0b7f7-school-management-system`।
- `gh pr create --base main --head arena/01a0b7f7-school-management-system` — title-এ session ID, body-তে: কী বদলেছে · কী যাচাই হয়েছে · কী যাচাই হয়নি · owner-এর করণীয়।
- merge করবে না (owner অনুমোদন সাপেক্ষে)।

## ৭. ডক ও ট্র্যাকার আপডেট (এই সেশনের অবিচ্ছেদ্য অংশ)

1. `docs/prompts/PROGRESS.md` → প্রম্পট ০৩-এর সারিতে `স্ট্যাটাস / তারিখ / Commit / PR / টেস্ট প্রমাণ / নোট` পূরণ।
2. সংশ্লিষ্ট doc entry হালনাগাদ — সাধারণত `docs/PROJECT_STATUS.md` (entry row), `docs/TASK_BACKLOG.md` (remaining list), `docs/HANDOFF.md` (নতুন সেশন-নোট)।
3. সেশন-রিপোর্ট (ছোট, ১ পৃষ্ঠা): `docs/prompts/reports/EX-02.md` — আগের অবস্থা → এখনকার অবস্থা, প্রমাণ (কমান্ড + ফল), যাচাই হয়নি এমন অংশ, বাকি ঝুঁকি, owner-সিদ্ধান্ত।
4. এই সেশনের পরের প্রম্পটটি এখনো `⏳ অপেক্ষমাণ` — সেটি কেউ নিজে থেকে শুরু করবে না; owner ক্রমিকভাবে দেবেন।

## ৮. owner-এর সিদ্ধান্ত প্রয়োজন হলে

- `download_student_list`/`class_section_summary`-তে ক্রম roll নাকি name — সুপারিশ: roll (register-ধরনের output), কিন্ত owner যদি name চান তবে সেভাবেই নথিভুক্ত হবে।
- Roll number কারো `None` থাকলে তাকে সবার শেষে দেখানো — সুপারিশ; অন্য নিয়ম চাইলে জানাও।
> সিদ্ধান্ত ছাড়া কাজ আটকে গেলে: কোড বদলাবে না, `docs/prompts/PROGRESS.md`-এ স্ট্যাটাস `⛔ ব্লকড (owner decision)` লিখবে, সিদ্ধান্ত-অনুরোধ `docs/prompts/reports/EX-02.md`-এ লিখবে (প্রশ্ন · কেন দরকার · প্রতিটি বিকল্পের প্রভাব · সুপারিশ), এবং শেষ ব্লকে পরিষ্কারভাবে বলবে।

## ৯. আউটপুট ফরম্যাট

১–২ বাক্যে ফলাফল → **পরিবর্তিত ফাইল** (তালিকা) → **যাচাই কমান্ড ও ফল** (সংখ্যা/ফলাফল) → **কী যাচাই হয়নি / বাকি ঝুঁকি** → **owner-এর করণীয় (যদি থাকে)** → **PR লিংক** → §০-এর সমাপ্তি স্ট্যাটাস ব্লক।
