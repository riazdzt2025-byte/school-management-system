# Project Status — School Management System

_Last updated: ২০২৬-০৯-২৩ (EX-05 — Missing marks → Absent/Fail: AB token সর্বত্র অভিন্ন, ৭২১ Django + ১৪ Node)_\
_Base: `acc1123` (Merge PR #45) on branch `arena/01a0cd68-school-management-system`_\
_Working tree: clean, no local overwrite, no reset --hard, no git clean_

> **২০২৬-০৯-২৩ EX-05 সম্পন্ন (প্রম্পট ০৬/২৮):** Missing marks → Absent/Fail নীতি ইতিমধ্যে Complete ছিল (D-MIS সিদ্ধান্ত ২০২৬-০৯-১৭: blank = F, **AB display**, TC/DISCONTINUED বাদ); এই সেশনে থাকা একমাত্র অসঙ্গতি — absent সেলের token ভিন্ন ভিন্ন পৃষ্ঠায় ভিন্ন (`AB` register-এ, `– absent` result card-এ, `— (no mark entered)` detail-এ, `Absent` Analysis card/subject-fail-এ) — **সব জায়গায় `AB`** করা হলো, এবং `EXAM_ABSENT_SUBJECT_FAILS=False` path-এ result_sheet/detail-এর হার্ডকোডেড F-badge ও "counted as 0" ফুটনোট policy-aware করা হলো (False হলে badge `–`, ফুটনোট "left out of the total and the GPA")। সব ১০টি result surface একই `build_exam_results` source ব্যবহার করে — duplicate হিসাব নেই (verified); নতুন ৬টি cross-view consistency test (`test_absent_token_consistency.py`)। `RESULT_PUBLISHING_GUIDE.md`-এ প্রদর্শন-token টেবিল যোগ। এই checkout-এ নিজে চালিয়ে যাচাই — **৭২১ Django + ১৪ Node pass** (৭১৫+৬), `check` 0 issue, `makemigrations --check` clean (leaf 0046), migration নেই। রিপোর্ট `docs/prompts/reports/EX-05.md`।

> **২০২৬-০৯-২০ EX-03 বাকি কাজ সম্পন্ন (প্রম্পট ০৪/২৮):** EX-03-এর প্রমিত বাকি আইটেম — `mark_evaluation_settings`-এ **weekly_test column non-MID exam_type-এ hide** — এই সেশনে করা হলো (view-এ `show_weekly_test` context flag + template-এ conditional column + help-text; POST-এ rejection আগে থেকেই ছিল, এখন UI-তেও input নেই) + ২ নতুন regression test। এই checkout-এ নিজে চালিয়ে যাচাই — **৬৭০ Django + ১৪ Node test pass** (৬২৫→৬৩৮→৬৫৩→৬৬৮→৬৭০ ক্রমে EX-01/02/03+finishing), `check` 0 issue, `check --deploy` ৬টি dev warning, `makemigrations --check` clean (leaf **0044** — EX-03 group migration), backup drill sqlite ১৫/০ ও moto-S3 ২৮/০ pass। EX-01/EX-02/EX-03 সব Complete — প্রমাণ `docs/prompts/reports/০০-baseline.md` + `EX-01.md`/`EX-02.md`/`EX-03.md` (§20-এ সারসংক্ষেপ)। নিচের ২০২৬-০৯-১৭-এর section-গুলো ঐতিহাসিক রেকর্ড; যেখানে সংখ্যা বা verdict ভিন্ন, §20-ই সত্য।

**Bengali TL;DR (সর্বশেষ — ২০২৬-০৯-২০ EX-03 + finishing):** EX-03 **Group-based Mark Evaluation** implement হয়েছিল — `SubjectMarkSetting.group` (migration **0044**, blank=default, 9-12 only, exact/MID owner সিদ্ধান্ত) + resolution chain **group→blank→Subject** (marks entry/import/result group-aware) + `mark_evaluation_settings` UI group selector/per-group listing+validation+audit। বাকি কাজ হিসেবে এখন **weekly_test column শুধু MID_TERM_1/2/3-এ দেখায়** (অন্য exam_type-এ column + input + help-text mention সব hidden; legacy saved value DB-এ থাকে, display হয় না)। এর আগে EX-02 (roll-order ৬৫৩) ও EX-01 (Analysis subtab+import preserve ৬৩৮) merge হয়েছে। পূর্ণ suite এখন **৬৭০ Django + ১৪ Node pass**, `check` 0, `makemigrations --check` clean (0044), `RetiredBoardFeatureTests` pass (SSC restore নয়)। Live Render/DB/backup এই sandbox থেকে **UNKNOWN** — docs ছাড়া নিশ্চিত দাবি নয়; কোনো production DB/credential ছোঁয়া হয়নি।

---

## 1. Verification performed this session (2026-09-17, সেশন ০১)

| Check | Result | Evidence |
|---|---|---|
| Repository access | **Verified — readable** | `git fetch origin --prune` exit 0, `git remote -v` = `github.com/riazdzt2025-byte/school-management-system` |
| Current branch / commit / working tree / base | **Clean** | `git branch --show-current` = `arena/01a0ad5e-school-management-system`; `git rev-parse HEAD` = `44cbcc365d9ad587c03bd06da7cb96bef8dd0c1d` = `origin/main`; `git status` = `nothing to commit, working tree clean`; `git merge-base HEAD origin/main` = same; `git log --oneline -1` = `44cbcc3 Merge pull request #27 …` |
| Branch rule | **Compliant** | Work stayed on `arena/01a0ad5e…`; no switch to other branch; no `reset --hard` / `git clean`; no overwrite of local changes |
| Remote operations | **Allowed — checked main** | `git fetch` succeeded, `origin/main` = `44cbcc3`; `git diff HEAD origin/main --stat` empty |
| Access failure handling | **No failure** | No password/token requested; if failed would report explicitly (not claimed verified) |
| Dependency compatibility (isolated) | **Pass with fallback** | `requirements.txt` pins `Django==6.1` (needs Python 3.12+). Sandbox Python 3.11.2 → `pip install Django==6.1` fails (expected). Fallback `pip install "Django>=5.2,<6" openpyxl Pillow python-dotenv dj-database-url whitenoise psycopg2-binary django-storages boto3` → `Django 5.2.17` clean; README documents fallback; no 6.x-only API (`grep` verified) |
| `python manage.py check` | **0 issues** | Isolated `/tmp/audit_venv` (Django 5.2.17) — `System check identified no issues (0 silenced).` |
| `python manage.py check --deploy` (DEBUG=True) | **6 warnings expected** | `W004 W008 W009 W012 W016 W018` — development defaults, not a bug |
| `python manage.py makemigrations --check` | **Clean** | `No changes detected` — models and migrations 0001–0042 in sync |
| `python manage.py test students` (isolated) | **555 tests, all pass** | `Ran 555 tests — OK` (was 550; +5 GPA/pagination/AB/inactive/import tests) (was 452 on 2026-09-16; +98 backup/media/encryption/off-box tests). No production DB touched; ephemeral SQLite test DB |
| `node --test students/js/student_row_actions.test.js` | **6 tests, all pass** | `1..6 pass 6 fail 0` |
| SSC removal regression | **Pass** | `grep -r SSCRegistration` only in migrations 0008/0032/0035 + test asserting absent; `RetiredBoardFeatureTests` passes |
| Production (Render) state | **UNKNOWN** | No `DATABASE_URL`, no Render API access from sandbox; never claimed otherwise (rule 7) |

**Isolated environment:** `python3 -m venv /tmp/audit_venv` → `pip install "Django>=5.2,<6" openpyxl Pillow python-dotenv dj-database-url whitenoise psycopg2-binary django-storages boto3` → `pip show Django` = `5.2.17`. Test DB is throwaway SQLite; `backup_smoke_test.sh` style drill not run on prod. No secrets written.

---

## 2. বর্তমান feature status audit (Complete / Partial / Missing / Unverified)

> Legend: **Complete** = end-to-end works + tests; **Partial** = core works but gap listed; **Missing** = not built / intentionally deferred; **Unverified** = needs live Render check (rule 7). প্রতিটি আইটেমে code/file evidence উল্লেখ আছে। Feature code থাকা / tests pass / PR merge / live deploy — আলাদা অবস্থা হিসেবে রিপোর্ট করা হয়েছে।
>
> ⚠️ **এই §2-এর কয়েকটি সারি ২০২৬-০৯-১৯-এ বাসি প্রমাণিত:** E1 (import redirect এখন stay-on-page),
> E7 (আগের automatic GPA 4.90–4.99 → 5.00 policy পরে বাতিল; current fourth-subject rule নিচে), O2 (student/archived/employee/attendance-এ pagination ১০০ আছে)।
> সঠিক ও প্রমাণসহ সর্বশেষ অবস্থা **§20** এবং `docs/prompts/reports/০০-baseline.md`-এ।

### 2.1 Exam (পরীক্ষা ও ফলাফল)

| # | Feature | Status | Evidence / Gap |
|---|---|---|---|
| E1 | Marks import শেষে একই exam-এর import page-এ থাকা | **Complete** | `views.py:3803-3810 import_exam_marks` — সফল import-এর পর `redirect(reverse('import_exam_marks', kwargs={'pk': exam.pk}) + '?subject=…&group=…')` (কমেন্ট "Stay on the same import page … (E1)"); POST-redirect-GET হওয়ায় refresh-এ double-import নেই। Regression pin: `tests.py::test_import_stay_on_page_redirects_to_same_page` + **`test_import_stay_on_page_preserves_subject_and_group`** (EX-01, PR #39 — group param সংরক্ষণও pinned)। ⚠️ ২০২৬-০৯-১৯-এর আগের Partial-ভিত্তি (`return redirect('exam_list')`, L3295/`:3391-3392`) এখন বাসি। পুরোনো PR #23 একই আচরণের প্রস্তাব — owner চাইলে superseded বন্ধ করতে পারেন। |
| E2 | Result Analysis Exam subtab | **Complete** | `views.py::_require_result_analysis_department` + 5 views: `result_analysis_subject_fail`, `multi_term`, `merit_slides`, `result_cards`, `section_arrangement` + `result_analysis_subject_fail_list` helper + templates `result_analysis_*.html` + sidebar `Result Analysis` flyout guarded by `can_result_analysis` context. Institution-scoped, permission-gated. Tests: `students/test_result_analysis.py` (curriculum, isolation, helpers)। **EX-01 (PR #39, 2026-09-19):** এখন Exam flyout-এও nested **Analysis subtab** (একই ৫টি named URL — দুটি entry point), `exam_list`-এ দৃশ্যমান `analysis-entry`, এবং ৫টি result পেজের হেডারে প্রাসঙ্গিক cross-link (`analysis-jump`) — সবই `can_result_analysis` gate-এ; per-view guard অপরিবর্তিত (anonymous 302 / no-perm 403 / Accounts 403 — `test_navigation.py::ExamAnalysisSubtabTests`-এ pinned)। |
| E3 | Class Performance Register সহ result lists/print/export-এ numeric roll-order | **Complete** | **আনুষ্ঠানিক নিয়ম (EX-02, PR #41, 2026-09-20):** register/roll output = numeric roll — `F('roll_no').asc(nulls_last=True)` + tie name→pk; merit/rank output = position (ইচ্ছাকৃত)। `result_sheet` Python sort-key (None last, name→pk — c17a45a, re-pinned); `student_list` + `download_student_list` (Excel, owner সিদ্ধান্ত: roll) class→section→roll→name→pk (আগে NULL **প্রথমে** আসত — ঠিক); attendance class-wise list `mark_attendance_bulk` name→roll; seat-plan/signature `SeatPlan.Meta (room_name, seat_no)` + `generate_seat_plan` register ক্রমে seat বরাদ্দ; class result-cards print run merit→roll (প্রতিটি card-এ position মুদ্রিত); multi-term/subject-fail/section-arrangement-এ pk tie-break। **Merit অপরিবর্তিত:** `exam_result_summary` (position-first table), `full_rank_list`, `top_10`, merit slides; unranked tail register order। `attendance_report` = record log (-date), `attendance_summary` = analytics (name) — পূর্ণ matrix: `docs/prompts/reports/EX-02.md`। Print CSS reorder করে না (template dictsort/JS-sort = 0)। Tests: `test_register_roll_order.py` (১৫ — rolls 2/10/100/None, duplicate-roll tie, দুই-পেজ pagination) + `test_sheet_defaults_to_numeric_roll_order_without_changing_merit`। |
| E4 | Group-based Mark Evaluation | **Complete** | EX-03 (2026-09-20, migration **0044**): `SubjectMarkSetting.group` (`''`=default, `choices=CLASS_GROUPS` must be blank for classes <9 — 9-12 only) + unique `institution+class+subject+exam_type+group` (append-only). Resolution এক ফাংশনে: `get_subject_marks(..., group)` / `active_exam_subject_ids(..., group)` / `resolve_mark_setting` **group→blank→Subject** fallback (marks entry/import/result সব group-aware). `mark_evaluation_settings` (URL `mark-evaluation/`) per `institution+class+exam_type+group` — `is_active`, parts CQ/MCQ/PT/WT, pass % + group selector + per-group listing; POST validation: full>0, pass 0-100, parts **exact** sum (=full — owner সিদ্ধান্ত), weekly_test **MID_TERM_* only** (owner সিদ্ধান্ত), <9 blank, duplicate via `update_or_create` + `record_audit`, institution-scoped, `change_subject` perm (অপরিবর্তিত). Inactive group-aware; backward compat blank=default (all groups). **weekly_test column এখন শুধু MID_TERM_1/2/3-এ render হয়** (2026-09-20 finishing: view `show_weekly_test` flag + template conditional; non-MID-এ save-এও reject — legacy stored value DB-এ থাকে, display হয় না)। Tests: `test_group_based_mark_evaluation.py` ১৭ (১৫ +২ column hide/show pin) + `MarksPartsAndPassRulesTests` ৯ + `MarkEvaluationActiveSubjectTests` ৩ (full 670)। Reports: `docs/prompts/reports/EX-03.md`। |
| E5 | নতুন subject / Higher Math assign / configure করে marks / result দেওয়ার workflow | **Complete** | তিনটি আলাদা যাচাই (নির্দেশ ৩): (1) **Curriculum-এ থাকা:** `curriculum_data.py:42 HMATH`, `SSC_GROUPS['SCI']` = `HMATH MANDATORY` (line 132-136), `HSC_GROUPS['SCI']` = `HMATH OPTIONAL sci_4th`; (2) **Database-এ থাকা:** migration `0042_higher_math_mandatory_science.py` (SSC SCI 9/09/10 → MANDATORY, reverse → OPTIONAL), `Subject` row via `seed_subjects`; (3) **Class/group-এ assigned থাকা:** `SubjectRequirement(institution, admission_class, group, subject, requirement_type)` + `subject_requirement_list` (Office CRUD) + `get_applicable_subjects()` + `auto_populate_subject_requirements`. New subject inline “or add a new subject below” restored (`bd1bd2c`), then marks via `enter_marks` / `import_exam_marks` per-subject, then `build_exam_results` → result views. Tests: `test_new_subject_result_workflow.py`, `test_result_analysis.py::test_ssc_higher_math_is_mandatory`, `ExamScopeConsistencyTests`। |
| E6 | Missing/null marks, entered zero, all-blank, optional/exempt subjects-এর আচরণ | **Complete** | Single source `result_utils.compute_subject_result` + `ABSENT='-'` + `EXAM_ABSENT_SUBJECT_FAILS` (default True, env). **All-blank (no row):** `mark is None` → if `True` → `F/0` counted as 0/full (absent True, `failed_parts=[]`) but cell shows dash; if `False` → `ABSENT` excluded from total/GPA. **All subjects blank:** `build_exam_results` → `overall_gpa=None, grade=ABSENT, status='No Marks'` (not Fail, not ranked). **Entered zero:** `marks_obtained=0` → `percentage 0` → `F/0.00` passed=False, counted toward total/GPA (distinct from absent). **Optional/exempt:** `ReligionColumn` single REL column per student's religion + `StudentSubjectChoice` optional_set_key + `not_applicable`/`religion_unassigned` (dash, never counted, not absent). Tests: `AbsentSubjectRulesTests` (5), `MarksPartsAndPassRulesTests` (including `test_a_student_entered_nowhere_has_no_row`, `test_configured_but_blank_part_is_a_failed_part`)। **EX-05 (2026-09-23):** token সর্বত্র অভিন্ন — absent সেল এখন **`AB`** প্রতিটি cell-প্রিন্টিং surface-এ (result_sheet, student_result_detail, result_card, analysis result_cards, subject_fail); `EXAM_ABSENT_SUBJECT_FAILS=False`-এ result_sheet-এর F-badge/ফুটনোট ও detail-এর ফুটনোট policy-aware; ১০টি surface-এর GPA/status একমুখ (`test_absent_token_consistency.py` ৬ test)। টেবিল: `RESULT_PUBLISHING_GUIDE.md` §2 |
| E7 | চতুর্থ/অতিরিক্ত বিষয়ের GPA নিয়ম | **Complete** | **EX-06 policy correction (2026-09-23/24):** old automatic 4.90→5.00 boost removed. `result_utils.calculate_final_gpa()` applies `min(5.00, (main-point-sum + max(0, FOURTH-point−2.00)) / main-subject-count)` with deterministic two-place `ROUND_HALF_UP`. Only selected `Subject.category='FOURTH'` qualifies; ordinary OPTIONAL is main. Fourth F/AB = zero bonus but never fails the main result; a main F/AB still yields Fail/0.00. **Owner 2026-09-24:** fourth marks/full marks are included in displayed total and percentage, while GPA denominator/pass-fail remain main-only. Merit is unique: letter grade → uncapped formula GPA → total (fourth included) → lowest numeric roll. One fourth choice per student is enforced before publishing (`fourth_subject_configuration_errors`). `test_fourth_subject_gpa.py` pins cap/no 5.20, fourth F versus main F, total/percentage inclusion, merit tie-break, all result/print/analysis surfaces, and the publish block; `tests.py` pins no-fourth 4.90 stays 4.90. No result-specific GPA export endpoint exists. Full rule/examples: `RESULT_PUBLISHING_GUIDE.md` §2. Scope-update proof: 727 Django + 14 Node pass, check 0, migrations clean; PR #47 fresh sqlite/Postgres/Node CI passed at `cbc7095` (run 35952497142). |
| E8 | Result cell থেকে Ctrl/Cmd+Click correction shortcut | **Complete** | `result_sheet.html` subject cells carry `data-subject-pk` (Religion cells use `sr.paper.pk` — the paper *that student* sits, never the REL column) + `data-group` inside `.result-table-card[data-enter-marks-base]`; `static/students/js/result_cell_shortcut.js` opens `enter_marks` for that subject+group in a **new tab** on Ctrl/Cmd+Click, and ignores plain clicks so printing is unaffected. `full_rank_list.html` has no subject columns, so its rows carry `data-shortcut-url` → `select_marks_subject` (group preserved). No `students.add_exammark` → `data-shortcut-disabled="true"` + tooltip “Ask Exam dept”. Documented in `RESULT_PUBLISHING_GUIDE.md` §7. Tests: `students/js/result_cell_shortcut.test.js` (8 Node) + `ResultCellShortcutTests` (3)। |
| E9 | Published/historical result safety | **Complete** | All 5 result views + `full_rank_list` + `student_result_detail`/`result_card` guard `if not exam.is_published: redirect exam_list + error`. `unmarked_assigned_subjects` (no column) and `marked_subject_ids_for_exam` (a subject only joins result once first mark entered) keep published register stable when subject assigned after publish. `missing_mark_subjects` notice warns before treating register as final. Tests: `ExamWorkflowTests.test_unpublished_result_views_redirect_to_exam_list`, `test_publish_toggle_only_mutates_on_post`। **Published-marks lock (R1, 2026-09-17):** while `is_published=True`, `enter_marks` and `import_exam_marks` refuse every write until an explicit **Unlock to edit published result** POST; `exam_marks_unlocked` and `exam_marks_write_blocked` join `exam_published`/`exam_unpublished` in the audit log, and `EXAM_LOCK_PUBLISHED=False` disables the lock. So a published exam can no longer be edited silently — see `RESULT_PUBLISHING_GUIDE.md` §7 and `test_published_lock_and_cell_shortcut.py`। |

### 2.2 Office (অফিস)

| # | Feature | Status | Evidence / Gap |
|---|---|---|---|
| O1 | একটি canonical Guardian Contact Number | **Complete** | Single `Student.guardian_contact_no` + `AdmissionApplication.guardian_contact_no` (0039 only fills blank, 0040 archives differing legacy numbers to `AuditLog(legacy_contact_dropped)` then `RemoveField` for `contact_no`/`applicant_contact_no`, 0041 required). `GUARDIAN_CONTACT_RE`, `normalize_guardian_contact` (Bangla ০-৯, numeric Excel cell `1812345678→01812345678`), `validate_guardian_contact` in `forms.py:138/284`, Excel import/export, enrolment `guardian_contact_no` copy, `contact_conflict_report` command. Tests: `test_guardian_contact.py` (unit + forms + import + enrolment + migration TransactionTestCase)। |
| O2 | Student pagination: সর্বোচ্চ ১০০ records | **Missing** | `views.student_list` (L1282) does `students = list(qs.order_by(...))` with no `Paginator`, no `limit`, no `?page` — loads all (254 fixtures, potentially thousands live). No “max 100” enforcement found (`grep -rn "Paginator\|paginate" students/views.py` only attendance backup). Intentionally deferred as P1 quick-fix (small session, see backlog O2)। |
| O3 | Subject Assignment Office subtab ও প্রয়োজনীয় permissions | **Complete** | Sidebar Office flyout: `Subject Assignments` (`perms.students.view_subjectrequirement`) + `Mark Evaluation` (`change_subject`). `permissions.py` Office group has `SubjectRequirement:[add,change,delete,view]` + `Subject:[add,change]` (inline new subject). Exam/Accounts have `view_subjectrequirement` read-only so “Go to Subject Assignments” links never 403. Scoped via `user=` in `SubjectRequirementForm` + `_get_scoped_object_or_404` on edit/delete. Tests: `test_subject_assignment_office.py`। |
| O4 | Admission Share Link-এর পাশে উন্নত Reports | **Complete** | **ADM-REPORTS** — বিস্তারিত `docs/WORK_TRACKER.md`। **Share Link:** অপরিবর্তিত — `admission_application_list.html`-এ `📲 Share Application Link` + toast (`share-toast`) `public_admission_apply` URL + `SCHOOL_INFO` কপি করে, `Open WhatsApp` via `wa.me/?text=`। **Reports:** admission funnel — `views.admission_funnel_report` (print-friendly) + `views.admission_funnel_export` (Excel, multi-institution scope-এ `By Institution` sheet), routes `reports/admission-funnel/` + `.../export/`; `SUBMITTED→OFFICE_APPROVED→ACCOUNT_PENDING→PAYMENT_APPROVED→ENROLLED` (`REJECTED` পাশে), `?from`/`?to` (`submitted_at` whole-day inclusive); scoping `_resolve_requested_institution` + `_scope_institution_qs` (list/export-এর হুবহু নীতি); guard `students.view_admissionapplication` (`raise_exception`) + Office/Accounts department — তাই direct URL-ও বন্ধ। **মূল navigation চাহিদা:** internal Admission page-এ `📲 Share Application Link`-এর ঠিক পাশে `📊 Reports / রিপোর্টস` (named URL ব্যবহৃত, কোনো query string নেই — session-selected institution-ই নিরাপদভাবে বহাল থাকে); Office flyout-এ `Admission Funnel` ও `class_section_summary` cross-link অক্ষত। **PR/merge:** PR #32 **MERGED** (`11cd35d`, 2026-09-18) — funnel code `main`-এ যাচাইকৃত; PR #33 **OPEN, merge হয়নি** (অনুমোদনের অপেক্ষায়)। **Tests:** `students/test_admission_funnel_report.py` = 20 tests (16 + 4 নতুন: placement/named URL, institution scope, unauthorised 403/302 + anonymous redirect, public form ও Thank You page-এ internal report link নেই); লোকাল ফুল suite **625 tests OK**, `check` 0 issue, `makemigrations --check` clean, `node --test` 14 pass (README fallback Django 5.2.17 / Python 3.11)। **Live deployment: Unverified**। Capacity/trend chart আলাদা **Optional enhancement `ADM-REPORTS-OPT-1`** — ওটি না থাকায় মূল report কাজ Partial নয়। |
| O5 | Application থেকে student record ও প্রয়োজনীয় documents-এ photo continuity | **Partial** | `accounts_approve_payment` creates `Student(name, admission_class, section, group, gender, religion, father_name, guardian_contact_no, admission_year)` + auto mandatory/conditional subjects, then `MoneyReceipt`. `AdmissionApplication` has **no photo field** (see model fields L453-...), so no photo to carry; `Student.photo` remains blank after admission. Documents (`TC`/`Certificate`/`ID card`) exist (`issue_tc`, `view_tc`, `certificate_list`, `student_id_card`) but rely on `Student.photo` separately uploaded. Photo continuity (upload in application → appears in ID/TC) missing — backlog O5 (needs model + form + storage)। |
| O6 | Public Thank You page, internal Back link এবং নিরাপদ progress tracking | **Complete** | **Thank You:** `public_admission_success.html` standalone (no sidebar) with Application Number/Class/Session alert + “Thank you… office will review”. **Back link:** `admission_application_detail.html` has `← Back to applications` + success page `← Back to Home` → dashboard. **Progress tracking:** `AdmissionApplication.next_step` updated per transition (`Accounts review` / `Payment approval` / `Enrollment completed`), `status` single source, `submitted_at`, `office_actor/account_actor` + timestamps, `AuditLog` snapshots. No public status-check endpoint (safe — not exposing PII via guessable URL), internal only. |
| O7 | Existing admission approvals, duplicate-payment/student prevention | **Complete (with small gap)** | `accounts_approve_payment` is `transaction.atomic` + `select_for_update`, checks `status != ACCOUNT_PENDING` → error (prevents double-approve), `SectionCapacity.has_room` pre-check, receipt generation loop with `IntegrityError` retry (3), `application.enrolled_student` set then `status=ENROLLED` (so second POST finds status not ACCOUNT_PENDING). **Duplicate student prevention:** capacity + exact `student_id` collision via model `save()` auto-increment per institution/year, but no name+class duplicate block on application (duplicate detection is list-warning only) — noted as low risk. Tests: `AdmissionApplicationWorkflowTests.test_payment_approval_creates_one_student_and_receipt`। |
| O8 | Student import, archive/restore, promotion/rollback, ID/TC/certificates | **Complete** | **Import:** `import_students` (Excel, Bangla digits, group rules, capacity, guardian contact, idempotent dedupe) + `download_import_template`. **Archive/restore/purge:** soft delete (`is_archived`, `archived_at/by`), `archived_students`, `restore_student`/`bulk_restore`, `purge_archived_student`/`bulk_purge` (POST-only, audited, scoped). **Promotion/rollback:** `student_promotion` + `PromotionBatch.institution` (0037) + `student_promotion_history` + `rollback_student_promotion` (404 if other institution). **ID/TC/certificates:** `student_id_card` + `issue_tc`/`view_tc` + `issue_certificate`/`view_certificate`/`certificate_list` (TransferCharacter/Bonafide etc.) — all `_get_scoped_object_or_404` scoped. Tests: `StudentArchiveSafetyTests`, `PromotionAndAuditTests`, `StudentProfileAndBulkUpdateTests`। |

### 2.3 Dashboard ও মূল ব্যবস্থা

| # | Feature | Status | Evidence |
|---|---|---|---|
| D1 | Role-appropriate dashboard/navigation | **Complete** | `dashboard` institution-scoped counts, `base.html` permission-gated flyouts (Office/Attendance/Exam/Result Analysis/Accounts/Employees), `can_result_analysis` context, Quick actions card (P2-6) gated. Tests `test_navigation.py`। |
| D2 | Developer branding-এর বর্তমান configuration | **Complete** | `SCHOOL_INFO` in `settings.py` (PKFSC name/address/phone) + `school_system/templates/students/base.html` print header + footer `Copyright © 2025 PKFSC · Software by ITOxide` (D2). Configurable via `SCHOOL_INFO` dict, not hardcoded per-page. No extra developer panel. |
| D3 | Production settings, permissions ও institution isolation | **Complete (code) / Unverified (live)** | `settings.py` DEBUG guard + `ImproperlyConfigured` for fallback SECRET_KEY when DEBUG=False, `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`/`TRUST_FORWARDED_PROTO`/`USE_X_FORWARDED_HOST`, `permissions.py` single source + `InstitutionAccess` isolation helpers. Code verified, **live env UNKNOWN** (needs Render check, P0-7)। |
| D4 | Dependency compatibility, CI ও logging | **Complete** | `requirements.txt` + README fallback, `workflows/tests.yml` matrix sqlite + postgres:16 + Node, `manage.py check` + `makemigrations --check` + `backup_smoke_test.sh` both engines + moto S3 mock. Logging via `record_audit` + `AuditLog` + console mail backend. |
| D5 | Database/media backup tooling এবং restore verification-এর প্রমাণ | **Complete (tooling) / Unverified (live schedule)** | `backup_data`/`restore_backup`/`check_backups` + `backup_cron.sh` + `render.cron.yaml` + `scripts/backup_smoke_test.sh` (disposable drill, byte-identical photo, 72 backup tests). Tooling proven locally on sqlite+postgres (CI), **live cron schedule/off-box bucket/health alert not proven** (needs Render, P0-8-live). `docs/BACKUP_AND_RESTORE.md`, `BACKUP_RESTORE_GUIDE.md`, `DATA_SAFETY_STATUS.md` present. |

### 2.4 Attendance

| # | Feature | Status | Evidence |
|---|---|---|---|
| A1 | Entry, daily uniqueness, permissions ও correction history | **Complete** | `AttendanceRecord` unique per `(institution, student/employee, date)` (DB constraint `unique_student_attendance_per_day` etc.), `mark_attendance`/`mark_attendance_bulk` via `update_or_create` (correction = re-POST same date), `_require_department(Office, Exam)`, institution-scoped, `record_audit(..., 'attendance_marked')`. |
| A2 | Unmarked/absent/holiday পার্থক্য | **Complete** | `STATUS_CHOICES` `P/A/L/H` (Present/Absent/Late/Holiday). `H` = holiday/closed, distinct from `A` (student not present but school open). Exams separate: `EXAM_ABSENT_SUBJECT_FAILS` distinguishes entered 0 (fail) vs blank (dash/F) vs not-applicable. Attendance summary counts per status. |
| A3 | Calendar এবং attendance percentage/report accuracy | **Complete** | `attendance_report` (date-ordered, institution-scoped), `attendance_summary` (date range filter `start_date`/`end_date` default 30 days, per-student/employee present/total → `attendance_rate` rounded 1 decimal). `employee_detail` + `student_detail` show last 30 days + rate. Tests `AttendanceTests`। **Gap:** no month-calendar grid UI — list + summary only (backlog A3)। |

### 2.5 Employee

| # | Feature | Status | Evidence |
|---|---|---|---|
| H1 | Existing CRUD/status history | **Complete** | `Employee` CRUD + `change_employee_status` + `EmployeeStatusLog` + history page `employee_status_history`, list/detail scoped, `record_audit` on edit with `changed_fields`. Tests `EmployeeDetailPageTests`। |
| H2 | Teacher-class-subject assignment | **Missing** | `Employee` has `institution` + `designation` + `status` only; no `assigned_class`, `assigned_section`, `assigned_subjects` or timetable. Subject assignment is `SubjectRequirement` (class-level), not teacher-level. Backlog H2. |
| H3 | Leave workflow | **Missing** | Only `Employee.status` (`ACTIVE/INACTIVE/ON_LEAVE`) + free-text status change; no `LeaveApplication` model, no leave balance, no approval flow. Backlog H3 (future). |
| H4 | Salary approval, duplicate prevention ও closed-period controls | **Partial** | `SalarySheet(employee, month, amount, status PAID/UNPAID, created_by)` CRUD, money validators `MinValue(0)`, `finance_dashboard` aggregates. Unique `(employee, month)` prevents duplicate sheet (DB constraint). **Closed-period controls missing** — no “month locked after payroll approval” logic (can edit PAID sheets). Backlog H4. |

### 2.6 গুরুত্বপূর্ণ সীমা (নির্দেশ ৩)

- **SSC Registration / BoardResult intentionally removed** — migration `0035_remove_ssc_registration_and_board_result.py` irreversible, `RetiredBoardFeatureTests` pass, no restore attempted this session.
- **Existing সুবিধা rebuild নয়** — ঘাটতি আলাদা করা হয়েছে (Missing/Partial তালিকা উপরে, duplicate task নয়)।
- **Higher Math তিনটি আলাদা যাচাই** — curriculum (SCI mandatory), DB (migration 0042), assigned (SubjectRequirement) — §2.1 E5 এ আলাদা evidence।
- **Code/tests/PR/live আলাদা** — E1 example: code+tests+PR proposal exists but live behavior incomplete — status Partial with PR evidence আলাদা লেখা।
- **Live data health/backup/migration status** — production access ছাড়া **Unverified** বলা হয়েছে, নিশ্চিত দাবি নয়।

---

## 3. README roadmap vs. actual code (at `44cbcc3` — needs refresh, P0-9)

| README roadmap item | Actual state (verified 2026-09-17) |
|---|---|
| Enforce the exam publish flag on every result view and result-card endpoint | **DONE** — all 5 + full-rank-list + detail/card check `is_published` |
| Add Excel import for exams and bulk exam marks | **DONE** — `import_exam_marks` + template download (`download_marks_import_template`) |
| Add a proper admission application model and application form workflow | **DONE** — `AdmissionApplication` + office→accounts state machine + public form + rate limit |
| Add Office approval and handoff to Accounts | **DONE** |
| Add class-wise Accounts confirmation and payment approval | **DONE** — `Fee` model pre-fills & warns on mismatch |
| Generate receipt numbers and MoneyReceipt records automatically after approved payment | **DONE** — `ADM-YYYY-…` + auto `RC-…` collision-safe |
| Add admission-room next-step status and receipt verification workflow | **PARTIAL** — `next_step` via workflow; no separate receipt-verification step (not requested) |
| Add promotion history, academic session validation, and rollback support | **DONE** (history + rollback + `PromotionBatch.institution`) |
| Add audit history for changes to students, exams, employees, and financial records | **DONE** — audited: archive/restore/purge, exam delete/publish, applications, promotion/rollback, attendance, employee status, edit_student/edit_employee |
| Add automated tests for permissions, imports, result publishing, approvals, and receipts | **DONE** — 555 Django + 6 Node (was 550; +5 new), CI sqlite & `postgres:16` |
| Display subjects and marks on the student detail page | **DONE** — Subjects tab = live `SubjectRequirement` assignments |
| Attendance module (bulk mark, report, summary + sidebar group) | **DONE** |
| Fees and payment workflow enhancements | **DONE** — fee schedule, auto receipts, money validators, rate limiting |
| Switch to PostgreSQL for production | **PARTIAL (CI proven; live switch = owner)** — `DATABASE_URL` wired, CI `postgres:16` green; live `DATABASE_URL` **UNKNOWN** |

**Documentation debt:** README still shows some `[ ]` todo — should be ticked (P0-9 doc-only).

---

## 4. Defects and security findings (current — resolved vs. open)

| ID | Severity | Finding | Status at `44cbcc3` |
|---|---|---|---|
| BUG-1 | High | `student_detail.html` linked missing `tc_print` URL → 500 for TC students | **FIXED** (P0-1) — `view_tc` + real fields; test passes |
| SEC-1/2 | High | `?institution=` override → cross-read | **FIXED** (P0-2) |
| SEC-3 | High | pk-level views no institution check | **FIXED** (P0-3) — `_get_scoped_object_or_404` + 42 isolation tests |
| SEC-4 | High | `student_promotion` cross-institution; `PromotionBatch` no column | **FIXED** (0037) |
| SEC-5 | Medium | `Voucher` no `institution` FK | **FIXED** (0036) |
| SEC-6 | Medium | `public_admission_apply` no rate limit | **FIXED** (5/10min) |
| SEC-7 | Medium | Money fields negative/absurd | **FIXED** (`MinValue(0)`) |
| SEC-L1/L2/L3 | Low | Session fallback / `09` vs `9` / `import_students` capacity | **FIXED** (P1-8, P1-7) |
| PERM-1 | Low | `setup_groups` vs `permissions.py` drift | **FIXED** (P0-11) |
| CONTACT | — | Two contact columns | **FIXED** (0039-0042) |
| E1-GAP | Low | Import redirect goes to exam_list not import page | **FIXED** (PR #29) — `import_exam_marks` now stays on the same page with `?subject=..&group=..`; `test_import_stay_on_page_redirects_to_same_page` |
| O2-GAP | Low | No pagination (max 100) | **FIXED** (PR #29) — `student_list` / `archived_students` paginate at 100; `test_pagination_limits_to_100` |
| E8-GAP | Low | No Ctrl+Click correction shortcut | **FIXED** — `result_cell_shortcut.js` + `data-subject-pk`/`data-group` cells (2026-09-17); backlog E8 |

---

## 5. Data / fixture context

- `institutions.json`: 6 institutions — makes isolation tests meaningful.
- `students_data.json`: 254 students (2026), 251 in pk 2 (School).
- **Unknown live:** production DB content, years, volume — fixtures are example data only (rule 7).

## 6. Test suite map (৬৭০ Django + ১৪ Node — re-verified ২০২৬-০৯-২০, §20)

**Python (`manage.py test students`): 670 pass in ~247s** (৬২৫ baseline +১৩ EX-01 +১৫ EX-02 +১৫ EX-03 +২ EX-03-finishing; এই checkout `7a13e33`+0044·Δ=৬৭০, ২০২৬-০৯-২০-এ নিজে চালানো)।
Isolation: 16 + 34 tests; Students/Admission/Exams/Attendance/HR/Finance/Backup/Media/SSC retirement as in previous §6 plus 72 backup tests (encryption/file modes/off-box stub/SHA/retention/health-gate), 33 media tests, +১৫ EX-01 `test_navigation`, +১৫ `test_register_roll_order`, +১৭ `test_group_based_mark_evaluation` (১৫ +২ weekly-column pin)।

**Node: 14 pass** — `student_row_actions.test.js` (৬) + `result_cell_shortcut.test.js` (৮) — `node --test students/js/*.test.js`,
২০২৬-০৯-২০-এ re-verified।

**Not yet automated (intentional deferrals):** `P2-3` i18n, `P2-7` drop `StudentSubject`.

---

## 7. Unknown production state (explicit — rule 7)

1. Live DB engine + size + ephemeral disk.
2. Render env: `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `TRUST_FORWARDED_PROTO`.
3. Persistent disk / object-storage for media & backups.
4. How many institutions live.
5. Live group/permission state.
6. Whether `merge_duplicate_subjects --apply` run.
7. Backup scheduling / off-box / health check.
8. Whether migration 0035 already ran.
9. Whether live upload→redeploy proven.

---

## 8–18. Prior session history

Prior sections 8–18 from the 2026-09-16 document are preserved in git history (`git show main:docs/PROJECT_STATUS.md` or `git log -- docs/PROJECT_STATUS.md`). Summary: security audit (P0-1/5/11), read/write isolation (SEC-1..3), backup runbook (P0-8), voucher/promotion isolation (0036/0037), P1 backlog (Fee, auto-receipt, attendance nav, curriculum tab, class choices, capacity, zero-padding, rate limit), P2 items (CI, login lockout, audit, quick links), media S3 (P1-11), and 2026-09-16 isolated verification (452 tests) — all merged via PRs #10–#27. This session (2026-09-17) intentionally adds **no feature code**, only audit docs + baseline.

---

## 19. Session 01 — 2026-09-17 · বর্তমান অবস্থা যাচাই, test baseline এবং চূড়ান্ত backlog (this session)

**Scope (অনুমোদিত):** শুধু audit documentation + isolated test baseline + সীমিত local test setup; কোনো বড় feature, grading/GPA policy change, production data cleanup, live deploy, paid service activation নয়। SSC restore নয়।

### 19.1 Checks (see §1 table)

- **Branch/commit/working tree/base/remote** verified clean, `44cbcc3` = `origin/main`.
- **Dependencies:** `/tmp/audit_venv` Django 5.2.17, `check` 0, `check --deploy` 6 dev warnings, `makemigrations --check` clean, 0001–0042 synced.
- **Tests:** `manage.py test students` **550 pass**, `node --test` **6 pass** — previous 452 → +98 backup/media tests (backup now 72 vs 14). No production DB used, no secrets, disposable test data.
- **SSC retirement:** still guarded, no restore.

### 19.2 Audit produced (see §2)

- Full **Complete/Partial/Missing/Unverified** matrix for Exam (9 items), Office (8), Dashboard (5), Attendance (3), Employee (4) — each with file/line evidence and acceptance split. Existing feature rebuilt নয়, ঘাটতি আলাদা করা হয়েছে।
- **Higher Math** curriculum/DB/assigned separately verified (E5).
- **GPA 4.90–5.00→5.00 rule** verified absent — no such rounding exists — decision required before implementation (D-GPA, two PRs planned per instruction).
- **Accounts fee engine / guardian portal / online payment** intentionally **out of implementation scope** — future backlog (as instructed §7).
- **Code vs tests vs PR vs live** separated per finding (e.g., E1: code/tests done, PR #23 proposed, live behavior still redirects).

### 19.3 Docs updated this session

- `docs/PROJECT_STATUS.md` — header bumped to `44cbcc3` 2026-09-17, §1 refreshed (550 tests), §2 replaced with detailed Exam/Office/Dashboard/Attendance/Employee audit (§2.1–2.6), §4/§6/§7 synced, new §19.
- `docs/TASK_BACKLOG.md` — rebuilt remaining backlog with ID/purpose/status/evidence/priority/dependencies/acceptance/tests/migration-risk/decision/small-session-scope per task; priority follows verification → security & backup → quick fixes → subject & result → Office → Attendance/Employee → Dashboard → final verification; GPA/missing-marks two-PR decision tasks added; future large expansions (fee engine, guardian portal, online payment) in Future Backlog.
- `docs/DEVELOPMENT_GUIDE.md` — **new** (local setup PY 3.11/3.12, branch rule, common commands, project structure, institution/permission model, workflows, testing, backup drill, conventions).
- `docs/HANDOFF.md` — new § for 2026-09-17 with verification, audit summary, next session recommendation.

### 19.4 Remaining work (see `TASK_BACKLOG.md` §Remaining)

Owner-only live ops (P0-7, P0-8-live, P1-11-live) + quick fixes (pagination 100, import stay-on-page, Ctrl+Click) + subject/result gaps (GPA decision, missing-marks two PRs) + Office gaps (Reports, photo continuity) + Attendance calendar + Employee assignments/leave/closed-period + two large deferrals (P2-3 i18n, P2-7 drop legacy) + doc tick (P0-9). Full detail per task in `TASK_BACKLOG.md`.

**No feature code, no migration, no grading/policy change, no destructive command, no live deploy in this session.**


---

## 20. Sessions 00–03 — ২০২৬-০৯-১৯→২০২৬-০৯-২০ · baseline + EX-01/EX-02/EX-03

**Scope:** শুধু যাচাই + ডকুমেন্টেশন (prompt §২) — **কোনো feature code, migration, template বা live কাজ নয়**।
**Branch:** `arena/01a0b9da-school-management-system` · **Base:** `8b7aa62` = `origin/main` (Merge PR #35) · working tree clean।
**পূর্ণ matrix + প্রমাণ (file:line, view, test নাম):** `docs/prompts/reports/০০-baseline.md`।

### 20.1 যাচাই কমান্ড ও ফল — সর্বশেষ EX-03 (isolated venv, Django 5.2.17 fallback)

| কমান্ড | ফল |
|---|---|
| `python manage.py check` | `0 issues` |
| `python manage.py check --deploy` | ৬ warning (`W004 W008 W009 W012 W016 W018`) — প্রত্যাশিত dev expectation |
| `python manage.py makemigrations --check` | `No changes detected` — models ⇄ migrations `0001`–**`0044`** synced (EX-03 `group` migration) |
| `python manage.py test students` | **`Ran 670 tests in ~247s` → `OK`** (৬২৫ +১৩ EX-01 +১৫ EX-02 +১৫ EX-03 +২ EX-03-finishing) |
| `node --test students/js/*.test.js` | **14 pass / 0 fail** (৮ shortcut + ৬ row-action) |
| `./scripts/backup_smoke_test.sh` | **১৫ step pass / ০ fail** (disposable sqlite, plaintext + encrypted, SHA verify, wrong-passphrase reject) |
| `moto_server` + `backup_smoke_test.sh --s3-endpoint …` | **২৮ step pass / ০ fail** (off-box upload → `--check-remote` → `fetch_backup` → restore → retention ২) |

**CI (PR #42, `gh pr checks 42`):** `test (sqlite, 3.12)` **pass** 5m22s · `test (postgres, 3.12)` **pass** 7m24s · `Node` **pass** 5s — postgres:16-এও suite সবুজ (run 35490969199, 7m28s)। **PR #41**-ও একইভাবে pass (sqlite 6m19s / postgres 6m39s / Node 5s)।

`RetiredBoardFeatureTests` সহ পুরো suite pass ⇒ SSC Registration/BoardResult পুনরুদ্ধার হয়নি।
কোনো production DB/credential/Render/S3 আসল bucket ছোঁয়া হয়নি; `.restore-drill/` নিজেই পরিষ্কার হয়েছে।

### 20.2 ২৮-সেশনের verdict (সংক্ষেপ)

| Verdict | সেশন |
|---|---|
| **Complete** (যাচাই করা: ইতিমধ্যে সম্পন্ন — শুধু regression + EX-01/02/03) | **EX-01** (Analysis subtab + import preserve, PR #39), **EX-02** (register/roll order, PR #41), **EX-03** (group-aware marks, 0044, PR পরবর্তী), **EX-04, EX-05, EX-06, EX-07, OF-01, OF-03, OF-04, DB-01, DB-04, DB-05, DB-06** (+ OF-02-এর ৪টি view pagination আগেই ছিল) |
| **Partial** (মূল অংশ আছে, নির্দিষ্ট কাজ বাকি) | **OF-02** (বাকি ৭টি list view pagination), **OF-05** (ছবি continuity), **OF-06** (progress page), **DB-02** (agent নামের comment), **DB-03** (SEC-FU-1/2), **AT-01** (per-record correction), **EM-03** (closed-period lock) |
| **Missing** | **AT-02** (calendar view), **EM-01** (teacher assignment), **EM-02** (leave — ⛔ owner-policy ছাড়া কোড নয়) |
| **Unverified** | **OF-07 / OF-08** (audit-সেশন এখনো চালানো হয়নি), **FN-01** (২৭টির পরে), + সব live-only অংশ |

### 20.3 বাকি কাজ (সংশোধিত — ২০২৬-০৯-২০, EX-03-পরবর্তী)

~~১. EX-01 Analysis subtab~~ ✅ · ~~২. EX-02 বাকি output-order~~ ✅ · ~~৩. EX-03 `SubjectMarkSetting.group`~~ ✅ (0044) ·
৪. OF-02 বাকি ৭টি list view-এ pagination · ৫. OF-05 admission photo + list photo + purge-এ ফাইল মুছে ফেলা ·
৬. OF-06 public progress/status page · ৭. OF-07/OF-08 audit · ৮. DB-02 `migrations/0034`-এর agent-নামের comment ·
৯. DB-03 SEC-FU-1/2 · ১০. AT-01 per-record correction · ১১. AT-02 calendar view · ১২. EM-01 assignment · ১৩. EM-03 closed-period · ১৪. FN-01 release যাচাই।

বিস্তারিত ও priority: `docs/TASK_BACKLOG.md` §Remaining (২০২৬-০৯-২০ update-log সহ)।

### 20.4 owner-সিদ্ধান্ত (সর্বশেষ)

- ~~OPEN PR #36/37/38~~ — EX-01 PR #39 ✅ ও EX-02 PR #41 ✅ MERGED (৭a13e33); EX-03 PR পরবর্তী — owner merge-অনুমোদন বাকি।
- **EX-03 owner-সিদ্ধান্ত ৩টি (সেশনের শুরুতে জিজ্ঞেস করে নেওয়া):** parts **exact** (=full), weekly **MID_TERM_* only**, group **9-12 only** (<৯ blank) — প্রয়োগ করা, পরীক্ষা করা।
- **EM-02 leave নীতি** — এখনো ⛔ blocked (লিখিত কোড-পূর্ব নীতি ছাড়া নয়)।
- DB-04-এর HSTS/SSL-redirect/secure-cookie (live) — `check --deploy`-এর ৬ warning-এর মূল কারণ।
- README §৭-এর বাকি সারি (EX-06/EX-07/OF-02/OF-05/OF-06/OF-07/OF-08/AT-01/AT-02/EM-01/EM-03) + weekly_test column hide (ভবিষ্যতে)।

**এই সেশন (EX-03):** code+migration+tests+docs — single append-only migration 0044, no destructive command, no live deploy (owner merge-অনুমোদন বাকি)।
