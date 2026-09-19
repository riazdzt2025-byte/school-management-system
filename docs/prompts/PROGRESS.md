# PROGRESS — প্রম্পট প্ল্যান (২৮ সেশন)

> **নতুন সেশনে শুরু করছেন?** `docs/prompts/HANDOFF-START.md` পড়ুন (মাত্র ২টি জিনিস পাঠাতে হয়)।
> **এখনকার অবস্থা:** কোনো প্রম্পট এখনো ✅ নয় → **প্রথম কাজ প্রম্পট ০১** = `docs/prompts/prompt-01-session-00-baseline.md`
> (START-ব্লক: `docs/prompts/copy-paste/kickoff/prompt-01-START.txt`)।
> প্রতি সেশনের এজেন্ট কাজ শেষে **নিজের সারি** আপডেট করবে — তাই "কত নম্বর চলছে / শেষ" এখানেই দেখা যাবে।

_এই ফাইলটিই একমাত্র সত্য: **কত নম্বরের প্রম্পট চলছে, কোনটি শেষ হয়েছে**। প্রতি সেশনের এজেন্ট নিজের সারি আপডেট করবে।_

**স্ট্যাটাস মানে:**
`⏳ অপেক্ষমাণ` — এখনো শুরু হয়নি · `🔄 চলছে` — এই মুহূর্তে চলছে · `✅ সম্পন্ন` — কোড+টেস্ট+ডক সব যাচাই হয়েছে · `🟡 আংশিক` — কিছু হয়েছে, কিছু বাকি · `⛔ ব্লকড` — owner সিদ্ধান্ত/অন্য কিছুতে আটকে আছে · `⏭️ বাদ (প্রযোজ্য নয়)` — যাচাই করে দেখা গেছে ইতিমধ্যে সম্পন্ন, কাজ লাগেনি।

**ক্রম:** ০১ (সেশন ০০ যাচাই) → EX-01…EX-07 → OF-01…OF-08 → DB-01…DB-06 → AT-01…AT-02 → EM-01…EM-03 → FN-01। ক্রম ভাঙা যাবে না; প্রতিটি প্রম্পট নিজের যাচাই প্রথমে করবে।

| # | সেশন | বিভাগ | ধরন | শিরোনাম | নির্ভরতা | স্ট্যাটাস | তারিখ | Commit / PR | টেস্ট প্রমাণ | নোট |
|---|------|-------|------|---------|----------|-----------|-------|-------------|---------------|------|
| ০১ | ০০ | প্রাথমিক | যাচাই | সর্বশেষ checkout থেকে বাকি কাজ নির্ধারণ (baseline) | — | ✅ সম্পন্ন | 2026-09-19 | ec6604b+baseline (PR #35 OPEN) | 625 Django + 14 Node, check 0, makemigrations clean | যাচাই করা: 625+14 pass, baseline রিপোর্ট `reports/০০-baseline.md` এ 28-session verdict (Complete 17, Partial 7, Missing 3, Unverified 1) — পরের প্রম্পট শুধু regression যাচাই করবে (প্রমাণ সহ) |
| ০২ | EX-01 | Exam | সংশোধন | Import redirect ও Analysis subtab | প্রম্পট ০১ (baseline) | ⏳ অপেক্ষমাণ · baseline: Partial (import redirect ✅, Analysis subtab 🔶) | — | — | baseline verified: import stay-on-page ✅ (`tests.py:2915`, `views:3707`), Exam flyout-এ Analysis নেই | যাচাই করা: import redirect ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে; Analysis subtab Exam-এ যোগ করতে হবে |
| ০৩ | EX-02 | Exam | সংশোধন | Result/Register roll-order | প্রম্পট ০২ (EX-01) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | numeric roll order সব register-এ (`result_utils:52,952`, `views.result_sheet:4090`, `views.student_list:1610`) | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ০৪ | EX-03 | Exam | উন্নয়ন | Group-based Mark Evaluation | প্রম্পট ০৩ (EX-02) | ⏳ অপেক্ষমাণ · baseline: ⛔ Missing (`group` field নেই) | — | — | `SubjectMarkSetting` has no `group`, only `institution,class,subject,exam_type` (`models:779-809`) | group field + migration লাগবে |
| ০৫ | EX-04 | Exam | যাচাই + উন্নয়ন | নতুন subject / Higher Math workflow | প্রম্পট ০৪ (EX-03) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | curriculum `auto_populate` + `quick_type` + HMATH `0042`, tests `test_new_subject*` 47k | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ০৬ | EX-05 | Exam | নিয়ম সংশোধন (policy) | Missing marks → Absent/Fail | প্রম্পট ০৫ (EX-04) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | `EXAM_ABSENT_SUBJECT_FAILS=True` (`settings:346`, `result_utils:547`) + TC exclusion | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ০৭ | EX-06 | Exam | নতুন নিয়ম | GPA 4.90–5.00 → 5.00 | প্রম্পট ০৬ (EX-05) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | `result_utils:928` `4.90 <= gpa <5.00 → 5.00` | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ০৮ | EX-07 | Exam | নতুন সুবিধা | Ctrl/Cmd+Click correction | প্রম্পট ০৭ (EX-06) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | `result_cell_shortcut.js` + `result_sheet:422/474` + `full_rank:158`, 8 Node tests | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ০৯ | OF-01 | Office | সংশোধন | একটি Guardian Contact | প্রম্পট ০৮ (EX-07) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | `guardian_contact_no` required + `0039-0042`, `test_guardian_contact.py` | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ১০ | OF-02 | Office | সংশোধন | সর্বোচ্চ ১০০-র pagination | প্রম্পট ০৯ (OF-01) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | 100/page: `student_list:1631`, `archived:2228`, `employee:1501`, `attendance:1250` | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ১১ | OF-03 | Office | সংশোধন | Subject Assignment Office subtab | প্রম্পট ১০ (OF-02) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | Office flyout `subject_requirement_list` (`base:199`) + `mark_evaluation_settings` | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ১২ | OF-04 | Office | উন্নয়ন | Admission reports | প্রম্পট ১১ (OF-03) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | funnel `admission_funnel_report:1146` + export, PR #32+#33 merged, 20 tests | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ১৩ | OF-05 | Office | যাচাই + উন্নয়ন | Student photos | প্রম্পট ১২ (OF-04) | ⏳ অপেক্ষমাণ · baseline: 🟡 Partial (photo ✅, continuity 🔶) | — | — | `Student.photo` exists + S3 tooling ✅; `AdmissionApplication.photo` missing → continuity gaps | photo continuity + live S3 বাকি |
| ১৪ | OF-06 | Office | উন্নয়ন | Public success page ও progress | প্রম্পট ১৩ (OF-05) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | `public_admission_success.html` + `next_step` + rate limit | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ১৫ | OF-07 | Office | যাচাই | Admission/import integrity | প্রম্পট ১৪ (OF-06) | ⏳ অপেক্ষমাণ · baseline: 🟡 Partial (core ✅, edge hardening 🔶) | — | — | scoping + `SectionCapacity` + validation ✅; duplicate fingerprint polish remain | edge-case hardening বাকি |
| ১৬ | OF-08 | Office | যাচাই | Archive/promotion/certificates | প্রম্পট ১৫ (OF-07) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | archive/restore/purge + promotion rollback + TC/cert/ID | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ১৭ | DB-01 | Dashboard | যাচাই + উন্নয়ন | Dashboard/navigation | প্রম্পট ১৬ (OF-08) | ⏳ অপেক্ষমাণ · baseline: 🟡 Partial (core ✅, polish 🔶) | — | — | 5 flyouts +  permission gates ✅; minor nav polish remain | nav polish বাকি |
| ১৮ | DB-02 | মূল ব্যবস্থা | সংশোধন | Developer branding | প্রম্পট ১৭ (DB-01) | ⏳ অপেক্ষমাণ · baseline: 🟡 Partial (core ✅, polish 🔶) | — | — | header/admin branding ✅; footer/print consistency polish remain | branding polish বাকি |
| ১৯ | DB-03 | মূল ব্যবস্থা | নিরাপত্তা | Permissions ও data isolation | প্রম্পট ১৮ (DB-02) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | `permissions.py` single source + 50+ isolation tests 625 pass | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ২০ | DB-04 | মূল ব্যবস্থা | নিরাপত্তা | Settings ও CI | প্রম্পট ১৯ (DB-03) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | settings guards + `tests.yml` sqlite+postgres+Node+deploy guards | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ২১ | DB-05 | মূল ব্যবস্থা | নতুন ব্যবস্থা | Backup tooling | প্রম্পট ২০ (DB-04) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | `backup_data`/`check`/`fetch` + 112 tests | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ২২ | DB-06 | মূল ব্যবস্থা | যাচাই | Restore drill ও automation | প্রম্পট ২১ (DB-05) | ⏳ অপেক্ষমাণ · baseline: 🟡 Partial (drill ✅, live 🔶) | — | — | local `backup_smoke_test` ✅; live cron/bucket/alert Unverified | live automation বাকি (owner-only) |
| ২৩ | AT-01 | Attendance | যাচাই + উন্নয়ন | Entry/correction | প্রম্পট ২২ (DB-06) | ⏳ অপেক্ষমাণ · baseline: ✅ Complete | — | — | `mark_attendance` + `mark_attendance_bulk` + unique per day | যাচাই করা: ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে |
| ২৪ | AT-02 | Attendance | যাচাই + উন্নয়ন | Calendar/report accuracy | প্রম্পট ২৩ (AT-01) | ⏳ অপেক্ষমাণ · baseline: 🟡 Partial (report ✅, calendar 🔶) | — | — | `attendance_report` + `attendance_summary` ✅; calendar grid Missing | calendar view বাকি |
| ২৫ | EM-01 | Employee | যাচাই + উন্নয়ন | Employee/teacher assignment | প্রম্পট ২৪ (AT-02) | ⏳ অপেক্ষমাণ · baseline: 🟡 Partial (employee ✅, teacher link 🔶) | — | — | `Employee` CRUD ✅; `TeacherAssignment` model Missing | teacher assignment বাকি |
| ২৬ | EM-02 | Employee | শর্তসাপেক্ষ (owner decision) | Leave | প্রম্পট ২৫ (EM-01) | ⏳ অপেক্ষমাণ · baseline: ⛔ Missing (owner decision ⛔) | — | — | no `Leave` model | owner policy সিদ্ধান্ত needed before build |
| ২৭ | EM-03 | Employee | যাচাই + উন্নয়ন | Payroll controls | প্রম্পট ২৬ (EM-02) | ⏳ অপেক্ষমাণ · baseline: 🟡 Partial (sheet ✅, lock 🔶) | — | — | `SalarySheet` unique month ✅; closed-period lock Missing | payroll lock বাকি |
| ২৮ | FN-01 | সমাপনী | যাচাই | পুরো release পরীক্ষা ও নির্দেশিকা | প্রম্পট ০১–২৭ (সব) | ⏳ অপেক্ষমাণ · baseline: ⛔ Blocked (01-27 pending) | — | — | awaits all prior | last verification |

## নিয়ম (এজেন্টদের জন্য)

1. নিজের প্রম্পটের সারি ছাড়া অন্য সারির স্ট্যাটাস বদলাবে না (owner ছাড়া)। শুধু প্রম্পট ০১-এ পুরো ledger-এর initial verdict বসানো যাবে।
2. সেশন শেষে অবশ্যই: স্ট্যাটাস + তারিখ (UTC) + commit sha + PR নম্বর ও state + টেস্ট সংখ্যা (Django/Node) + `check` / `makemigrations --check` ফল।
3. স্ট্যাটাস `✅` তখনই যখন ফোকাসড টেস্ট + পূর্ণ suite + `check` + `makemigrations --check` সব pass এবং সংশ্লিষ্ট ডক হালনাগাদ।
4. `⛔ ব্লকড` হলে কারণ + owner-প্রশ্ন এক লাইনে, এবং `docs/prompts/reports/<সেশন>.md`-এ বিস্তারিত।
5. CI fail হলে স্ট্যাটাস `🟡 আংশিক`, কারণ ও log-এর সারাংশ নোটে।
