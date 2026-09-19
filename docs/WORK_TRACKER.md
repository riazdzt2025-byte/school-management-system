# Work Tracker — School Management System

_একটিমাত্র পরিষ্কার tracker। প্রতিটি কাজের স্থায়ী পরিচয় (stable ID) এখানে থাকবে, যাতে
`docs/PROJECT_STATUS.md` ও `docs/TASK_BACKLOG.md` একই status ও একই ID reference করে।_

**নিয়ম:** এই ফাইলে শুধু যাচাই করা অবস্থাই লেখা হয়। কোনো কাজ নিজের যাচাই ছাড়া
"সম্পন্ন" ধরে ভরা হয় না — অন্য সেশনের দাবি এখানে অনুলিপি হয় না, প্রমাণসহ উদ্ধৃত হয়।

_Last updated: 2026-09-18 · branch `arena/01a0b574-school-management-system` · base `11cd35d` (Merge PR #32) = `origin/main`_

---

## ADM-REPORTS — Admission Reports

**স্থায়ী পরিচয়:** `ADM-REPORTS`
**সম্পর্কিত backlog entry:** `docs/TASK_BACKLOG.md` → `O4 · Admission Share Link-এর পাশে উন্নত Reports`
**সম্পর্কিত status row:** `docs/PROJECT_STATUS.md` → §2.2 Office, row `O4`
**মূল চাহিদা:** internal Admission page-এ `Share Application Link`-এর পাশে Reports, এবং
`SUBMITTED → ENROLLED` admission funnel report (institution-scoped, Excel export সহ)।

### Status

| দিক | অবস্থা |
|---|---|
| মূল requirement (funnel/report) | **Complete** — code `main`-এ merged + navigation চাহিদা পূরণকারী follow-up PR খোলা |
| Code merge status | PR #32 **MERGED** · PR #33 **OPEN (merge হয়নি — অনুমোদনের অপেক্ষায়)** |
| Live deployment status | **Unverified** |
| Optional enhancement (capacity/trend chart) | **Not started** — মূল কাজের অংশ নয়, নিচে আলাদা করা |

> মূল funnel/report চাহিদা পূর্ণ হওয়ায় এটি **Complete**। Capacity/trend chart না থাকা
> এই কাজকে অস্পষ্টভাবে "Partial" রাখে না — ওটি আলাদা Optional enhancement
> (`ADM-REPORTS-OPT-1`), নিচে তালিকাভুক্ত।

### Implemented capabilities

PR #32 (merged) থেকে — যাচাই করা হয়েছে এই checkout-এ code উপস্থিত আছে কিনা দেখে:

- `students.views.admission_funnel_report` — institution-scoped admission funnel
  (`SUBMITTED → OFFICE_APPROVED → ACCOUNT_PENDING → PAYMENT_APPROVED → ENROLLED`,
  `REJECTED` funnel-এর পাশে আলাদা), print-friendly পেজ।
- `students.views.admission_funnel_export` — Excel export; scope একাধিক institution
  ছুঁলে আলাদা `By Institution` sheet।
- Routes: `reports/admission-funnel/` (`admission_funnel_report`) ও
  `reports/admission-funnel/export/` (`admission_funnel_export`)।
- Filters: `?institution=` (নিরাপদভাবে bounded) + `?from=` / `?to=` (`submitted_at`
  whole-day inclusive)।
- Scoping: `_resolve_requested_institution` + `_scope_institution_qs` — list/export-এর
  সাথে হুবহু একই নীতি; session selection হারালে scoped clerk "all institutions"-এ
  পড়ে না, নিজের allowed set-এ সীমিত থাকে।
- Guards: `students.view_admissionapplication` (`raise_exception=True`) + Office/Accounts
  department check — sidebar link লুকানোই নিরাপত্তা নয়, direct URL-ও বন্ধ।
- Navigation: Office flyout-এ `Admission Funnel`, এবং `class_section_summary` পেজ থেকে
  cross-link।

এই follow-up (PR #33) থেকে — মূল navigation চাহিদা:

- **internal Admission page-এ `📊 Reports / রিপোর্টস` action, `📲 Share Application Link`-এর
  ঠিক পাশে** (`students/templates/students/admission_application_list.html`)।
- বিদ্যমান named URL `admission_funnel_report` ব্যবহৃত — নতুন view/route তৈরি হয়নি।
- `perms.students.view_admissionapplication` gate — শুধু অনুমোদিত user link পায়।
- Link-এ **কোনো query string নেই**: report-টি এই list page যে session-selected institution
  দিয়ে filter করে ঠিক সেটিই পায়, তাই institution context নিরাপদভাবে বজায় থাকে এবং
  URL ট্যাম্পার করে scope বাড়ানো যায় না।

**ইচ্ছাকৃতভাবে অপরিবর্তিত:** backend authorization, export structure ও institution scope,
`download_admission_sheet`, Office flyout link, Office/Accounts access policy। কোনো
model/migration নেই। Public application form ও Thank You page-এ কোনো internal report
link নেই। SSC Registration / SSC Result Summary ফিরিয়ে আনা হয়নি।

### Tests actually run

লোকাল রান — README-তে নথিভুক্ত fallback অনুযায়ী (sandbox-এ Python 3.11,
`requirements.txt`-এর `Django==6.1` চায় Python 3.12+; README বলে প্রজেক্ট কোনো
6.x-only API ব্যবহার করে না, তাই `Django>=5.2,<6`): **Django 5.2.17 / Python 3.11.2, sqlite**।

| কমান্ড | ফল |
|---|---|
| `manage.py test students.test_admission_funnel_report` | **Ran 20 tests — OK** (16 বিদ্যমান + 4 নতুন) |
| `manage.py test students` (পূর্ণ suite) | **Ran 625 tests — OK**, 0 fail / 0 error |
| `manage.py check` | System check identified no issues (0 silenced) |
| `manage.py makemigrations --check --dry-run` | No changes detected (migration consistency অক্ষত) |
| `node --test students/js/*.test.js` (Node 22.22.3) | 14 pass, 0 fail |

এই follow-up-এ যোগ হওয়া ৪টি test:

- `test_admission_page_shows_reports_link_beside_the_share_link` — Reports link Share
  Application Link-এর পাশে, correct named URL-এ যায়, bilingual label আছে, এবং Office
  flyout link-ও টিকে আছে (দুটি entry point একসাথে)।
- `test_admission_page_reports_link_keeps_the_session_institution` — link follow করলে
  institution A-এর সংখ্যাই আসে, `Funnel B` আসে না, href-এ `institution=` নেই।
- `test_admission_page_reports_link_is_denied_to_unauthorised_users` — anonymous → 302
  (login), permission ছাড়া → **403** (পেজ ও direct URL উভয়ে), permission থাকলেও ভুল
  department → **302** (dashboard)।
- `test_public_admission_pages_carry_no_internal_report_link` — public form (rendered)
  এবং public form + Thank You template (source) কোনো internal report link বহন করে না।

বিদ্যমান regression cover যা এই রানে pass করেছে: funnel counts, date range,
institution isolation (page + export), `?institution=` escape রোধ, session হারানোর
fallback, permission/department negatives, Excel contents, empty scope,
`download_admission_sheet`, `test_share_application_link_is_untouched`।

**CI (authoritative, Django 6.1 / Python 3.12, sqlite + postgres):** PR #33-এর তিনটি
check-ই **pass** — বিস্তারিত নিচে "CI verification"-এ। PR #32-এর ৬টি check-ও merge-এর
আগে সবুজ যাচাই করা হয়েছিল।

### PR / merge status (আলাদা আলাদা)

| Item | Status | প্রমাণ |
|---|---|---|
| Commit — funnel feature | `1a557fc` | PR #32-এর একমাত্র commit |
| PR #32 — admission funnel report | **MERGED** | merge commit `11cd35d`, `mergedAt` 2026-09-18T17:10:51Z; merge-এর আগে `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN`, ৬টি CI check SUCCESS যাচাই করা হয়েছে |
| `main` — funnel code উপস্থিত | **Yes** | `origin/main` = `11cd35d`; `students/urls.py`-তে `admission_funnel_report` route, `students/test_admission_funnel_report.py` ও `admission_funnel_report.html` checkout-এ আছে |
| Commit — এই follow-up | `4978c99` | branch `arena/01a0b574-school-management-system`, base `11cd35d` |
| PR #33 — Admission page Reports action | **OPEN — merge হয়নি** | মালিকের অনুমোদন ছাড়া merge করা হবে না |

### CI verification

**PR #33 (commit `4978c99`) — GitHub Actions, Django 6.1 / Python 3.12: সব check pass।**

| Check | ফল | সময় |
|---|---|---|
| `test (sqlite, 3.12)` | **pass** | 6m14s |
| `test (postgres, 3.12, true)` | **pass** | 5m11s |
| `Node row-action button tests` | **pass** | 7s |

এই workflow-তে `manage.py check`, `makemigrations --check`, তিনটি production deploy guard
(fallback `SECRET_KEY` প্রত্যাখ্যান, wildcard `ALLOWED_HOSTS` প্রত্যাখ্যান → `students.E016`,
production-shaped config pass) এবং পূর্ণ `manage.py test students` sqlite ও Postgres উভয়ে
চলে — অর্থাৎ Django checks ও migration consistency CI-তেও যাচাই হয়েছে।

প্রসঙ্গ: PR #32-এর ৬টি check-ও merge-এর আগে সবুজ যাচাই করা হয়েছিল।
(CI job log-এর ভেতরের test সংখ্যা এই sandbox থেকে পড়া যায়নি, তাই সংখ্যাটি লোকাল
রান থেকেই লেখা হয়েছে; check-এর pass/fail ফল `gh pr checks` থেকে নেওয়া।)

### Live deployment status

**Unverified.**

- Render `main` থেকে auto-redeploy করে (`DEPLOY_NOTES.md`)। PR #32 `main`-এ merge হওয়ায়
  funnel report deploy হওয়ার কথা — কিন্তু এই sandbox থেকে live সাইট যাচাই করা হয়নি,
  তাই নিশ্চিত দাবি করা হচ্ছে না।
- PR #33 `main`-এ নেই, তাই Admission page-এর Reports button **live-এ নেই** (এটি git
  state থেকে নিশ্চিত, live probe নয়)।
- কোনো production data / configuration / credential পরিবর্তন বা ব্যবহার করা হয়নি।
  কোনো demo credential এখানে পুনরায় প্রকাশ করা হয়নি।

### অবশিষ্ট requirement

মূল চাহিদার জন্য **কোড-স্তরে কিছু বাকি নেই** — শুধু একটি অনুমোদন বাকি:

1. **PR #33 merge-এর অনুমোদন** (মালিকের সিদ্ধান্ত; এজেন্ট নিজে merge করবে না)।
2. **খোলা product সিদ্ধান্ত (নীতি বদলানো হয়নি):** funnel report ও নতুন Reports button
   বিদ্যমান নীতি অনুযায়ী **Office ও Accounts** উভয় department-কে দেখা যায়। Accounts কি
   পুরো funnel (enrolment stage-সহ) দেখবে, নাকি শুধু payment stage-সীমিত view পাবে —
   এটি মালিকের সিদ্ধান্ত। সিদ্ধান্ত না হওয়া পর্যন্ত বর্তমান নীতিই বলবৎ।
3. Merge-এর পরে চাইলে **live Render যাচাই** (অনুমোদিত user দিয়ে Admission page → Reports),
   যা এই sandbox থেকে সম্ভব নয়।

### Future enhancements (Optional — মূল কাজকে Partial করে না)

- **`ADM-REPORTS-OPT-1` — Capacity / trend charts:** class/section-ভিত্তিক capacity vs
  enrolled (`SectionCapacity` vs actual), payment-vs-enrolled trend, date-wise trend
  chart। এটি আলাদা Optional enhancement; মূল funnel/report চাহিদার শর্ত নয়।
  (Backlog O4 acceptance-এর (b)/(c) অংশ।)
- Admission photo continuity — আলাদা কাজ (`O5`), এই tracker-এ সম্পন্ন ধরা হয়নি।
- Dashboard redesign — এই follow-up-এর scope-এর বাইরে; করা হয়নি।

### Scope note

এই যাচাইয়ে **অন্য কোনো কাজ সম্পন্ন ধরে এই tracker ভরা হয়নি**। `O2`, `O5` ও অন্যান্য
entry-র status তাদের নিজস্ব পূর্ব-যাচাই অনুযায়ী অপরিবর্তিত আছে; এই সেশনে শুধু
`ADM-REPORTS` / `O4` হালনাগাদ করা হয়েছে।
