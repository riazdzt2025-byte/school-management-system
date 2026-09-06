# Result Publishing Guide

How to take an exam from "nothing marked" to "results published", and what each
setting actually changes. Everything below matches the current code; if a screen
looks different, the deploy is behind — see [`DEPLOY_NOTES.md`](DEPLOY_NOTES.md).

Short version:

> Subject assignments → Mark Evaluation Settings → create the exam (with a
> group) → enter or import marks → read the result sheet → publish.

---

## 0. Once per class: subject assignments

Marks entry and the result sheet both work off **Subject Assignments**
(`Subject → Subject Assignments`), keyed by Institution + Class + Group.

- A subject with a blank group (Bangla, English…) counts for every group.
- A subject assigned to `SCI` never appears in a `BUS` exam, and vice versa.

**Fallback:** if a class has no assignments at all, every subject is offered and
the pages say so. Marks entry is never blocked, but the result sheet then cannot
tell one group's subjects from another's — configure assignments for classes
9–12 before publishing anything.

## 1. Mark Evaluation Settings (`Exam → Mark Evaluation`)

Pick Institution + Class + Exam Type, then per subject:

| Column | Meaning |
|---|---|
| Full Marks | What the subject is marked out of **for this exam type** |
| CQ / MCQ | Split of the written paper. Blank = no such part |
| Practical | Practical marks (e.g. Physics 75 + 25). Blank = no practical |
| Weekly Test | Only for exam types that carry one (Mid Term) |
| Pass % | Pass mark as a percentage of Full Marks; 40 is the SSC rule |
| Pass Marks | Read-only result of the above |
| Parts total | Green when the parts add up to Full Marks, **red when they do not** |
| Each part must pass | See the pass rules below |

Notes:

- Settings are per **exam type**: Second Term can be 100 marks with a practical,
  Mid Term 50 without one. With no setting row, the subject's own defaults apply.
- A part bigger than Full Marks is refused. A red "Parts total" is only a warning
  — but marks above a part total are rejected during entry, so fix it.
- Clearing a row's Full Marks leaves the subject alone entirely.

## 2. Pass rules

A subject passes when **both** hold, unless you tick *Each part must pass*:

1. total obtained ≥ Full Marks × Pass % ;
2. nothing is configured-but-missing.

With **Each part must pass** ticked, every configured part must reach its own pass
mark (`part max × Pass %`): with Physics 75 + 25 at 40%, a student needs 30 in
theory **and** 10 in practical. Failing any part makes the whole subject **F** with
0.00 points — the total does not save it, and the student's result becomes Fail with
GPA 0.00.

A part that is configured but left blank for a student **counts as a failed part**.
That is the difference between "student did not sit the practical" and "we forgot to
enter the practical": both are missing marks, and neither may be read as a pass.

## 3. Create the exam

`Exam → Add Exam`. Class, Section and Group are dropdowns; the exam **name is
generated** from exam type + session (e.g. *Second Term Examination-2026*), it is
not typed.

**Set the group** for classes 9–12. One exam per group is the clean model:
then marks entry, marks import, seat plan and the result sheet all show exactly
that group's students and subjects, and no group picker appears. An exam without a
group still works — every marks page then offers a group picker — but the exam
matches every group's subjects until you pick one.

## 4. Enter the marks

Two routes, same screens:

- `Exam List → Enter Marks` (subject picker for one exam), or
- `Exam → Enter Marks` (pick institution, class, group, exam type, session and
  subject — this creates the exam row if it does not exist yet).

Rules that matter:

- **Leave a box empty when the student did not sit that paper. Never type 0.**
  A blank is stored as "nothing entered" and prints a dash (—) on the result;
  a 0 is a real mark of zero, which fails the subject.
- Boxes are per configured part (CQ / MCQ / Practical / Weekly Test) and the
  total is added up for you. Re-saving a row overwrites it; nothing is appended.
- Invalid entries are reported per student and skipped, the rest still saves.

### Import from Excel instead

`Exam List → Import Marks` → **Download Excel template**. The workbook already has
one row per (student × subject assigned to this exam), plus *How to fill*,
*Subjects* (this exam's Full Marks, parts and pass marks) and *Students* sheets.
Fill the Marks column and upload it back:

- a row with a blank Marks cell is skipped, not rejected;
- an unknown student ID, a student outside the exam's class/section/group, an
  unknown or unassigned subject code, a duplicate row, or a mark above this exam's
  Full Marks **rejects the whole upload** — nothing is partially imported.

Import writes totals only. Where a subject has parts configured, the part columns
stay empty, so *Each part must pass* will fail those subjects; enter such subjects
on screen, or untick the rule for the imported exam type.

## 5. Check before publishing

Read them in this order:

1. **Result Sheet** (`Exam List → Result Sheet`) — the grid: dashes for absent,
   `*` and red for a failed subject, hover any cell for the part breakdown and the
   pass mark. A yellow notice at the top lists marks held in **subjects that are
   not assigned to this exam** (they are deliberately excluded from the numbers —
   fix the assignments or the marks, then re-check).
2. **Result Summary** — Pass/Fail counts, totals, positions, and per-student
   detail links.
3. **Top 10** — ranking sanity check: ties share a position, and a student whose
   marks sit only in unassigned subjects must not be ranked.
4. **One result card** — print preview, because that is what parents see.

A student with no entered marks at all shows `No Marks`, is left unranked, and does
not drag anyone else's average down.

## 6. Publish

`Exam List → Publish`. Publishing only gates the result pages (sheet, summary,
Top 10, detail, card) — an unpublished exam redirects those visitors to the exam
list, and the result card carries a *DRAFT* banner if printed anyway.

**Exam results are permanent: the delete route is disabled on purpose.** After
publishing you can still correct marks (they flow straight into the result), then
unpublish → re-check → republish while the correction is verified.

## 7. After a board result is published

`SSC Registration → Add Board Result` for the cohort, then
`Office → SSC Result Summary`. Board GPA is entered by hand — it is the board's
number, not the school's exam calculation, and nothing here overwrites it.

---

## Housekeeping that affects results

- **Duplicate subjects.** `Bangla 1st Paper` and `BANGLA FIRST PAPER` are two rows,
  so marks split between them and both can show up as a separate subject column.
  Back up, then run `python manage.py merge_duplicate_subjects` (dry run), check
  the KEEP/MERGE report, then `--apply`. See
  [`DEPLOY_NOTES.md`](DEPLOY_NOTES.md) for the exact steps.
- **Section on the exam.** Blank section = the whole class. Set it to publish one
  section at a time.
- **Zero-padded classes.** `9` and `09` are treated as the same class everywhere in
  the exam module; if a new screen ever filters on a raw string, that is a bug.
