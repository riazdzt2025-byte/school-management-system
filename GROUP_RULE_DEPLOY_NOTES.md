# Deploy notes — groups only from class 9 upwards

Merged to `main`. Render redeploys automatically from `main`.

## The problem this fixes

The Add Student and Admission screens offered a **Group** dropdown for every
class, so students in class 6, 7 and 8 ended up stored with "Science". Those
classes follow one common syllabus — there is no group at all — and a group on
them makes the student list, marks entry and result sheets filter on something
those classes never had.

`admission_dropdown_options` made it worse: when a class had no
`SubjectRequirement` rows configured yet it fell back to the **full** group
list, which is how Science showed up for class 6.

## The rule now, in one place

`students/models.py`:

```python
GROUPED_CLASS_LABELS = ['9', '10', '11', '12']
GENERAL_GROUP_CODES  = ('SCI', 'BUS', 'HUM')

Student.class_supports_group(admission_class)   # True from class 9 up
Student.group_choices_for_class(admission_class)  # Science / Business / Humanities
```

Everything else asks these instead of hard-coding `['9','10','11','12']`:

| Where | Behaviour |
| --- | --- |
| Add / Edit Student (`StudentForm`) | Group hidden and optional below class 9; required from class 9 with only the three choices. A submitted group on class 6-8 is dropped, not rejected. |
| `Student.save()` | Clears `group` whenever the class has none, so nothing re-enters the DB through any screen. |
| Admission application form + public apply form | Group starts hidden; the dropdown-options endpoint returns `groups: []` and `supports_group: false` below class 9. |
| Excel import | The Group column is ignored for classes below 9. |
| Bulk update | A group is applied only to students in a grouped class; moving students into class 6-8 clears their group. |
| Student list filter / marks picker | Same shared list drives the show/hide. |

Class labels are normalised, so `'09'` and `'9'` behave identically.

Diploma trades (`DCS`, `DEL`, `DCV`) and `General` / `Non-Group` stay in
`GROUP_CHOICES` for existing rows, but they are no longer offered by the
admission screens. Diploma institutions use semester labels ("1st Semester"),
which are not in `GROUPED_CLASS_LABELS` — tell me if one of them needs groups
and I will widen the rule.

## Existing wrong data

`migrations/0033_clear_groups_below_class_9.py` runs on deploy and clears the
group on every student whose class is below 9. It touches nothing else — class
9 Science stays Science.

To see what it will do without changing anything:

    python manage.py clean_student_groups

Then apply it (the migration already did this on deploy; the command is here
for a re-check or for a database that was restored afterwards):

    python manage.py clean_student_groups --apply

Both print a per-class report first.

## Verified

    python manage.py test students     # 85 tests, OK (18 new for this rule)

Checked against a running server as well:

- `GET /admission/dropdown-options/?admission_class=6` → `{"groups": [], "supports_group": false}`
- same for class 8; class 9 and 11 → Science, Business Studies, Humanities
- `POST /add/` with class 6 + `group=SCI` → saved with `group=''`
- `POST /add/` with class 9 + no group → "Group is required for classes 9, 10, 11, and 12."
- `POST /add/` with class 9 + `DCS` → "Select Science, Business Studies or Humanities."
- `clean_student_groups --apply` cleared 3 seeded class 6/7/8 rows, left class 9 alone

## After the deploy

1. Open **Students → Add Student**, pick class 6: the Group field is gone.
   Pick class 9: it comes back with Science / Business Studies / Humanities.
2. Open **Students** and filter by class 6: the Group filter stays hidden; by
   class 9 it appears.
3. Spot-check a class 6 student's profile — the Group column should be empty.

---

# Login screen: institution + department cards (second fix)

## The problem

`institution_login` built its cards from `InstitutionAccess`:

```python
cards = InstitutionAccess.objects.select_related('institution', 'user')...
```

With no `InstitutionAccess` rows — the state of a fresh install — the login
page rendered "No institution access has been assigned for this account yet",
the hidden `institution_id` field was empty, and the "choose your institution"
step meant nothing. Admins could still authenticate (the view accepts any
institution for superuser/staff) but with an empty institution in the session.

## What changed

- **Login page** now renders one card per `Institution`, each with Office /
  Exam / Accounts pills. The card picks the institution, the pill picks the
  department, and the hidden field is pre-filled with the first institution so
  it is never empty. The "no access assigned" warning is gone; it only shows a
  message now when no institution exists at all.
- **`grant_institution_access` command** — the piece a non-admin needs, since
  without an `InstitutionAccess` row their login is refused with a message that
  reads like a wrong password:

      python manage.py grant_institution_access                              # who can log in
      python manage.py grant_institution_access --list-users
      python manage.py grant_institution_access clerk --institution 1
      python manage.py grant_institution_access clerk --institution "Professor Kazi Faruky Kallan Trust" --department Office
      python manage.py grant_institution_access clerk --institution 1 --department Office --revoke

  It also runs `ensure_default_groups()` so the department's permissions exist
  and the user does not hit 403 after logging in. Idempotent; reviving an
  inactive row re-activates it.
- **Django admin**: `InstitutionAccess` got a proper `ModelAdmin`
  (list display, filters, search) so access can be managed from the browser
  after logging in as admin.

Login rules themselves are unchanged: superuser/staff may pick any
institution + department; everyone else needs an active `InstitutionAccess`
row for exactly what they picked.

## Verified

    python manage.py test students     # 91 tests, OK (6 new)

Against a running server on a database with **zero** `InstitutionAccess` rows:

- login page shows the institution with Office/Exam/Accounts pills and posts `institution_id=1`
- admin login → 302, `/students/` 200, `/admin/` 200
- plain user `clerk` → "Invalid username, password, or institution access."
- after `grant_institution_access clerk --institution 1 --department Office` → 302, `/students/` 200, `/admin/` 302 (correctly refused)
- after `--revoke` → refused again

---

# Archive (soft delete) audit and fixes

Audited the archive flow with a throwaway database and a running server. The
core of it was sound — `Delete` archives instead of deleting, `Restore` puts
the student back with the status they had, and the student list, dashboard,
marks scope, result sheets and attendance already ignored archived rows.

Six things were wrong. All six are fixed.

## 1. The department that archives could not read the archive (403)

`archived_students` is guarded by `students.view_student`, but no department
group was ever granted `view_student`. An Office user could archive a student
and then got **403** on the only page that lists what they archived:

    [p] Office user delete_student POST    http=302   ← can archive
    [p] Office user archived_students GET  http=403   ← cannot see it

`students/permissions.py` (and the `setup_groups` command, which mirrors it)
now grant `view_student` to Office, Admission, Exam and Accounts. It runs from
`post_migrate`, so the deploy applies it — no shell needed.

## 2. Promotion carried archived students into the next class

`student_promotion` filtered on `admission_class` only:

    [6] archived student now in class 7 | kept student now in class 7

A student who had left the school was promoted along with the batch. Now
filtered with `is_archived=False`.

## 3. Excel export included archived students

`download_student_list` queried `Student.objects.all()`, so the download and
the list on screen disagreed:

    row: ('AU101', 'ZZ Archived One', '6', 'A') | status = Discontinued

Now filtered.

## 4. Class/Section summary counted archived students

    row cells: ['6', 'A', '2', ...]   ← one active student, counted as 2

Now filtered.

## 5. Restore was guarded by the wrong permission

Archive needs `students.delete_student`; restore needed `students.both
change_student`. A user holding only `change_student` could undo an archive
they were never allowed to make. Both restore views now require
`delete_student`, so archiving and undoing it are granted together.

## 6. Archived records stayed editable

`GET /edit/<pk>/` on an archived student rendered the form (200). It now
redirects to the Archive page with "Restore the student before editing".

Also filtered: bulk update, bulk-update selection page, auto registration and
other active-student workflows — none of them should reach an archived row.

## Verified

    python manage.py test students     # 101 tests, OK (10 new in ArchiveIntegrityTests)

Against a running server, logged in as an Office-department user:

| step | result |
| --- | --- |
| archive a student | 302 |
| `/students/archived/` | **200** (was 403), student listed with a Restore button |
| student list | archived student gone |
| Excel export | only the 2 active students |
| class/section summary | `Total students: 2` (was 3) |
| promotion 6 → 7 | actives moved, archived stayed in class 6 |
| `GET /edit/<archived>` | 302 → `/students/archived/` |
| restore as Office user | 302, `is_archived=False`, `status=ACTIVE` |
| restore without `delete_student` | 403 (unit test, no department group) |

---

# Import: 133 rows in the sheet, 56 students on the site

## What was wrong

1. **Group labels matched by exact equality only.** The filled template says
   "Business"; the stored label is "Business Studies". Every Business row
   imported with a blank group, which the list renders as "—".
2. **`Student.save()` generated `student_id` as `count + 1`.** After a partial
   import the numbering has holes, and the next count-based id can land on a
   suffix that is already taken. The row then died with an IntegrityError and
   was skipped — which is how a 133-row sheet produced a fraction of the
   students.

## What changed

- `parse_group_label()` accepts codes (SCI/BUS/HUM), full labels and short
  forms ("Business", "Science", "Humanities", "Commerce", "Arts"). Unknown or
  blank still becomes ''.
- `Student.save()` steps over taken id suffixes instead of raising.
- The import is now **safe to re-run**: a row whose (institution, name, class,
  section, roll, year) already exists is skipped instead of duplicated, and if
  that existing student has a blank group while the sheet carries one, the
  group is filled in. The banner reports
  `N added, M already present (skipped), K existing student(s) got their group filled in.`
- Row errors now print the exception type and up to 30 rows instead of 10.

106 tests pass. Verified: a 133-row sheet mirroring the filled template
imports 133/133 (127 HUM + 6 BUS), a second upload adds 0 and skips 133.

## After the deploy

Re-upload the **same** filled Excel once. It will create the missing rows,
skip the ones already present, and backfill the Business group on the "—"
students. If any rows still error, the banner now names the row and the
reason — paste that text (or the file) and it can be fixed precisely.
