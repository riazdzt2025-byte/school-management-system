# রেজাল্ট দ্রুত দেখা — পরিবর্তন ও যাচাই

তারিখ: ২০২৬-১১-০১। ব্যবহারকারীর অভিযোগ: রেজাল্ট দেখতে গেলে বেশি দেরি হয়।
এটি owner-এর অনুরোধে নেওয়া আলাদা performance fix; প্রম্পট ১৭ (DB-01) সম্পন্ন নয়।

## কী কারণে দেরি বাড়ছিল

প্রতিটি শিক্ষার্থীর প্রতিটি বিষয়ের জন্য নম্বর-বণ্টনের setting আলাদা query করে আনা হতো।
শিক্ষার্থী বা বিষয় বাড়লে query সংখ্যাও গুণহারে বাড়ত। এ ছাড়া একই cohort-এর বাইরের
marks-ও আনা হতো, প্রতিটি mark-এর সঙ্গে অব্যবহৃত Student/Subject join হতো, এবং sheet-এর
header-এ একই setting আবার আনা হতো।

## কী বদলেছে

- সব বিষয়ের marks configuration একসঙ্গে আনা হয়। Group-specific setting → blank-group
  fallback → Subject default এবং `9`/`09` class spelling-এর আগের অগ্রাধিকারই থাকে।
- শুধু নির্বাচিত cohort-এর marks আনা হয়; অব্যবহৃত join বাদ। Marked-subject তালিকাও
  ওই একই mark rows থেকে তৈরি হয়।
- Official/provisional header একই bulk resolver ব্যবহার করে। Populated sheet-এ
  empty-state subject diagnosis চালানো হয় না।
- Calculation-local snapshot; কোনো persistent result cache নেই। নম্বর বা setting বদলালে
  পরের বারই নতুন মান দেখা যায়। আগের ফল জমা করে রেখে দেওয়া হয়নি।
- Bootstrap 5.3.2, Bootstrap Icons 1.11.3 এবং Inter/Fraunces-এর ব্যবহৃত font weight
  অ্যাপের own static storage থেকে আসে। Shared layout ও login-এর external CDN dependency
  সরানো হয়েছে; Student detail-এ duplicate Bootstrap bundle সরানো হয়েছে।
  Bootstrap JS deferred; font-display swap। License/version/provenance:
  `students/static/students/vendor/README.md`।

GPA, fourth-subject bonus, absent/pending, optional/religion applicability, pass/fail,
ranking/roll order, institution isolation এবং publish access policy বদলানো হয়নি।
কোনো model, migration বা দৃশ্যগত redesign নেই।

## মাপা ফল: একই কাজ, অনেক কম SQL query

একই synthetic fixture-এ ৮ ও ৮০ শিক্ষার্থী, প্রত্যেকের ১০টি mandatory বিষয়।
SQLite, Python 3.11.2 / Django 5.2.18 local fallback। সংখ্যাগুলো SQL query count,
**production-এর সেকেন্ড বা latency measurement নয়**।

| কাজ | আগে: ৮ → ৮০ জন | এখন: ৮ → ৮০ জন |
|---|---:|---:|
| Result calculation | 89 → 809 | **9 → 9** |
| Official result sheet / print | 122 → 842 | **25 → 25** |
| Summary / full rank / top 10 | 95 → 815 | **15 → 15** |
| Provisional sheet | 105 → 825 | **16 → 16** |
| Individual result detail / card | 97 → 817 | **17 → 17** |

৮০ জনের ক্ষেত্রে calculation query 809 থেকে 9 এবং official sheet 842 থেকে 25 হয়েছে।
Query সংখ্যা এখন এই fixture-এ cohort বাড়লেও বাড়ে না। Browser-এর own rendering,
নেটওয়ার্ক ও hosting latency এর বাইরে; live site-এ কত সেকেন্ড কমল তা মাপা হয়নি।

## Regression ও browser যাচাই

- `python manage.py test students --verbosity 1`: **1057 tests, OK**।
  নতুন ১০টি performance/static regressions ও একটি merged-religion provisional header test।
- `node --test students/js/*.test.js`: **29 pass, 0 fail**।
- `python manage.py check`: 0 issue; `makemigrations --check --dry-run`: no changes।
- Production-এর exact `CompressedManifestStaticFilesStorage` দিয়ে temporary directory-তে
  `collectstatic` পরীক্ষা করা হয়েছে। Hashed font URL, icon font, Bootstrap CSS/JS ও
  source-map references resolve হয়; compressed manifest তৈরি হয়।
- Chromium 143 / Playwright, synthetic 80-student database: official sheet, full print,
  summary, provisional, individual card, Student detail-এর Results tab এবং 390px mobile view যাচাই হয়েছে।
  JavaScript error, failed request বা external request পাওয়া যায়নি। Print media-তে
  sidebar hidden/main margin zero এবং A4 landscape PDF তৈরি হয়েছে। আসল প্রিন্টার ও
  production hosting যাচাই করা হয়নি।

Regression চালাতে:

```bash
python manage.py test students.test_result_performance
python manage.py test students.tests.ReligionPaperTests
python manage.py test students
node --test students/js/*.test.js
```

## Deploy করার সময়

স্বাভাবিক Render build command-এ অবশ্যই static collection থাকতে হবে:

```bash
pip install -r requirements.txt && python manage.py collectstatic --noinput
```

এরপর বিদ্যমান `./scripts/render_start.sh` ব্যবহার করা যায়। পুরোনো/অসম্পূর্ণ
`staticfiles/` থাকলে `collectstatic --noinput` আবার চালান। শুধু Python code copy করে
manifest/static assets update না করলে নতুন local asset URL পাওয়া যাবে না।

এই পরিবর্তন নিজে production deploy বা merge করা হয়নি। Live Render speed, hosting
cold start, database network latency ও real-school data volume আলাদাভাবে যাচাই করতে হবে।
