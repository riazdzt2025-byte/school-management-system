# ০০ — Baseline (প্রম্পট ০১ / ২৮) · সেশন ০০

_তারিখ (UTC): ২০২৬-০৯-১৯ · ধরন: যাচাই + ডকুমেন্টেশন (কোনো feature code, migration বা live কাজ নয়)_
_branch: `arena/01a0b9da-school-management-system` · base = `origin/main` @ `8b7aa62` (Merge PR #35)_
_সেশন-ID: `০০` · প্রম্পট ফাইল: `docs/prompts/prompt-01-session-00-baseline.md`_

> এই ফাইলটিই ২৮-সেশনের **initial verdict matrix** (প্রম্পট ০১-এর প্রধান deliverable)। এখানে
> প্রতিটি দাবির পাশে code-এবidence (file:line / view / test নাম) আছে; যেখানে নিজে চালিয়ে
> যাচাই করা হয়নি, সেখানে স্পষ্টভাবে **Unverified** লেখা আছে — কোনো দাবি ledger থেকে
> অনুলিপি করা হয়নি।

---

## ১. Checkout ও branch যাচাই (দাবি নয় — কমান্ডের ফল)

| যাচাই | ফল |
|---|---|
| `git rev-parse HEAD` | `8b7aa62cd71d76c04f99043f46b24a978a2a78dd` |
| `git rev-parse origin/main` | `8b7aa62cd71d76c04f99043f46b24a978a2a78dd` (**একই**) |
| `git log --oneline -1` | `8b7aa62 Merge pull request #35: লিংকগুলো main-এ (PR #34 merge-এর পরের sync)` |
| `git status --porcelain` | খালি — working tree clean (কোনো pre-existing uncommitted change নেই) |
| একটি মাত্র commit ইতিহাস | এই checkout-এ আগের **কোনো প্রম্পট-সেশনের commit নেই** → প্রম্পট ০১ ই সত্যিকারের প্রথম ধাপ |
| fork/branch নিয়ম | সব কাজ `arena/01a0b9da-school-management-system`-এ; `reset --hard`/`git clean`/force-push নেই |

⚠️ **প্রম্পট-ফাইলের প্রেক্ষাপট এখন পুরোনো (stale):** `prompt-01-*.md` §১-এ base লেখা আছে
`f64194a` = `origin/main` (Merge PR #33)। তারপর `main`-এ **PR #34** (২৮-সেশন প্রম্পট প্ল্যান)
ও **PR #35** (লিংক sync) merge হয়েছে, তাই বর্তমান base `8b7aa62`। ২৭টি future prompt-এর
প্রেক্ষাপট-section-ও একই কারণে "তারিখ-পিছিয়ে" — নম্বর/ক্রম অপরিবর্তিত, শুধু base নতুন।

⚠️ **সমান্তরাল সেশন দুটি:** PR **#36** (`arena/01a0b835-…`) ও PR **#37** (`arena/01a0b85c-…`)
দুটোই "০০ / prompt 01" শিরোনামে **খোলা (OPEN, merge হয়নি)** এবং একই ডক-ফাইল ছোঁয়
(`PROGRESS.md`, `reports/০০-baseline.md`, `PROJECT_STATUS.md`, `TASK_BACKLOG.md`, `HANDOFF.md`)।
এগুলো `main`-এ নেই, তাই এই baseline-এর কোনো অংশ ওগুলোর উপর নির্ভর করে না। merge-এর সময়
কোনটি রাখবেন সেটি owner-সিদ্ধান্ত (নাহলে একই ফাইলে conflict হবে)।

`gh pr list` (state=all, প্রথম ৮টি): #35 MERGED · #34 MERGED · #33 MERGED · #32 MERGED ·
#31 MERGED · #30 MERGED · **#36 OPEN** · **#37 OPEN**।

---

## ২. যাচাই কমান্ড ও প্রকৃত ফল (এই checkout, isolated venv)

**Environment:** Python 3.11.2 · Node v22.22.3 · `python3 -m venv /tmp/audit_venv` →
`pip install "Django>=5.2,<6" openpyxl Pillow python-dotenv dj-database-url whitenoise psycopg2-binary django-storages boto3`
→ **Django 5.2.17** (README-এর documented fallback; `requirements.txt`-এ `Django==6.1` = Python 3.12+, এই sandbox-এ চলে না)।
টেস্ট DB = throwaway SQLite; কোনো production DB/credential ছোঁয়া হয়নি।

| কমান্ড | ফল (হুবহু) | সময় |
|---|---|---|
| `python manage.py check` | `System check identified no issues (0 silenced).` | 0.5s |
| `python manage.py check --deploy` (DEBUG=True) | `System check identified 6 issues (0 silenced).` → `security.W004, W008, W009, W012, W016, W018` — প্রত্যাশিত dev-default warning, exit 0 | 0.9s |
| `python manage.py makemigrations --check` | `No changes detected` (models ⇄ migrations 0001–**0043** synced) | ~1s |
| `python manage.py test students --verbosity 1` | **`Ran 625 tests in 231.431s` → `OK`** (exit 0, 0 failure/0 error) | 3m52s |
| `node --test students/js/*.test.js` | `# tests 14 · # pass 14 · # fail 0` (`result_cell_shortcut.test.js` ৮ + `student_row_actions.test.js` ৬) | 0.2s |
| `./scripts/backup_smoke_test.sh` (sqlite, disposable) | **`steps passed: 15, failed: 0` — RESULT: PASSED** (plaintext + encrypted restore, SHA verify, wrong-passphrase reject, photo byte-identical) | 9.9s |
| `moto_server` + `./scripts/backup_smoke_test.sh --s3-endpoint http://127.0.0.1:5055` | **`steps passed: 28, failed: 0` — RESULT: PASSED** (upload → `check_backups --check-remote` → `fetch_backup` → restore → remote retention = 2) | 17.3s |

**Baseline সংখ্যা নিশ্চিত:** পুরোনো দাবি "৬২৫ Django + ১৪ Node" **সঠিক** — এই checkout-এ নিজে
চালিয়ে প্রমাণিত (একটি সংখ্যাও বদলায়নি)। `.restore-drill/` স্ক্রিপ্ট নিজেই মুছে ফেলে; কাজ শেষে
`git status` আবার clean।

`RetiredBoardFeatureTests` সহ পুরো suite pass → SSC Registration/BoardResult পুনরুদ্ধার হয়নি
(কোড-এ শুধু migration 0008/0032/0035 + `students/tests.py:2777`-এর assert)।

---

## ৩. Inventory (যাচাই করা আকার)

| জিনিস | সংখ্যা / প্রমাণ |
|---|---|
| `students/urls.py` | 118 লাইন, **১০৫টি `path()`** route |
| `students/views.py` | 5,100 লাইন, **১৬৫টি top-level view/helper function** |
| `students/models.py` | 1,026 লাইন, **২৬টি model class** |
| `students/result_utils.py` | 1,028 লাইন (ফলাফলের একক source) |
| migrations | ৪৪টি ফাইল (`0001`–**`0043_auditlog_institution`** = leaf ✅) |
| টেস্ট | `students/tests.py` (2,935 লাইন, 35 class) + **২৩টি** `students/test_*.py` |
| Node টেস্ট | `students/js/result_cell_shortcut.test.js` + `students/js/student_row_actions.test.js` (১৪ test) |
| Templates | `students/templates/students/*.html` ৭৩টি + `school_system/templates/students/`-এ **৭টি override** (`add_student`, `archived_students`, `dashboard`, `delete_student`, `login`, `student_detail`, `student_list`) |
| CI | `.github/workflows/tests.yml` (১৮১ লাইন): matrix **sqlite + postgres:16**, ৩টি deploy-guard ধাপ, Node job, backup smoke test, moto S3 off-box drill |
| Custom checks | `students/checks.py`: `students.E011`, `E013`, `E016`, `W010`, `W014`, `W015` |
| Scoping helper (`views.py`) | `_is_admin`, `_institutionally_scoped`, `_scoped_institution_ids`, `_user_can_access_institution`, `_get_scoped_object_or_404`, `_resolve_requested_institution`, `_scope_by_allowed_institutions`, `_scope_institution_qs`, `_scope_write_queryset`, `_visible_institutions`, `_institution_ids_outside`, `_selected_institution_for_request`, `_filter_by_selected_institution`, `_require_department` |
| Command | `backup_data`, `restore_backup`, `check_backups`, `fetch_backup`, `copy_media_to_storage`, `seed_subjects`, `seed_subject_requirements`, `setup_groups`, `grant_institution_access`, `contact_conflict_report`, `merge_duplicate_subjects`, `clean_student_groups` |
| Scripts | `scripts/backup.sh`, `restore.sh`, `backup_cron.sh`, `backup_smoke_test.sh` (+ prompt tooling) |

---

## ৪. ২৮-সেশনের verdict matrix (এই checkout-এ যাচাই করা)

**Verdict মানে:** `Complete` = চাহিদা কোডে আছে **এবং** টেস্টে প্রমাণ আছে → সেশনটি শুধু
regression যাচাই করবে · `Partial` = মূল অংশ আছে, নির্দিষ্ট ঘাটতি বাকি → সত্যিকারের কাজ আছে ·
`Missing` = কিছুই নেই · `Unverified` = এই sandbox থেকে প্রমাণ করা সম্ভব নয় (live) বা সেশনটির
deliverable এখনো তৈরি হয়নি (audit-session)।

### প্রাথমিক

| # | সেশন | Verdict | প্রমাণ (file:line / test) | এখনকার অবস্থা → দরকার কি না |
|---|---|---|---|---|
| ০১ | ০০ baseline | **✅ এই সেশনেই সম্পন্ন** | এই ফাইল + §২-এর কমান্ড ফল | হয়েছিল → নতুন baseline দরকার নেই |

### Exam (EX-01…EX-07)

| # | সেশন | Verdict | প্রমাণ | দরকার কি না |
|---|---|---|---|---|
| ০২ | EX-01 Import redirect + Analysis subtab | **Partial** | redirect ✅: `views.py:3803-3810` (`redirect(reverse('import_exam_marks')…+'?subject=…&group=…')`, কমেন্ট "Stay on the same import page … (E1)") + regression test `tests.py:2915 test_import_stay_on_page_redirects_to_same_page`। subtab ❌: `base.html:221-232` = Exam flyout (Enter Marks/Exam List/Mark Evaluation), `base.html:233-243` = **আলাদা "Result Analysis" group** (৫ link, `can_result_analysis` gated) | import অংশ **ইতিমধ্যে সম্পন্ন**; বাকি শুধু Analysis **subtab placement** → EX-01 প্রম্পটের আসল কাজ + owner-সিদ্ধান্ত ২টি |
| ০৩ | EX-02 roll-order | **Partial** | register outputs ✅: `views.py:4078-4090` (`result_sheet` sorted key `(roll_no is None, roll_no, name.lower(), pk)`), `result_utils.py:994-996`+`1025-1027` (একই key row-level-এ), `views.py:1610` (`student_list`), `views.py:1693` (`download_student_list` Excel), `views.py:4968` (`result_analysis_multi_term`), base query `result_utils.py:52 get_exam_students → order_by('roll_no','name')` ⇒ seat plan/signature sheet-ও numeric roll; merit order অপরিবর্তিত (`result_utils.py:1005` কমেন্ট, `full_rank_list`/`top_10` position-ভিত্তিক) | ৯টি output-এর মধ্যে প্রধানগুলো ✅; আসল বাকি = বাকি output-গুলোর নিয়ম-লিখন (`exam_result_summary`, `class_section_summary`, `attendance_report` class-wise list, print CSS) + নিয়ম draft — সেই সেশনের কাজই বৈধ |
| ০৪ | EX-03 Group-based Mark Evaluation | **Partial (dev work বাকি)** | **`SubjectMarkSetting`-এ group field নেই** — `models.py:779-812`: ফিল্ড = `institution, admission_class, subject, exam_type, full_marks, cq_marks, mcq_marks, practical_marks, weekly_test_marks, is_active`; unique = `(institution, admission_class, subject, exam_type)`। group-aware **UI** আছে: `views.py:2602+ mark_evaluation_settings` (`group` param, `group_choices` from `SubjectRequirement`), `_exam_group_selection`, মডেল-স্তরের group আসে `SubjectRequirement.group` (অফার/তালিকা) থেকে | গোপন না: group-ভিত্তিক **তালিকা/ফিল্টার** কাজ করে, কিন্তু group-ভিত্তিক **নম্বর-স্কিম সংরক্ষণ** নেই → নতুন মডেল-ফিল্ড + unique-constraint পরিবর্ত + append-only migration + UI + test। owner-সিদ্ধান্ত ৩টি (§৭ EX-03) আগে দরকার |
| ০৫ | EX-04 Higher Math workflow | **Complete — verify-first** | curriculum: `curriculum_data.py:42` (`HMATH`), `:135` SSC SCI **MANDATORY**, `:179` HSC SCI **OPTIONAL `sci_4th`** · migration `0042_higher_math_mandatory_science.py` (9/09/10 SCI → MANDATORY, reverse → OPTIONAL) · seeds `seed_subjects`/`seed_subject_requirements` (দুই কমান্ড বিদ্যমান) · tests: `test_result_analysis.py:57 test_ssc_higher_math_is_mandatory` (+ `:60-75` Biology/HSC/Business সহ ৪টি negative), `test_new_subject_result_workflow.py` (47 test), `test_subject_assignment_office.py` (28) | **যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে**। owner-প্রশ্ন ৩টি (§৭ EX-04) শুধু পরিবর্তন করলে প্রযোজ্য |
| ০৬ | EX-05 missing marks → Absent/Fail | **Complete** | একক source: `result_utils.py:589 compute_subject_result` + `:547 absent_subject_fails_result()` → `settings.py:346 EXAM_ABSENT_SUBJECT_FAILS` **default True** (`:343-346` কমেন্ট সহ) · `ABSENT = '-'` (`result_utils.py:544`) · সব-ফাঁকা → `overall_gpa=None, grade=ABSENT, status='No Marks'` (`result_utils.py:914`) · AB display: `result_sheet.html:480,487,530` (+legend L530) · tests: `tests.py:2869 test_absent_shows_AB_and_counts_as_F` (`'AB'`, `'absent-mark'`, `status='Fail'`, `gpa='0.00'` assert), `students/tests.py:1313` (`override_settings(EXAM_ABSENT_SUBJECT_FAILS=False)`), `AbsentSubjectRulesTests`, `MarksPartsAndPassRulesTests` · সব result view একই source: `views.py:4087,4172,4194,4224,4253,4963,4982,4996` → `build_exam_results` | **যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে**। ছোট open item: `AB` token শুধু register/result_sheet-এ; result card-এ শব্দ "absent" (`result_card.html`), rank list-এ "(N absent)" — সব জায়গায় token এক করতে হলে ছোট সিদ্ধান্ত |
| ০৭ | EX-06 GPA 4.90–5.00 → 5.00 | **Complete** | `result_utils.py:925-930` — `if Decimal('4.90') <= overall_gpa < Decimal('5.00'): overall_gpa = Decimal('5.00'); overall_grade = 'A+'`, owner-decision কমেন্ট (2026-09-17) সহ, শুধু passing result-এ (has_fail branch `:917-920` আলাদা) · test `tests.py:2829 test_gpa_490_to_499_boosted_to_500` (9×80 + 1×70 = avg exactly 4.90 → 5.00) · rounding boundary হাতে যাচাই: `round(Decimal('4.895'),2) = 4.90` ⇒ 4.895-ও boost হয় (4.894 → 4.89, boost নয়) | **যাচাই করা: ইতিমধ্যে সম্পন্ন**। owner-প্রশ্ন (§৭ EX-06 "4.895 → 4.90 না 4.89") code-এর বর্তমান আচরণে **4.90/boost** — শুধু নিশ্চিতকরণ বাকি, কোড বদলানোর দরকার নেই |
| ০৮ | EX-07 Ctrl/Cmd+Click | **Complete (core)** | JS `students/static/students/js/result_cell_shortcut.js` + Node test ৮টি (`result_cell_shortcut.test.js`) · cells: `result_sheet.html:422` (`data-enter-marks-base`), `:474` (`data-subject-pk`, Religion-এ `sr.paper.pk`), `:475` (`data-group`) · দ্বিতীয় পেজ: `full_rank_list.html:79-80,126-127` (`data-shortcut-url`, permission ছাড়া `data-shortcut-disabled="true"`) · Django tests `test_published_lock_and_cell_shortcut.py` (`:183` url+group, `:211` permission-off, `:222` rank-list row link) | **যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে**। prompt-এ "বাকি" বলা তালিকা আসলে owner-scope প্রশ্ন (আর কোন পেজে, mobile/touch, permission set) — §৭ EX-07 |

### Office (OF-01…OF-08)

| # | সেশন | Verdict | প্রমাণ | দরকার কি না |
|---|---|---|---|---|
| ০৯ | OF-01 একটি Guardian Contact | **Complete** | migrations `0039` (backfill) → `0040` (legacy archive + `RemoveField`) → `0041` (required) বিদ্যমান (`students/migrations/0039-0041`) · canonical `Student.guardian_contact_no` (130 ব্যবহার site) · `forms.py:76` কমেন্ট (legacy column 0040-এ গেছে), `forms.py`-এ `GUARDIAN_CONTACT_RE`/`normalize_guardian_contact`/`validate_guardian_contact` · legacy নাম বাকি শুধু: `Employee.contact_no` (আলাদা মডেল, বৈধ) + `contact_conflict_report` কমান্ড (legacy column অনুপস্থিতি handle করে) · tests `test_guardian_contact.py` (৯ class / ৩৯ test: normalization, form, admission form, Excel import, export, enrolment, search, migration TransactionTestCase, conflict report) | **যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে**। দুই নম্বরের প্রদর্শন/দ্বিতীয় ইনপুট template-এ নেই (grep প্রমাণ) |
| ১০ | OF-02 pagination সর্বোচ্চ ১০০ | **Partial** | ✅ `Paginator(..., 100)`: `views.py:1250 attendance_report`, `:1501 employee_list`, `:1631 student_list`, `:2228 archived_students` · ❌ pagination নেই (reading করেছি প্রতি view): `money_receipt_list:4482`, `voucher_list:4533`, `salary_sheet_list:4588`, `audit_log_list:4820`, `admission_application_list:561`, `exam_list:3456`, `subject_requirement_list:2818`, `student_exams:2419`, `certificate_list:2109`, `student_promotion_history:4799`, `accounts_admission_queue:759` · export `download_*` ইচ্ছাকৃতভাবে full-data (রাখতে হবে) | ৪/১৫ view সম্পন্ন → **আসল কাজ বাকি** (১১টি list view) + owner-প্রশ্ন (fixed ১০০ বনাম নির্বাচনযোগ্য) |
| ১১ | OF-03 Subject Assignment Office subtab | **Complete** | nav `base.html:198` (`perms.students.view_subjectrequirement` → `subject_requirement_list`), `:199`/`:229` (`perms.students.change_subject` → `mark_evaluation_settings`) · routes `subject-requirements/…` + `api/subject-requirements/` (`urls.py`) · tests `test_subject_assignment_office.py` (৪ class/২৮ test), `test_navigation.py` (৫) | **যাচাই করা: ইতিমধ্যে সম্পন্ন — শুধু regression** |
| ১২ | OF-04 Admission reports | **Complete** | `views.py:1146 admission_funnel_report`, `:1174 admission_funnel_export`; funnel helpers `_funnel_stages:998`, `_admission_funnel_queryset:1027`, counts/summary/by-institution `:1077-1145` · `class_section_summary:940`, `download_admission_sheet:576` · tests `test_admission_funnel_report.py` (২০) · PR #32 MERGED, #33 MERGED | **যাচাই করা: ইতিমধ্যে সম্পন্ন**। capacity/trend chart = আলাদা optional `ADM-REPORTS-OPT-1` (এখনো নেই, মূল চাহিদার অংশ নয়) |
| ১৩ | OF-05 Student photos | **Partial** | ✅ `Student.photo = ImageField(upload_to='student_photos/', blank=True, null=True)` (`models.py:252`), form-এ 2MB/type check, widget `accept="image/*"` (`tests.py:407 test_student_form_includes_photo_field`); storage tests `test_upload_security.py` (১০) + `test_media_storage.py` (৩৩, private bucket/`student_photos/` resolve সহ) · ❌ **student list টেমপ্লেটে photo নেই** (`school_system/…/student_list.html`-এ `photo` grep = 0; ছবি ব্যবহার শুধু `id_card_print.html` + `result_analysis_merit_slides.html` + `add_student.html`) · ❌ `AdmissionApplication`-এ **কোনো photo field নেই** (`models.py:458-527`) ⇒ admission থেকেই ছবি আসে না · ❌ purge-এ ছবি ফাইল মোছে না: `views.py:2312-2334 _purge_archived_student` → শুধু `student.delete()` (Django file delete করে না) | **আসল কাজ বাকি** (৩টি গ্যাপ) + owner-সিদ্ধান্ত ৩টি (§৭ OF-05) |
| ১৪ | OF-06 public success + progress | **Partial** | ✅ `views.py:674-681 public_admission_apply` POST → `public_admission_success.html` (application number/class/session alert); rate limit `:665-671` (৫/১০ মিনিট per IP) + `test_rate_limiting.py:19,77` · ❌ public **status/progress route নেই** — `students/urls.py`-এ কোনো tracking/status path নেই (`progress`/`tracking` grep = 0) · ❌ success/apply template-এ WhatsApp/copy share নেই (দুই ফাইলেই `whatsapp|clipboard|cop` grep = 0); share link আছে শুধু internal `admission_application_list.html`-এ (O4) · template-এ নিজেই লেখা "…use the application number above to check the status" ⇒ যে পেজ নেই তার দিকেই ইঙ্গিত | মূল success পেজ ✅; **progress/status page + (হয়) share — আসল কাজ বাকি**, owner-সিদ্ধান্ত ২টি |
| ১৫ | OF-07 admission/import integrity | **Unverified (audit-only session)** | code guard আছে: capacity skip `views.py:3353-3364` (+`SectionCapacity.has_room` `models.py:329`), zero-pad tolerance `:2449/2493/2615/2844` ('9'↔'09'), clerk scoping (SEC-IMPORT), row-level error report; enrolment path `accounts_approve_payment:854` (Student + auto `MoneyReceipt` + subject auto-assign + `Fee` pre-fill), `admission_application_id`-তে `_rate_limit_exceeded`; tests `test_import_capacity.py` (২), isolation (২৪+৪৪), `test_money_validation.py` (৮), `test_auto_receipts.py` (৩) | এই সেশনের deliverable = **integrity audit** (happy path + boundary + failure) — সেটি এখনো করা হয়নি ⇒ verdict Unverified (কোড-ঘাটতি নয়)। owner-নীতি প্রশ্ন ৩টি (§৭ OF-07) আগে দরকার |
| ১৬ | OF-08 archive/promotion/certificates | **Unverified (audit-only session)** | code আছে: `archived_students:2217`, `restore_student:2247`, `bulk_restore_students:2277`, `_purge_archived_student:2312`, `purge_archived_student:2337`, `bulk_purge_archived_students:2357`, `discontinue_student:2383`; promotion `student_promotion:4691`, `student_promotion_history:4799`, `rollback_student_promotion:4754` + `PromotionBatch.institution` (0037) + `StudentPromotionHistory.source_roll_no` (0021); certificates `issue_tc:2033`, `view_tc:2063`, `issue_certificate:2076`, `view_certificate:2098`, `certificate_list:2109`, `student_id_card:2407`; tests: `tests.py:63/95/114/143/157/167/183`, `:568` (TC 500-regression), isolation `test_institution_isolation.py:266`, write-isolation `:358/370/402/419/561` | audit-সেশনের ফলের অপেক্ষায় (verdict Unverified) + owner-প্রশ্ন ৩টি (§৭ OF-08) |

### Dashboard / মূল ব্যবস্থা (DB-01…DB-06)

| # | সেশন | Verdict | প্রমাণ | দরকার কি না |
|---|---|---|---|---|
| ১৭ | DB-01 Dashboard/navigation | **Complete** | `views.py:529-557 dashboard` — `total_students` শুধু `status='ACTIVE', is_archived=False` + institution scope (`_scope_by_allowed_institutions` fallback), `total_institutions = _visible_institutions(request).count()`, `classes`/`sessions` একই scoped qs থেকে (N+1 নেই: ৩ aggregate + ২ values_list) · template override `school_system/templates/students/dashboard.html` · nav `students/templates/students/base.html` (৭ group + flyout + `Ctrl+B` + print-hide) · tests `test_navigation.py` (৫: attendance/promotion gating ×৩, quick-links visible/hidden ×২) | **যাচাই করা: ইতিমধ্যে সম্পন্ন — শুধু regression** (nav URL গুলো named-reverse দিয়ে টেস্টে dhরা) |
| ১৮ | DB-02 Developer branding | **Partial** | ✅ admin branding `school_system/urls.py:8-10` (`site_header` PKFSC / `site_title` PKFSC Admin / `index_title`), template brand + login override · ✅ README-এ author credit `README.md` শেষে ("**Habib** … [GitHub Profile]") · ❌ committed source-এ **একটিমাত্র agent/tool নাম**: `students/migrations/0034_subjectmarksetting_is_active.py:1` → `# Generated by Arena Agent on 2026-09-08` (`grep -rn "Arena" students/ school_system/ --include=*.py/html/js` ⇒ শুধু এই একটি) | ছোট কাজ: এই comment-টি সম্পাদনা (operations নয় — সীমা §৪ মানতে হবে) + owner-সিদ্ধান্ত (credit থাকবে কি না, তথ্য কোথায়) |
| ১৯ | DB-03 permissions ও isolation | **Partial** | ✅ `permissions.py::_group_permission_map()` একক source + `setup_groups` delegate, `InstitutionAccess`, helpers `views.py:202-373` (১৪টি scoping helper), login-এ `sync_user_department_permissions` · tests: `test_institution_isolation.py` ২৪, `test_institution_write_isolation.py` ৪৪, `test_audit_log_scoping.py` ১১ (≈৭৯টি) · ⚠️ **SEC-FU-1 খোলা**: rate-limit/lockout counter `cache`-এ কিন্তু `settings.py`-এ **কোনো `CACHES` নেই** (grep = 0) ⇒ default LocMemCache, per-process, restart-এ হারায় · ⚠️ **SEC-FU-2 খোলা**: `permissions.py:137-157` শুধু Office/Exam/Accounts map করে, বাকি group (`Subjects`, `HR`, `Audit` + `Admission` alias) login-এ সরিয়ে দেয় | দুটো open item-ই owner-সিদ্ধান্ত/ছোট কাজ (shared cache backend, HR/Audit নীতি) |
| ২০ | DB-04 settings ও CI | **Complete (code) / Unverified (live)** | `settings.py`: fallback SECRET_KEY guard (DEBUG=False-এ `ImproperlyConfigured`), `ALLOWED_HOSTS` wildcard → `students.E016`, `EXAM_ABSENT_SUBJECT_FAILS` `:346`, `MAILERS_BACKEND` env (`Django 6 mail.E001` fix) · CI `.github/workflows/tests.yml`: matrix sqlite + `postgres:16`, ৩টি deploy-guard ধাপ (fallback key fail · wildcard host fail via `students.E016` · production-shaped config pass), Node job, backup smoke (sqlite+postgres), moto S3 · tests `test_security_settings.py` (৫), `test_rate_limiting.py` (৭), `test_upload_security.py` (১০) · ⚠️ live env/HSTS নীতি owner-নির্ভর | code ✅; owner-সিদ্ধান্ত ২টি (§৭ DB-04: HSTS/SSL-redirect, DEBUG=False-এ secure cookies) — এগুলোই `check --deploy`-এর ৬ warning-এর কারণ (intentional) |
| ২১ | DB-05 backup tooling | **Complete (tooling) / Unverified (live)** | commands `backup_data`, `restore_backup`, `check_backups`, `fetch_backup`, `copy_media_to_storage`; scripts `scripts/backup.sh`, `restore.sh`, `backup_cron.sh` (healthcheck ping), `backup_smoke_test.sh` (`--postgres`, `--s3-endpoint`), `render.cron.yaml`; manifest+SHA, openssl/age encryption, optional S3 off-box copy, retention gate · tests `test_backup_tooling.py` (২৬ class / ১১২ test) · **এই সেশনে হাতে চালানো drill**: sqlite ১৫/০ pass, moto-S3 off-box ২৮/০ pass | tooling ✅; live cron/off-box/alert = owner (P0-8-live) + সিদ্ধান্ত ৩টি (§৭ DB-05) |
| ২২ | DB-06 restore drill ও automation | **Complete (drill locally proven) / Unverified (live cron)** | `restore_backup --yes --verify` (`--verify` → SHA match, `migrate --check`, record counts, media refs — drill আউটপুটে দেখা গেছে: "SHA-256 verified", "migrate --check OK", "Media references OK", wrong-passphrase reject) · `scripts/backup_smoke_test.sh` এই checkout-এ **নিজে চালানো** (§২) · CI-তে দুই matrix + moto · `.restore-drill/` gitignored (cleanup-এর পর `git status` clean) | drill ✅ প্রমাণিত; Render cron আসলে চলছে কি না + RPO/RTO/alert = owner-সিদ্ধান্ত (§৭ DB-06) |

### Attendance / Employee (AT-01…EM-03) ও সমাপনী (FN-01)

| # | সেশন | Verdict | প্রমাণ | দরকার কি না |
|---|---|---|---|---|
| ২৩ | AT-01 entry/correction | **Partial** | entry ✅: `mark_attendance:1265`, `mark_attendance_bulk:1286` (student/employee, `update_or_create` ⇒ **একই দিন আবার mark করলে overwrite হয়**, form GET-এ আগের মান pre-fill `:1330-1333`), audit: `record_audit(..., 'attendance_marked', …, {'count','date'})` — শুধু aggregate · model `AttendanceRecord:908-943` (`P/A/L/H`, unique per institution+student/date & employee/date; **`updated_by`/`updated_at` নেই**) · ❌ per-record correction পেজ/diff-তথ্য নেই, correction window/future-date বারণ নেই (`datetime.fromisoformat` যেকোনো তারিখ নেয়) | entry ✅; correction workflow = আসল বাকি কাজ + owner-সিদ্ধান্ত ৩টি (§৭ AT-01) |
| ২৪ | AT-02 calendar/report accuracy | **Missing (calendar)** | ✅ `attendance_report:1242` (100/পেজ), `attendance_summary:1400` (date-range + rate) · ❌ **calendar view/template নেই** (`grep -rin calendar` ⇒ শুধু nav icon `base.html:211`), কোনো central holiday model নেই (`'H'` শুধু প্রতি-রেকর্ড status `models.py:913`), রেকর্ড না থাকলে absent ধরা হয় না (rate `attendance_summary:1439+` শুধু রেকর্ড-ভিত্তিক) | calendar view = নতুন উন্নয়ন + owner-সিদ্ধান্ত ৩টি (§৭ AT-02: rate-এর সূত্র, holiday, monthly column) |
| ২৫ | EM-01 teacher assignment | **Missing** | Employee layer আছে: `Employee:873`, `EmployeeStatusLog:893`, `employee_list:1490` (100/পেজ), `employee_detail:1517`, `change_employee_status:4443`, `employee_status_history:4471` · ❌ **শিক্ষক↔শ্রেণি/বিভাগ/বিষয় assignment নেই** — `grep "TeacherAssignment|assignment" students/models.py` = ০; signature sheet শুধু seat-plan থেকে | নতুন মডেল + UI + test লাগবে + owner-সিদ্ধান্ত ৩টি (§৭ EM-01) |
| ২৬ | EM-02 leave | **Missing · ⛔ owner-policy ছাড়া কোড নয়** | `Employee.status`-এ `ON_LEAVE` আছে → `EmployeeStatusLog` ইতিহাস; ❌ **leave request/approval/balance মডেল নেই** (`grep "Leave\|LeaveRequest" students/models.py` = ০ — শুধু help_text-এ শব্দ) · attendance status `L` = **Late** (ছুটি নয়), `H` = Holiday; payroll deduction-এর কোনো নীতি নেই (`SalarySheet:983` — শুধু amount/status) | ⚠️ prompt-এর নিজের শর্ত: **owner-এর লিখিত নিয়ম ছাড়া কোনো মডেল/কোড নয়** → EM-02 শুরুর আগেই decision-request (`reports/EM-02-decision-request.md`) |
| ২৭ | EM-03 payroll controls | **Partial** | ✅ duplicate prevention: `SalarySheet` unique `(employee, month)` (`models.py:993`), money validation `MinValue(0)`/`MaxValue` (`test_money_validation.py` ৮ test), `finance_dashboard:4639` aggregate, `salary_sheet_list/add/edit/delete:4588-4637` (Accounts dept) · ❌ **closed-period/lock নেই** — PAID sheetও edit করা যায়, `SalarySheet`-এ status ছাড়া কোনো lock flag নেই (backlog H4) | closed-period control = আসল বাকি কাজ + owner-সিদ্ধান্ত ৩টি (§৭ EM-03) |
| ২৮ | FN-01 final release verification | **Unverified (শুরু হয়নি)** | নির্ভরতা: ০২–২৭; live-only অজানা-গুলো (`P0-7`, `P0-8-live`, `P1-11-live`, `P1-10-live`, D-8 DB engine) এই sandbox থেকে অসম্ভব — owner-এর Render করণীয় | ২৭টি শেষ হলে সামগ্রিক go/no-go + নির্দেশিকা |

---

## ৫. তিনটি পরিষ্কার তালিকা

### ৫.১ যাচাই করা — **ইতিমধ্যে সম্পন্ন** (শুধু regression যাচাই বাকি)

- **EX-04** Higher Math (curriculum + migration 0042 + seeds + টেস্ট)
- **EX-05** Missing marks policy (`EXAM_ABSENT_SUBJECT_FAILS=True`, AB display, TC বাদ)
- **EX-06** GPA 4.90–4.99 → 5.00 boost (implemented + টেস্ট; boundary = rounded 2-dp)
- **EX-07** Ctrl/Cmd+Click (result_sheet + full_rank_list; Node ৮ + Django ৩ test)
- **OF-01** একটি Guardian Contact (0039–0041, ৩৯ test)
- **OF-03** Subject Assignment Office subtab (nav + routes + ২৮ test)
- **OF-04** Admission reports/funnel (view + export + ২০ test)
- **DB-01** Dashboard scoping ও navigation (৫ test + code)
- **DB-04 / DB-05 / DB-06** — security settings + CI + backup tooling + **restore drill এই সেশনে হাতে চালিয়ে pass** (live অংশ বাদে)
- **EX-01-এর অর্ধেক** (import stay-on-page + regression test `tests.py:2915`)
- **OF-02-এর অর্ধেক** (৪টি high-volume view-এ `Paginator(...,100)`)

### ৫.২ আসলে **বাকি** (এই checkout-এ সত্যিই করতে হবে)

1. **EX-01** — Exam flyout-এ Analysis **subtab** বসানো (পেজগুলো আছে, subtab নেই)।
2. **EX-02** — বাকি output-গুলোর roll-order নিয়ম + নিয়ম ডকুমেন্ট (`exam_result_summary`, `class_section_summary`, attendance class-wise list, print CSS)।
3. **EX-03** — `SubjectMarkSetting`-এ **group** যোগ (নতুন append-only migration + UI + test)।
4. **OF-02** — ১১টি list view-এ pagination (money receipts, vouchers, salaries, audit log, admission list, exams, subject requirements, student exams, certificates, promotion history, accounts queue)।
5. **OF-05** — admission form-এ ছবি + student list-এ ছবি + purge-এ ফাইল মুছে ফেলা।
6. **OF-06** — public **status/progress** পেজ (+ হয়তো success পেজে share/copy)।
7. **OF-07 / OF-08** — integrity audit নিজে চালানো (কোড-ঘাটতি নয়, audit বাকি)।
8. **DB-02** — `0034`-এর comment থেকে agent নাম সরানো (comment-only, operations নয়)।
9. **DB-03** — SEC-FU-1 (shared cache backend) ও SEC-FU-2 (`HR`/`Subjects`/`Audit` group নীতি)।
10. **AT-01** — per-record correction (কেউ সংশোধন করলে তার প্রমাণ + সময়-সীমা)।
11. **AT-02** — server-rendered **calendar view** (নতুন JS লাইব্রেরি ছাড়া)।
12. **EM-01** — শিক্ষক↔শ্রেণি/বিভাগ/বিষয় assignment।
13. **EM-03** — closed-period / lock (PAID sheet edit আটকানো)।
14. **FN-01** — চূড়ান্ত release যাচাই (২৭টি শেষ হলে)।

### ৫.৩ **owner-সিদ্ধান্ত ছাড়া শুরু করা যাবে না**

- **EM-02 (leave)** — পুরো নীতি লিখিত না দিলে কোড নয় (type/paid/entitlement/approval/attendance/payroll) — ⛔।
- **EX-03** — parts-এর যোগ = full marks (exact) কি না; weekly test কোন exam type-এ; group config শুধু class ৯–১২ কি না।
- **EX-06** — 4.895 → 4.90 (boost) নাকি 4.89 — বর্তমান কোড boost করে, শুধু **নিশ্চিতকরণ**।
- **EX-07** — আর কোন পেজে shortcut, mobile আচরণ, permission set।
- **OF-02** — page size fixed ১০০ নাকি নির্বাচনযোগ্য।
- **OF-05** — admission form-এ ছবি, সর্বোচ্চ আকার, purge-এ ছবি মোছা।
- **OF-06** — progress page-এর যাচাই factor (application number + contact?) ও REJECTED-এ বার্তা।
- **OF-07 / OF-08** — capacity race, duplicate roll, fee mismatch block-vs-warn; TC থাকলে purge, certificate নম্বর পদ্ধতি, দুইবার promotion।
- **DB-02 / DB-03 / DB-04 / DB-05 / DB-06 / AT-01 / AT-02 / EM-01 / EM-03** — README §৭-এর নিজ নিজ সারি।
- **merge নীতি** — OPEN PR **#36 / #37** (সমান্তরাল সেশন, একই baseline scope) নিয়ে কোনটি রাখবেন।

---

## ৬. যাচাই হয়নি (Unverified) ও বাকি ঝুঁকি

| কী | কেন যাচাই হয়নি | ঝুঁকি |
|---|---|---|
| live Render env/config (P0-7), backup cron, off-box bucket, alerts (P0-8-live), S3 bucket (P1-11-live), production DB engine (P1-10-live/D-8) | এই sandbox-এ production credential/DB/Render access নেই (নিয়ম §৪) | backup আসলে চলছে কি না অজানা → production data-loss ঝুঁকি **খোলা** |
| postgres:16-এ suite | লোকালে Postgres service নেই; CU-তে matrix-এ আছে | SQLite ↔ Postgres পার্থক্য (conditional unique constraint) শুধু CI-তে প্রমাণিত — CI ফল PR-এ দেখা হবে |
| OF-07/OF-08-এর পূর্ণ audit | সেশনগুলো এখনো চালানো হয়নি (ক্রম অনুযায়ী পরে) | integrity-ঘাটতি (capacity race, duplicate roll) থাকতে পারে |
| AB-token-এর এক-রকমতা | result card/rank list-এ ভিন্ন শব্দ ("absent") | ছাপানো কাগজে শিক্ষক-অভিভাবক বিভ্রান্তি (কসমেটিক, data নয়) |
| `students/tests.py`-এর ৬২৫ সংখ্যা বনাম literal `def test` ৪৬৪ | inheritance/mixin ও loop-জেনারেটেড টেস্ট | কিছুই নয় — Django-র রিপোর্টই সত্য (625) |

**অন্য ঝুঁকি:** ২৮টি prompt-এর প্রেক্ষাপট `f64194a`-ভিত্তিক (base এখন `8b7aa62`) — কোনো সেশন
পুরোনো দাবির উপর নির্ভর করলে ভুল করতে পারে; এই matrix-ই সেই সংশোধক। এছাড়া PR #36/#37
খোলা থাকায় ডক-ফাইলে দ্বৈত সম্পাদনা → merge conflict।

---

## ৭. owner-প্রশ্ন (এই সেশন আটকায়নি; শুধু তালিকা)

1. **OPEN PR #36 ও #37** (দুটোই "প্রম্পট ০১" স্কোপ, ভিন্ন branch) — কোনটি merge করবেন?
   সুপারিশ: **একটি** রাখুন; এই PR (#38, `arena/01a0b9da-…`) স্বতন্ত্রভাবে যাচাই করা (উপরের
   কমান্ড-ফল সহ) — একাধিক merge করলে ডকে পরস্পরবিরোধী verdict থেকে যাবে।
2. **EM-02 leave নীতি** — লেখিত নীতি ছাড়া কেবল এই একটি সেশনই সত্যিকারের ব্লকড;
   `reports/EM-02-decision-request.md` সেই সেশনের নির্দেশিত output (prompt ২৬)।
3. **DB-04-এর secure-cookie/HSTS সিদ্ধান্ত** — এটিই `check --deploy`-এর ৬টি warning-এর
   মূল কারণ; DEBUG=True dev-এ এগুলো প্রত্যাশিত, live-এ চাই কি না সিদ্ধান্ত দিলে DB-04-এর
   বাকি অংশ (live) যাচাই করা যাবে।

---

## ৮. সিদ্ধান্ত ও নিয়ম যা এই সেশন মানল

- কোনো feature code, migration বা live কাজ **নেই** — শুধু যাচাই + ডক (prompt §২)।
- কোনো migration ফাইল edit/নতুন migration নেই; `makemigrations --check` clean (leaf 0043)।
- SSC Registration/BoardResult পুনরুদ্ধার করা হয়নি; `RetiredBoardFeatureTests` pass।
- কোনো production DB/credential/Render/S3 আসল bucket ছোঁয়া হয়নি; `.env`/`db.sqlite3`/`media/`/
  `backups/`/`.restore-drill/` — কিছুই commit হয়নি (drill নিজে পরিষ্কার করে, `git status` clean)।
- `main`-এ push/merge নেই; অন্য branch-এ যাওয়া নেই; force-push/`reset --hard`/`git clean` নেই।
