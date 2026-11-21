# Assign by class — বিষয়ের গ্রিডে শিক্ষক বসানো (সেশন ২০২৬-১১-২১)

**Status: Complete (code + tests)।** Branch `arena/521f2feb-school-management-system`, base `7730a95`.

## চাওয়া হয়েছিল

> "teacher er jobno class w subject sajano thakbe paser kolame teacher dropdawun/sarch kore diye
> assain korbe eta sohoj hobe karon akoi shikkhok ekadik bisoy ba onno claser ono bosoy noye thaken"

অর্থাৎ — শিক্ষকের job no, class ও subject সাজানো থাকবে, **পাশের কলামে** শিক্ষক ড্রপডাউন/সার্চ করে
অ্যাসাইন করা যাবে। সহজ হবে, কারণ **একই শিক্ষক একাধিক বিষয় বা অন্য ক্লাসের বিষয় নেন**।

owner-এর বেছে নেওয়া আকার (ask_user-এ দুই প্রশ্ন):
1. **ক্লাস+সেকশন → বিষয়ের গ্রিড, পাশে শিক্ষক সার্চ** (একবারে সব সারি পূরণ)
2. **নিচে Save চেপে একবারে সব** (প্রতি সারিতে সাথে সাথে সেভ নয়)

## আগের অবস্থা

`TeacherAssignment` মডেল ও রেজিস্ট্রি ছিল (EM-01), কিন্তু অ্যাসাইন করার স্ক্রিন **এক সারির ফর্ম**:
শিক্ষক নম্বর টাইপ → class → section → subject → Save, প্রতিটি বিষয়ের জন্য আলাদা করে।
একই শিক্ষককে ৮টি বিষয়ে বসাতে হলে ৮ বার ফর্ম খুলে নম্বর টাইপ করতে হতো।

## এখন

### স্ক্রিন: Employees → Assign by Class (`/employees/assignments/grid/`)

- **Institution → Class → Section → Session** বেছে নিলে ঐ ক্লাসের **কারিকুলামের প্রতিটি বিষয় এক সারি**।
  সারিতে বিষয়ের নাম, group (SCI/BUS/HUM) ও ধরন (Mandatory/Optional/Conditional) pill আকারে।
- **পাশের কলামে শিক্ষক সার্চ** — job no (`2011 02 0001`), শুধু সিরিয়াল (`0001`), `02 0001`,
  বাংলা অঙ্ক (`২০১১০২০০০১`), অথবা নামের অংশ — যেটাই টাইপ করুন, নিচে ছোট তালিকা;
  তীর-চিহ্ন/Enter/ক্লিক করে বাছাই; বাছাই হলে ঘরে `2011 02 0001 · Salma Akter` বসে ও লুকানো
  `employee_<subject>` ভরে যায়।
- **একই শিক্ষক পরের খালি সারিতে সাজেশন হয়ে থাকে** — পরের সারির ঘরে ক্লিক করে Enter চাপলেই
  একই শিক্ষক বসে, নম্বর আবার টাইপ করতে হয় না (মূল চাহিদা)।
- সারির নিচে ছোট লাইন: পদবি, inactive হলে স্ট্যাটাস, এবং **"also teaches Class 10 (A) · Physics"** —
  ঐ শিক্ষক এই সেশনে অন্য কোন কোন ক্লাস/বিষয়ে আছেন (সর্বোচ্চ ৪টি)।
- **নিচে একবার Save** — একই transaction-এ সব সারি লেখা হয়।
  - খালি সারি = ঐ বিষয়ের শিক্ষক **সরানো** (hard delete নয়, `is_active=False` + audit — ইতিহাস থাকে)।
  - শিক্ষক বদল = পুরোনো সারি inactive + নতুন সারি (audit: `teacher_assignment_unassigned` + `teacher_assignment_created`)।
  - কিছু না বদলালে কিছুই লেখা হয় না (idempotent)।
- **"Clear all"** — এক ক্লিকে সব ঘর খালি (Save না করা পর্যন্ত ডেটাবেজে কিছু হয় না)।
- লেখার অনুমতি (`add_` + `change_teacherassignment`) না থাকলে গ্রিড **read-only** (readonly input,
  Save নেই, POST = 403)।
- রেজিস্ট্রি লিস্টে এখন দুই বাটন: **+ Assign by class** (নতুন) ও **+ One row** (পুরোনো এক-সারির ফর্ম),
  সাইডবারেও "Assign by Class" যুক্ত।

### নিয়ম (আগের মতোই, নতুন কিছু নয়)

- একই teacher+class+section+subject+session-এ একটির বেশি active সারি নয় (DB constraint)।
- inactive শিক্ষক, অন্য প্রতিষ্ঠানের শিক্ষক, কারিকুলামের বাইরের বিষয়ের শিক্ষক — সব POST-এ Server-side
  যাচাই হয়; এক সারিতেও ভুল থাকলে **কোনো সারিই সেভ হয় না** এবং কোন বিষয়ে কী ভুল লেখা হয়।
- section খালি = **পুরো ক্লাস** (section-ভিত্তিক সারির সাথে মেশে না)।
- প্রতিষ্ঠান-স্কোপ: clerk-এর নিজের প্রতিষ্ঠানের বাইরে POST করলে কিছুই লেখা হয় না (`_resolve_requested_institution`)।
- কারিকুলাম থেকে বাদ পড়া কিন্তু আগে assign করা বিষয়ও গ্রিডে থাকে (`not in this class's curriculum`
  pill সহ), যাতে পুরোনো সারি সরানো যায়।

## প্রমাণ

```bash
python manage.py test students.test_teacher_assignment_grid   # ২২ pass
python manage.py test students                              # ১৪১৪ pass, OK
python manage.py check                                      # 0 issue
python manage.py makemigrations --check --dry-run            # No changes detected
node --test students/js/*.test.js                           # ৮৩ pass (নতুন ২০)
```

**CI (PR #97, run 44913534666):** sqlite ✅ 9m8s · Node ✅ 5s ·
**postgres ❌** — fail-টি `Backup / restore smoke test (postgres)` ধাপে, `Run test suite (postgres)` ✅
অর্থাৎ **১৪১৪টি Django টেস্ট postgres:16-এ সব pass**; ব্যর্থতা backup smoke ধাপে, যেটি `main`-এ (run 44874631733)
একইভাবে fail করছে — অর্থাৎ এই ব্রাঞ্চের কোড-জনিত নয় (pre-existing infra/step issue, আলাদা খতিয়ান দরকার)।

| ফাইল | কী |
|---|---|
| `students/views.py` | `teacher_assignment_grid` + `_grid_rows`/`_grid_sections`/`_grid_also_map`/`_grid_teacher_rows`/`_grid_teacher_from_post`/`_apply_grid` |
| `students/urls.py` | `employees/assignments/grid/` → `teacher_assignment_grid` |
| `students/templates/students/teacher_assignment_grid.html` | নতুন স্ক্রিন |
| `students/static/students/js/teacher_assignment_grid.js` | শিক্ষক সার্চ + সাজেশন + পিক |
| `students/js/teacher_assignment_grid.test.js` | ২০টি Node টেস্ট (DOM stub) |
| `students/test_teacher_assignment_grid.py` | ২২টি Django টেস্ট |
| `students/templates/students/teacher_assignment_list.html`, `base.html` | লিংক |

## যাচাই হয়নি / ঝুঁকি

- **আসল ব্রাউজারে হাতে দেখা হয়নি** — এই sandbox-এ Playwright ব্রাউজার নামানো যায়নি (নেটওয়ার্ক ব্লক)।
  DOM/লজিক Node টেস্টে যাচাই করা, পেজটা Django টেস্ট client দিয়ে ২০০ ও প্রত্যাশিত মার্কআপ দেয়।
- টাচ/মোবাইলে ছোট স্ক্রিনে টেবিল অনুভূমিক scroll করে (৬৪০px-এর নিচে)।
- পুরোনো এক-সারির ফর্ম ও রেজিস্ট্রি লিস্ট অপরিবর্তিত — কোনো migration নেই।

## owner-এর করণীয়

- লাইভে (Render) merge-এর পর একবার খুলে দেখে নেওয়া: Employees → Assign by Class → ক্লাস বেছে →
  দুটি সারিতে একই শিক্ষক → Save।
