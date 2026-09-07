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
