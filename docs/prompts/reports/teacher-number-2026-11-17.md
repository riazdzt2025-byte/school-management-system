# শিক্ষক নম্বর — Assign Teacher স্ক্রিন (সেশন ২০২৬-১১-১৭)

**Status: Complete (code + tests + docs)।** Branch `arena/de3d4d37-school-management-system`, base `ecb9b77`.

## চাওয়া হয়েছিল

"শিক্ষক নম্বর ইনপুট" — কম অপশন, স্মুথ। চারটি সিদ্ধান্ত owner দিয়েছেন:

| প্রশ্ন | সিদ্ধান্ত |
|---|---|
| ফরম্যাট | **২০১১ (প্রতিষ্ঠা সাল) দিয়ে শুরু হওয়া লম্বা আইডি** — যেমন `2011 000 001` |
| ইউনিক স্কোপ | **পুরো সিস্টেমে একটাই ইউনিক** (প্রতি প্রতিষ্ঠানে আলাদা নয়) |
| কোথায় বসবে | **শুধু Assign Teacher ফর্মে** (নম্বর ইনপুট), সাথে Employee তালিকা/বিবরণে দেখা যাবে |
| সার্চে কারা | **শুধু শিক্ষক** (`designation`-এ "Teacher") — আয়া/কেয়ারটেকার/হিসাবরক্ষক নয় |

## আগের অবস্থা (যাচাই করা)

`Employee` মডেলে **শিক্ষকের কোনো নম্বর/আইডি ফিল্ডই ছিল না** — শুধু নাম, পদবি, বিভাগ, প্রতিষ্ঠান, যোগদান, মোবাইল, স্ট্যাটাস।
Assign Teacher ফর্মে ছিল **৭টি ঘর**: Institution · Employee (সব কর্মচারীর লম্বা ড্রপডাউন) · Class (হাতে টাইপ) · Section (হাতে টাইপ) · Subject (সব বিষয়) · Session (প্রতিবার টাইপ) · Active।
ডেটাবেজে `'9'` ও `'09'` — দুই spelling-ই আছে, তাই শ্রেণি যাচাইয়ে spelling-tolerant তুলনা লাগে (`class_filter_variants`)।

## এখন

**১. নম্বর তৈরি হয় একবার, কখনো দুবার নয়**
- `Employee.teacher_no` — `unique`, খালি থাকলে `NULL` (unique text column-এ একটাই `''` ঢোকে, তাই অশিক্ষক কর্মচারীরা `NULL` পান)।
- ফরম্যাট: `2011` + ৬ সংখ্যার সিরিয়াল → `2011000001`, স্ক্রিনে/প্রিন্টে দেখায় `2011 000 001`।
- কাউন্টার = বিদ্যমান `DocumentSequence` (scope `TEACHER`), `select_for_update` দিয়ে lock করা; কাউন্টার কখনো পিছায় না ⇒ **অবসর/ডিলিট করা শিক্ষকের নম্বর আবার কাউকে দেওয়া হয় না**।
- হাতে বসানো/ইমপোর্ট করা নম্বর কাউন্টারকে টেনে ওপরে তোলে (`seed`), প্রথম allotment কখনো পুরোনো নম্বরে ধাক্কা খায় না।
- প্রথম save-এ allot হয়; পরের কোনো edit/status change নম্বর বদলায় না। `update_fields` দিয়ে আংশিক write-এ কাউন্টার খরচ হয় না।

**২. অশিক্ষক কর্মচারী নম্বর পান না** — `designation`-এ `teacher` (case-insensitive) না থাকলে `NULL`। কেয়ারটেকার→শিক্ষক পদে বদলালে পরের save-এ নম্বর পেয়ে যান।

**৩. Assign Teacher স্ক্রিন — একটাই আসল প্রশ্ন**

| আগে | এখন |
|---|---|
| Institution ড্রপডাউন | লুকানো — শিক্ষকের রেকর্ড থেকেই সেট হয় |
| Employee ড্রপডাউন (সব কর্মচারী) | **শিক্ষক নম্বরের বাক্স**, সাথে টাইপের সময়েই নাম+পদবি+স্ট্যাটাস |
| Class (হাতে) | আগের মতো, তালিকা প্রতিষ্ঠানের শ্রেণি থেকে |
| Section (হাতে) | শ্রেণি বাছলে **সেই শ্রেণিরই সেকশন** datalist-এ |
| Subject (সব বিষয়) | **শুধু সেই শ্রেণির কারিকুলাম**; বাইরের বিষয় আর দেখায় না |
| Session (প্রতিবার টাইপ) | **চলতি সেশন অটো-ভরা** (জুলাইয়ে বছর শুরু), `<details>`-এ লুকানো |
| Active চেকবক্স | লুকানো, ডিফল্ট চালু |

**টাইপ করার নিয়ম** — `2011 000 001`, `2011-000-001`, `2011.000.001`, বাংলা অঙ্ক `২০১১০০০০০১`, আর শুধু সিরিয়াল `1` — সবই একই শিক্ষককে খোঁজে; আংশিক নম্বরে ছোট তালিকা (তীর/Enter/ক্লিক), ভুল নম্বরে স্পষ্ট বার্তা "No teacher has the number…"। টাইপিংয়ে কোনো network call নেই — শিক্ষক-তালিকা পেজের সাথেই আসে (`json_script`)।
JS বন্ধ ব্রাউজারের জন্য `teacher-lookup/` endpoint (GET, permission-gated, শুধু নিজের প্রতিষ্ঠানের শিক্ষক)।

**৪. সার্ভার-সাইড (JS-এর উপর ভরসা নয়)**
- `teacher_no` টাইপ করা নম্বরই একমাত্র কর্তৃপক্ষ: employee **ও** institution দুটোই সেট থেকেই সেট হয় — লুকানো `<select>` কারচুপি করলে কিছু হয় না।
- ভুল/ফাঁকা নম্বর, অজানা নম্বর, নিষ্ক্রিয় (RESIGNED/DEMOTED/OSD) শিক্ষক — সব আলাদা বার্তা, কিছুই সেভ হয় না।
- শ্রেণি প্রতিষ্ঠানের বাইরে হলে আটকায়; `09` লিখলে প্রতিষ্ঠানের নিজের label (`9`) সেভ হয়।
- আগের duplicate-আটকানো এখন বিষয়ের নাম নিয়ে বলে: "Salma Akter already teaches Physics to class 9 (A) in 2026-2027."

**৫. নম্বর দেখা যায়** — Employee List-এ "Teacher No." কলাম, Employee detail-এ "Teacher number", Employee অ্যাড/এডিট ফর্মে read-only (কাউন্টারই দেয়, কেউ বানাতে/বদলাতে পারে না), Django admin-এ list/search।

## প্রমাণ

- নতুন `students/test_teacher_number.py` — **৪৭** (ফরম্যাট/normalise, allotment ও অ-পুনর্ব্যবহার, হাতে-বসানো নম্বর respect, অশিক্ষক = `NULL`, স্ক্রিনের ঘর-কমা, সব টাইপিং ভ্যারিয়েন্ট, ভুল/অজানা/নিষ্ক্রিয়, কারচুপি করা hidden select, `09`, duplicate বার্তা, edit prefill/switch, lookup endpoint ও permission, list/detail/form display)।
- নতুন `students/js/teacher_number_picker.test.js` — **৩০** Node টেস্ট (stub DOM)।
- `students/test_teacher_assignment.py` (EM-01) নতুন কন্ট্রাক্টে হালনাগাদ — ১২ pass।
- **পূর্ণ suite: ১২৯১ Django + ৫৯ Node pass**; `check` 0 issue; `makemigrations --check` clean (leaf `0057`).
- লোকাল `runserver`-এ সত্যিকারের লগইন করে পেজ রেন্ডার যাচাই (lookup JSON, sections `{"9": ["A"]}`, subjects, সেশন `2026-2027`)।

## Owner-কে জানানো দরকার

- **নম্বর একবার দেওয়া হলে বদলানো যায় না** (UI-তে)। ভুল নম্বর ঠিক করতে হলে এখন Django admin/DB — দরকার হলে "নম্বর বদল" ফ্লো পরের কাজ।
- পুরোনো শিক্ষকদের নম্বর **লেজি-অ্যালোকেট**: যাঁর রেকর্ড আগে থেকে আছে, তিনি নম্বর পাবেন শুধু পরেরবার সেভ হলে (ফর্ম/স्ट্যাটাস বদল)। সবাইকে একসাথে নম্বর দিতে চাইলে একটা data migration চালানো যাবে — এটা owner-সিদ্ধান্ত।
- নম্বর এখনই কোথাও **প্রিন্ট হয় না** (salary sheet/signature sheet/ID card) — owner শুধু Assign ফর্ম চেয়েছিলেন, তাই ছোঁয়া হয়নি। চাইলে পরের ধাপ।
- আসল ব্রাউজারে হাতে (মোবাইল কিবোর্ড, বাংলা IME) যাচাই হয়নি — Node DOM-stub + Django render টেস্টে প্রমাণিত।

## ফাইল

`students/models.py` (field + allotment + `normalize/display_teacher_number`, `current_academic_session`), `forms.py` (`TeacherAssignmentForm` নতুন করে, `EmployeeForm`-এ read-only নম্বর), `views.py` (`_teacher_assignment_form_context`, `_assignment_sessions`, `teacher_number_lookup`), `urls.py`, `admin.py`, `templates/students/teacher_assignment_form.html` (নতুন), `employee_list.html`, `employee_detail.html`, `static/students/js/teacher_number_picker.js`, migrations `0056`/`0057`, টেস্ট দুটি + EM-01 টেস্ট হালনাগাদ।

## CI (PR #90)

- `test (sqlite, 3.12)` ✅ — পুরো ১২৯১ Django টেস্ট pass।
- `test (postgres, 3.12)` — **`Run test suite (postgres)` ✅ pass** (আসল Postgres-এও সব টেস্ট pass)। fail হয়েছে শুধু **`Backup / restore smoke test (postgres)`** ধাপে, যা `main`-এও আগের তিনটি run-এ (base commit `ecb9b77` সহ) একইভাবে fail — এই পরিবর্তনের সাথে সম্পর্কহীন।
- `Node row-action button tests` ✅ (৬s) — `node --test students/js/*.test.js` এখন ৫৯টি টেস্ট চালায় (৩০ নতুন)।
