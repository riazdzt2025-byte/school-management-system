# প্রম্পট প্ল্যান — প্রথম production release (২৮ সেশন)

_তৈরি: ২০২৬-০৯-১৯ · branch `arena/01a0b7f7-school-management-system` · base `f64194a` = `origin/main` (Merge PR #33)_

এই ফোল্ডারে আপনার দেওয়া সেশন-টেবিলকে **ক্রমানুসারে চালানো যায় এমন ২৮টি prompt**-এ ভাঙা হয়েছে। প্রতিটি prompt স্বয়ংসম্পূর্ণ: প্রেক্ষাপট (এই checkout-এ যাচাই করা কোড-প্রমাণসহ), চাহিদা, ধাপ, সীমা ও নিয়ম, টেস্ট কমান্ড, PR/CI নিয়ম, ডক আপডেট, এবং owner-সিদ্ধান্তের প্রশ্ন।

---

## ০. দ্রুত খোঁজার তালিকা (সবচেয়ে আগে পড়ুন)

| কী চাই | কোথায় |
|---|---|
| **২৮টি প্রম্পটের ক্লিকযোগ্য লিংক** (md · কপি-টেক্সট · START · Word) | `docs/prompts/LINKS.md` — অথবা GitHub: [`LINKS.md`](https://github.com/riazdzt2025-byte/school-management-system/blob/main/docs/prompts/LINKS.md) |
| কোন প্রম্পট চলছে/শেষ | `docs/prompts/PROGRESS.md` |
| নতুন সেশনে শুরু (মাত্র ২টি জিনিস) | `docs/prompts/HANDOFF-START.md` |
| নম্বর/সেশন/শব্দ দিয়ে প্রম্পট বের করা (এজেন্ট বা টার্মিনাল) | `python3 scripts/show_prompt.py 4` (বা `EX-03`, `gpa`) |
| লিংক তালিকা হালনাগাদ (merge-এর পরে `main`) | `python3 scripts/prompt_links.py --branch main` |

> এজেন্টকে শুধু বললেই হবে: **“প্রম্পট ০৪ দাও”** — সে `LINKS.md`/`show_prompt.py` দিয়ে এক ধাপে সঠিক প্রম্পট + START-ব্লক বের করে দেবে।

## ১. কীভাবে ব্যবহার করবেন

0. **নতুন সেশনে শুরু করতে হলে** `docs/prompts/HANDOFF-START.md` পড়ুন — মাত্র **দুইটি** জিনিস পাঠাতে হয়:
   (১) `docs/prompts/copy-paste/kickoff/prompt-<NN>-START.txt` (সংখ্যা-ভরা, তৈরি করা) এবং
   (২) `docs/prompts/copy-paste/prompt-<NN>-*.txt` (বা `docs/prompts/prompt-<NN>-*.md`)।
   বাকিটা repo (PROGRESS.md + reports) থেকেই নতুন এজেন্ট নিজে পড়ে ও যাচাই করে — আগের কথোপকথন মনে না থাকলেও সমস্যা নেই।
1. **ক্রম ভাঙবেন না।** ০১ → EX-01…EX-07 → OF-01…OF-08 → DB-01…DB-06 → AT-01…AT-02 → EM-01…EM-03 → FN-01 (সর্বশেষ)।
2. একবারে **একটি** prompt কপি করে এজেন্টকে দিন (file-এর পুরোটা, শিরোনামসহ)।
3. এজেন্ট উত্তরের **প্রথম লাইনে** লিখবে `▶ চলছে: প্রম্পট ০N / ২৮ …` এবং **শেষে** `✔ শেষ হয়েছে: প্রম্পট ০N / ২৮ …` — এই দুই ব্লক দেখেই বুঝবেন কত নম্বরের prompt চলছে/শেষ হয়েছে।
4. সেশন শেষ হলে এজেন্ট `PROGRESS.md`-এর নিজের সারি (স্ট্যাটাস/তারিখ/commit/PR/টেস্ট প্রমাণ) আপডেট করবে। **সেটিই স্থায়ী রেকর্ড।**
5. কোনো সেশন `⛔ ব্লকড (owner decision)` হলে তার decision-অনুরোধপত্র `reports/<সেশন>.md`-এ লেখা থাকবে — সিদ্ধান্ত দিয়ে আবার সেটিই চালাবেন।
6. সেশন শেষে owner হিসেবে আপনি ঠিক করবেন: PR merge করবেন কি না (এজেন্ট নিজে merge করবে না)।

## ২. নম্বর, স্ট্যাটাস ও "কত নম্বর চলছে / শেষ"

| প্রতীক | অর্থ |
|---|---|
| `▶ পরবর্তী` | যে prompt এখন চালানোর কথা (ledger-এ শুধু একটি) |
| `⏳ অপেক্ষমাণ` | এখনো শুরু হয়নি |
| `🔄 চলছে` | এই মুহূর্তে চলেছে |
| `✅ সম্পন্ন` | কোড + টেস্ট + ডক যাচাই হয়েছে (প্রমাণ ledger-এ) |
| `🟡 আংশিক` | কিছু হয়েছে, কিছু বাকি |
| `⛔ ব্লকড` | owner-সিদ্ধান্ত/বাহ্যিক কারণে আটকে আছে |
| `⏭️ বাদ (প্রযোজ্য নয়)` | যাচাই করে দেখা গেছে ইতিমধ্যেই সম্পন্ন — কাজ লাগেনি |

প্রতিটি prompt-এ স্ট্যাটাস ব্লকের কাঠামো একই:

```
▶ চলছে: প্রম্পট ০৩ / ২৮ (prompt 03/28) — সেশন EX-02 · সংশোধন · বিভাগ: Exam
   পূর্ববর্তী: প্রম্পট ০২ / ২৮ (EX-01 — Import redirect ও Analysis subtab) → ✅ সম্পন্ন
   এই প্রম্পট: 🔄 চলমান · পরবর্তী: প্রম্পট ০৪ / ২৮ (EX-03 — Group-based Mark Evaluation)
```

## ৩. সূচি (২৮ প্রম্পট)

| # | সেশন | বিভাগ | ধরন | শিরোনাম | ফাইল | নির্ভরতা |
|---|------|-------|------|---------|------|----------|
| ০১ | ০০ | প্রাথমিক | যাচাই | সর্বশেষ checkout থেকে বাকি কাজ নির্ধারণ (baseline) | `prompt-01-session-00-baseline.md` | — |
| ০২ | EX-01 | Exam | সংশোধন | Import redirect ও Analysis subtab | `prompt-02-ex-01-import-redirect-analysis-subtab.md` | ০১ |
| ০৩ | EX-02 | Exam | সংশোধন | Result/Register roll-order | `prompt-03-ex-02-result-register-roll-order.md` | ০২ |
| ০৪ | EX-03 | Exam | উন্নয়ন | Group-based Mark Evaluation | `prompt-04-ex-03-group-based-mark-evaluation.md` | ০৩ |
| ০৫ | EX-04 | Exam | যাচাই + উন্নয়ন | নতুন subject / Higher Math workflow | `prompt-05-ex-04-new-subject-higher-math.md` | ০৪ |
| ০৬ | EX-05 | Exam | নিয়ম সংশোধন | Missing marks → Absent/Fail | `prompt-06-ex-05-missing-marks-absent-fail.md` | ০৫ |
| ০৭ | EX-06 | Exam | নতুন নিয়ম | GPA 4.90–5.00 → 5.00 | `prompt-07-ex-06-gpa-boost-4-90-to-5.md` | ০৬ |
| ০৮ | EX-07 | Exam | নতুন সুবিধা | Ctrl/Cmd+Click correction | `prompt-08-ex-07-ctrl-click-correction.md` | ০৭ |
| ০৯ | OF-01 | Office | সংশোধন | একটি Guardian Contact | `prompt-09-of-01-single-guardian-contact.md` | ০৮ |
| ১০ | OF-02 | Office | সংশোধন | সর্বোচ্চ ১০০-র pagination | `prompt-10-of-02-pagination-100.md` | ০৯ |
| ১১ | OF-03 | Office | সংশোধন | Subject Assignment Office subtab | `prompt-11-of-03-subject-assignment-office-subtab.md` | ১০ |
| ১২ | OF-04 | Office | উন্নয়ন | Admission reports | `prompt-12-of-04-admission-reports.md` | ১১ |
| ১৩ | OF-05 | Office | যাচাই + উন্নয়ন | Student photos | `prompt-13-of-05-student-photos.md` | ১২ |
| ১৪ | OF-06 | Office | উন্নয়ন | Public success page ও progress | `prompt-14-of-06-public-success-and-progress.md` | ১৩ |
| ১৫ | OF-07 | Office | যাচাই | Admission/import integrity | `prompt-15-of-07-admission-import-integrity.md` | ১৪ |
| ১৬ | OF-08 | Office | যাচাই | Archive/promotion/certificates | `prompt-16-of-08-archive-promotion-certificates.md` | ১৫ |
| ১৭ | DB-01 | Dashboard | যাচাই + উন্নয়ন | Dashboard/navigation | `prompt-17-db-01-dashboard-navigation.md` | ১৬ |
| ১৮ | DB-02 | মূল ব্যবস্থা | সংশোধন | Developer branding | `prompt-18-db-02-developer-branding.md` | ১৭ |
| ১৯ | DB-03 | মূল ব্যবস্থা | নিরাপত্তা | Permissions ও data isolation | `prompt-19-db-03-permissions-data-isolation.md` | ১৮ |
| ২০ | DB-04 | মূল ব্যবস্থা | নিরাপত্তা | Settings ও CI | `prompt-20-db-04-settings-and-ci.md` | ১৯ |
| ২১ | DB-05 | মূল ব্যবস্থা | নতুন ব্যবস্থা | Backup tooling | `prompt-21-db-05-backup-tooling.md` | ২০ |
| ২২ | DB-06 | মূল ব্যবস্থা | যাচাই | Restore drill ও automation | `prompt-22-db-06-restore-drill-and-automation.md` | ২১ |
| ২৩ | AT-01 | Attendance | যাচাই + উন্নয়ন | Entry/correction | `prompt-23-at-01-attendance-entry-and-correction.md` | ২২ |
| ২৪ | AT-02 | Attendance | যাচাই + উন্নয়ন | Calendar/report accuracy | `prompt-24-at-02-attendance-calendar-and-report-accuracy.md` | ২৩ |
| ২৫ | EM-01 | Employee | যাচাই + উন্নয়ন | Employee/teacher assignment | `prompt-25-em-01-employee-teacher-assignment.md` | ২৪ |
| ২৬ | EM-02 | Employee | শর্তসাপেক্ষ | Leave (owner-সিদ্ধান্ত ছাড়া কোড নয়) | `prompt-26-em-02-leave.md` | ২৫ |
| ২৭ | EM-03 | Employee | যাচাই + উন্নয়ন | Payroll controls | `prompt-27-em-03-payroll-controls.md` | ২৬ |
| ২৮ | FN-01 | সমাপনী | যাচাই | পুরো release পরীক্ষা ও নির্দেশিকা | `prompt-28-fn-01-full-release-verification.md` | ০১–২৭ |

## ৪. সাধারণ নিয়ম (প্রতিটি prompt-এ পূর্ণ আকারে আছে)

- সব কাজ **কেবল** `arena/01a0b7f7-school-management-system` branch-এ; `main`-এ push নয়, merge নয় (owner অনুমোদন ছাড়া); অন্য branch নয়।
- production DB / live Render / credential / bucket — **কিছুই ছোঁয়া যাবে না**; কোনো password/token chat-এ নয়।
- SSC Registration / BoardResult পুনরুদ্ধার নিষিদ্ধ (migration 0035 irreversible)।
- `.env`, `db.sqlite3`, `media/`, `backups/`, `.restore-drill/` কখনো commit নয়; টেস্টে শুধু synthetic ডেটা।
- বিদ্যমান migration-এর operations edit নিষিদ্ধ; দরকার হলে নতুন append-only migration + `makemigrations --check` clean।
- smallest coherent change; scope-বাইরে refactor/redesign নয়; নতুন paid service/SMS/email/payment নয়।
- **যাচাই ছাড়া "সম্পন্ন" দাবি নিষিদ্ধ** — শুধু চালানো টেস্টের ফলই প্রমাণ (`docs/WORK_TRACKER.md`-এর নীতি)।
- প্রতিটি সেশনে ডক আপডেট + `PROGRESS.md` সারি + `reports/<সেশন>.md` (ছোট রিপোর্ট)।

## ৫. Baseline (লগ করা তথ্য)

- Checkout: branch `arena/01a0b7f7-school-management-system`, base `f64194a` = `origin/main` (Merge PR #33; PR #32/#33 দুটোই MERGED)।
- ⚠️ `docs/PROJECT_STATUS.md` ও `docs/TASK_BACKLOG.md` শেষ হালনাগাদ **২০২৬-০৯-১৭ (`44cbcc3`)** — অর্থাৎ বর্তমান checkout থেকে পিছিয়ে। এজন্যই **প্রম্পট ০১ (সেশন ০০)** হলো তাজা baseline যাচাই।
- পুরোনো সেশনগুলোর দাবি (নিজে চালিয়ে যাচাই করা হয়নি): ৬২৫ Django + ১৪ Node টেস্ট pass, `check` 0 issue, `makemigrations --check` clean।
- স্যান্ডবক্স env: Python 3.11.2, Node v22.22.3, Django আগে থেকে নেই → isolated venv + documented fallback `Django>=5.2,<6` (Python 3.12+ হলে `requirements.txt`-এর Django 6.1)।
- মাত্রা: `students` অ্যাপ (models ~1100+ লাইন, বড় views.py), ২৩টি `test_*.py` + `students/tests.py`, ২টি Node test file, CI matrix sqlite + `postgres:16`।
- যাচাই করে দেখা কিছু গুরুত্বপূর্ণ অবস্থা (এগুলোই prompt-গুলোর প্রেক্ষাপট): `SubjectMarkSetting`-এ **group field নেই** → EX-03 প্রকৃত উন্নয়ন; `students/result_utils.py` ~L925-930-এ **GPA boost আছে** → EX-06 verify-first; `import_exam_marks` এখন **একই page-এ ফেরে** → EX-01 verify-first; sidebar-এ Result Analysis **আলাদা group** (Exam-এর ভেতরে subtab নেই) → EX-01-এর বাকি কাজ।

## ৬. প্রমাণ কোথায় জমা হয়

| জায়গা | কী থাকে |
|---|---|
| `PROGRESS.md` | ২৮ সারির ledger — কত নম্বর চলছে/শেষ, স্ট্যাটাস, commit, PR, টেস্ট সংখ্যা |
| `reports/<সেশন>.md` | সেশন-রিপোর্ট: আগের→এখনকার অবস্থা, কমান্ড ও ফল, যাচাই হয়নি এমন অংশ, ঝুঁকি, owner-সিদ্ধান্ত |
| `HANDOFF-START.md` + `copy-paste/kickoff/prompt-NN-START.txt` | নতুন সেশনে প্রম্পট শুরু করার START-ব্লক ও গাইড |
| `copy-paste/` (২৯টি .txt) · `export/` (PDF · DOCX) | কপি-পেস্ট ও প্রিন্ট/সম্পাদনার সংস্করণ |
| `docs/PROJECT_STATUS.md` / `docs/TASK_BACKLOG.md` / `docs/HANDOFF.md` | repo-র প্রচলিত doc entry হালনাগাদ |
| `reports/০০-baseline.md` | প্রম্পট ০১-এর পূর্ণ baseline matrix (২৮ আইটেমের verdict) |

## ৭. owner-সিদ্ধান্তের সারি (কোন সেশন আটকে যেতে পারে)

| সেশন | সিদ্ধান্ত | বিস্তারিত |
|---|---|---|
| EX-01 | Analysis subtab কোথায়/কীভাবে বসবে; পুরোনো Result Analysis group রাখা হবে কি না | `prompt-02` §৮ |
| EX-03 | parts-এর যোগ = full marks (exact) কি না; weekly test কোন exam type-এ; group config শুধু class ৯–১২ কি না | `prompt-04` §৮ |
| EX-04 | inactive/removed subject-এর পুরোনো marks; optional choice pending আচরণ | `prompt-05` §৮ |
| EX-05 | `AB` না dash, partially-entered exam-এ GPA-তে 0 ধরা হবে কি না | `prompt-06` §৮ |
| EX-06 | 4.895 → 4.90 (boost) নাকি 4.89? rounding নীতি | `prompt-07` §৮ |
| EX-07 | কোন পেজে shortcut; mobile আচরণ; permission set | `prompt-08` §৮ |
| OF-01 | contact ফরম্যাট validation; একই নম্বর দুই ছাত্রে অনুমোদিত কি না | `prompt-09` §৮ |
| OF-02 | page size fixed ১০০ নাকি নির্বাচনযোগ্য | `prompt-10` §৮ |
| OF-04 | নতুন report কোনটি (capacity/trend); Accounts-এর funnel scope | `prompt-12` §৮ |
| OF-05 | admission form-এ ছবি; সর্বোচ্চ আকার; purge-এ ছবি মুছে ফেলা | `prompt-13` §৮ |
| OF-06 | progress page-এর যাচাই factor; REJECTED-এ বার্তা | `prompt-14` §৮ |
| OF-07 | capacity race নীতি; duplicate roll নীতি; fee mismatch block vs warn | `prompt-15` §৮ |
| OF-08 | TC থাকলে purge; certificate নম্বর পদ্ধতি; দুইবার promotion | `prompt-16` §৮ |
| DB-02 | সাইটে developer credit থাকবে কি না, তথ্য কোথায় | `prompt-18` §৮ |
| DB-03 | rate-limit cache backend; SEC-FU-2 (HR/Audit group) নীতি | `prompt-19` §৮ |
| DB-04 | HSTS/SSL-redirect; `DEBUG=False`-এ secure cookies | `prompt-20` §৮ |
| DB-05 | retention window; encryption key কোথায়; off-box destination | `prompt-21` §৮ |
| DB-06 | RPO/RTO; alert destination; cron overlap | `prompt-22` §৮ |
| AT-01 | কে সংশোধন করবে; correction window; ভবিষ্যতের তারিখ | `prompt-23` §৮ |
| AT-02 | rate-এর সূত্র (H/L); holiday হ্যান্ডলিং; monthly summary-র কলাম | `prompt-24` §৮ |
| EM-01 | assignment granularity; কে assign করবে; session retention | `prompt-25` §৮ |
| EM-02 | **পুরো leave নীতি** (type/paid/entitlement/approval/attendance/payroll) — সিদ্ধান্ত ছাড়া কোড নেই | `prompt-26` §৮ |
| EM-03 | lock granularity; unlock authority; bulk run-এর default amount | `prompt-27` §৮ |
| FN-01 | release go/no-go; কোন খোলা decision release আটকাবে | `prompt-28` §৮ |

## ৮. নোট

- prompt গুলো এই checkout-এর কোড পড়ে লেখা: যেখানে "কোডে আছে বলে দেখা গেছে" লেখা, সেখানে সেশনটি প্রথমে সেটিই যাচাই করবে; মিলে গেলে কাজ কমবে (`⏭️ বাদ`) — ভুল/পুরোনো দাবির উপর ভিত্তি করে অপ্রয়োজনীয় কাজ এড়াতে এটি ইচ্ছাকৃত।
- প্রতিটি prompt-এ "যাচাই ছাড়া সম্পন্ন দাবি নিষিদ্ধ" নিয়মটি বাধ্যতামূলক; ledger-এ শুধু প্রমাণসহ অবস্থা লেখা হবে।
- prompt-এ পরিবর্তন দরকার হলে ফাইলটি সম্পাদনা করুন — ক্রমিক সংখ্যা (০১…২৮) অপরিবর্তিত রাখুন, কারণ ledger ও status block ওই নম্বরের উপর নির্ভর করে।
