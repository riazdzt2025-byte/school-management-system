# Deploy notes — group-aware marks entry (PR #1)

Merged to `main` on 2026-09-06. Render redeploys automatically from `main`.

No new database migrations, so the deploy is a plain code update.

---

## 1. Verify the deploy

Open the live site and check the exam you were looking at:

    https://school-management-system-27mn.onrender.com/exams/2/select-subject/

You should now see:

- a **Group** dropdown above the subject list (because that exam has no group set)
- the subject list shrinking to that group's subjects when you pick one
- a line stating which class/group the list is filtered by

If the page looks unchanged, the deploy has not finished. Check the Render
dashboard → Events, and confirm the service builds from `main`.

## 2. Clean up duplicate subjects

The subject list contains near-duplicates such as `Bangla 1st Paper` /
`BANGLA FIRST PAPER` and `Bangla 2nd Paper` / `Bangla Second Paper`.

**Back up the database first.** In the Render dashboard open the service Shell
(or connect to Postgres) and run a dry run:

    python manage.py merge_duplicate_subjects

This changes nothing. Read the report:

- `KEEP` is the row that will survive (the one with the most references).
- `MERGE` rows will have their marks and assignments moved onto the keeper,
  then be deleted.
- Any line warning that **full marks differ** needs a human decision — fix the
  wrong row in the admin first, then re-run.

When the report looks right:

    python manage.py merge_duplicate_subjects --apply

Re-running afterwards should print `No duplicate subjects found.`

## 3. Set a group on existing exams

Exams created without a group match every group's subjects for that class. The
group picker handles this, but it is cleaner to set the group on the exam
itself: **Exam → Exam List → Edit → Group**. One exam per group.

Once an exam has a group, the picker disappears and marks entry, marks import
and the student list are all constrained to that group automatically.

---

## What changed in the code

| Area | Change |
|---|---|
| `select_marks_subject` | subject list filtered by class + group; group picker for exams with no group; POST validated |
| `enter_marks` | rejects subjects not assigned to the exam's class/group, including hand-edited URLs |
| `import_exam_marks` | rejects rows with an unassigned subject, and students whose group differs from the exam's; lists accepted subject codes on the page |
| `get_exam_subjects()` | shared helper reading `SubjectRequirement`; returns only the assigned subjects (no fallback — an unassigned class is empty, and the marks/result pages link to Subject Assignments) |
| Result sheet | Islam & Hindu religion papers print as one merged **Religion (REL)** column; headers show subject codes (BAN1, ENG1, REL…) with a "Subject codes" legend below the table |
| `students/apps.py` | default groups now sync on `post_migrate` instead of at import time, so a fresh database can migrate |
| `settings.py` | `CSRF_TRUSTED_ORIGINS` is now configurable via env var |
| `merge_duplicate_subjects` | new management command, dry run by default |

### Safety net

If a class has no `SubjectRequirement` rows configured, every subject is shown
(with a notice on the page) so marks entry is never blocked. Configure subject
assignments per class/group to get the filtered behaviour.
