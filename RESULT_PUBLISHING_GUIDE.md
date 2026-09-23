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
(`Office → Subject Assignments`), keyed by Institution + Class + Group.

- A subject with a blank group (Bangla, English…) counts for every group.
- A subject assigned to `SCI` never appears in a `BUS` exam, and vice versa.
- There is **no Subjects master page** any more. A brand-new subject is created
  on the *Assign Subject* form itself: leave the Subject dropdown empty and fill
  in the code, name, full marks and category that appear below it. The code and
  the name must both be unique across the whole system.
- **Optional** subjects need one more step: each student's choice has to be
  recorded (`Office → Students → Edit student`). Mandatory subjects and each
  student's own religion paper are derived automatically and need no choice row.

**No fallback:** a class with no assignment rows offers **no subjects at all** —
marks entry, the Excel import and the result sheet all refuse to guess, and each
page now says *why* the list is empty (nothing assigned / switched off in Mark
Evaluation / no student takes it) with a link to the screen that fixes it. There
is deliberately no fallback to the whole Subject master list, because that is
how one group's subjects used to leak into another group's exam.

**A subject assigned today joins an already-published exam only once someone
has a mark for it.** Assignments are read when a result is calculated, not
stored on the exam — but a subject the exam holds no mark for at all is *not*
a result column (see the pass rules), so merely assigning a subject can never
rewrite an old result: the sheet names it in a notice instead. The moment the
first mark is entered, the subject becomes a column on that exam's sheets, and
from then on a student without a mark in it is graded F. The Subject
Assignments list, the Assign Subject form and Mark Evaluation all list the
published exams this would touch *before* you save. An **Optional** subject
only counts for the students who actually chose it.

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

**A subject with no mark entered *for that student* fails them** (the NCTB/SSC
reading): the result sheet prints **AB** (Absent), never a 0, but the subject is
graded **F** and counted as 0 out of its Full Marks, so the student's result
becomes **Fail with GPA 0.00**. Not sitting a paper is not the same as scoring
nothing on it — the AB keeps that visible on paper — but it is not an exemption
either. This applies as soon as the subject holds a mark for *anyone* in the
exam: 40 marks entered and one box empty means that one student did not sit it.

**One token everywhere (D-MIS, decision 2026-09-17).** Every surface that
prints subject cells uses the same tokens — the same data never wears two
faces, and no view recomputes a result on its own (they all read the one
`build_exam_results` source):

| Cell content | Token on the page | Counted in total/GPA? |
|---|---|---|
| Assigned subject, nothing entered for this student | **AB** (+ grade **F** badge) | Yes — 0 out of Full Marks, result becomes Fail |
| Same blank, with `EXAM_ABSENT_SUBJECT_FAILS=False` | **AB** (grade shows `–`) | No — left out of the total and the GPA |
| A real entered 0 | **0** | Yes — a genuine zero, fails like any 0 |
| Optional subject this student did not select | *(blank cell)* | No |
| Religion paper not assigned for this student | *(blank cell)* | No |
| Subject with no marks for *anyone* in the exam | no column at all — named in the notice | No |

`AB` is what the register (Result Sheet), the student Result Detail, the Result
Card print, and Result Analysis (Subject Fail, class Result Cards) all print.
The ranking outputs (Result Summary, Top 10, Full Rank List, merit slides,
multi-term) print no subject cells — they show the same status/GPA and a
"(N absent)" count. A student with *no* marks anywhere prints `No Marks`, is
left unranked, and TC/DISCONTINUED students are not in the register at all.

**A subject the exam holds no mark for at all is not a column.** It is left out
of the register, the totals and the GPA entirely, and the result sheet names it
in a notice instead. Two reasons this matters:

- Assignments are keyed to the *class*, not to the exam, and are read when a
  result is calculated. Without this rule, a subject assigned to the class
  **after** an exam was published arrived as a brand-new empty column and failed
  every student in it — a published Pass 5.00 became Fail 0.00 just because
  someone added a subject. The column appears as soon as the first mark is
  entered.
- It is also how an un-entered subject shows up: if a paper *was* examined and
  nobody's marks are in yet, the register will be missing that column rather
  than failing the whole class. **Read the notice** — it is the difference
  between "not examined" and "not entered yet".

To go back to leaving un-entered subjects out of the total for individual
students as well, set `EXAM_ABSENT_SUBJECT_FAILS=False` in the environment;
nothing else about the AB/zero distinction changes.

The one exception is a student with **no marks in any subject**: they are listed as
`No Marks`, left unranked and not counted as Fail — nobody sat the exam, nobody
should get a fabricated GPA 0.00 in the position list.

### Final GPA and the fourth subject (D-GPA)

**Owner-corrected policy, 2026-09-23:** the old automatic **4.90–4.99 → 5.00**
benefit does **not** apply. A student is graded on their main subjects, with at
most one selected **fourth subject** giving a bonus. A fourth subject is a
selected paper whose Subject category is **FOURTH** (for example *Agriculture
Studies (4th Subject)*); an ordinary `OPTIONAL` subject remains a main subject.

For **N main subjects**, the calculation is:

```
final GPA = min(5.00, (sum(main subject GPA points) + max(0, fourth point - 2.00)) / N)
```

The fourth paper is **not** an extra denominator: 10 main papers plus
Agriculture are still graded over 10 main papers, never 11. Decimal
`ROUND_HALF_UP` makes the final two-place display deterministic, and the final
GPA is always capped at **5.00** — no result can display 5.10 or 5.20.

| Main point sum / N | Fourth-subject point | Calculation | Published GPA / grade |
|---|---:|---|---|
| 49 / 10 | none | 49 / 10 | 4.90 |
| 49 / 10 | F = 0.00 | (49 + 0) / 10 | 4.90 — Pass if all main papers pass |
| 48 / 10 | A+ = 5.00 | (48 + 3) / 10 = 5.10 | **5.00 / A+** |
| 50 / 10 | A+ = 5.00 | (50 + 3) / 10 = 5.30 | **5.00 / A+** |

A fourth-subject **F** (including an AB under the default absent policy) earns
zero bonus but **does not make the main result Fail**. A failed or absent **main
subject** still makes the whole result Fail with GPA 0.00. Result totals,
percentage, main GPA denominator, and the total-mark rank tie-break all use
only the main subjects; the fourth paper remains visible on the sheet/card with
its own mark and grade. When its bonus brings final GPA to 5.00, the published
overall grade is A+.

A school can offer several FOURTH papers so pupils can choose, but each student
may select **at most one**. Publishing is blocked with the named student and
subject list if a pupil has two or more fourth-subject choices; correct the
student's subject choices before publishing. There is no separate GPA/result
Excel-export route at present; browser print / Save as PDF uses these same
rendered result pages.

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
  A blank is stored as "nothing entered" and prints **AB** (Absent) on the result,
  while a 0 is a real mark of zero. Both fail the subject (see the pass rules), but
  only the 0 claims the student sat the paper and scored nothing — keep the record
  truthful.
- Boxes are per configured part (CQ / MCQ / Practical / Weekly Test) and the
  total is added up for you. Re-saving a row overwrites it; nothing is appended.
- Invalid entries are reported per student and skipped, the rest still saves.

### Import from Excel instead

`Exam List → Import Marks` → pick **one subject** → **Download current list**.
The file is built from the **live Student List** for that exam’s class/section/group
(sheet title like `9SC Physics`). If students join or leave, download again — do
not reuse last term’s sheet. Old IDs that are no longer on the roll are skipped
on import. Columns match how teachers already fill marks:

`Roll | ID | Name | CQ | MCQ | PT` (and `WT` when a weekly test is configured).
A subject with no parts has a single `Marks` column instead.

The Physics teacher fills Physics; the Bangla teacher fills Bangla. Do not put
other subjects on the same sheet.

- Identify students by the **ID** column (roll is a fallback).
- Leave a cell blank when the student did not sit that paper — blank is skipped,
  while 0 is a real mark of zero.
- A mark above that part's maximum, an unknown or out-of-scope student, or a
  duplicate row **rejects the whole upload** — nothing is partially imported.

Import writes the part fields (CQ / MCQ / Practical / Weekly Test) and the total,
so *Each part must pass* still works. An older three-column file (`Student ID,
Subject Code, Marks`) is still accepted for the selected subject, but it only
stores a total.

## 5. Check before publishing

Read them in this order:

1. **Result Sheet** (`Exam List → Result Sheet`) — the grid: **AB** for absent,
   `*` and red for a failed subject, hover any cell for the part breakdown and the
   pass mark. A yellow notice at the top lists marks held in **subjects that are
   not assigned to this exam** (they are deliberately excluded from the numbers —
   fix the assignments or the marks, then re-check).
2. **Result Summary** — Pass/Fail counts, totals, positions, and per-student
   detail links.
3. **Top 10** — ranking sanity check: ties share a position, and a student whose
   marks sit only in unassigned subjects must not be ranked.
4. **One result card** — print preview, because that is what parents see.

A student with no entered marks at all shows `No Marks` and is left unranked. A
student who sat some subjects but not others shows `Fail` with the missed subjects as
**AB** — read those before publishing, because a box left empty by mistake costs
a student their whole result.

## 6. Publish

`Exam List → Publish`. Publishing only gates the result pages (sheet, summary,
Top 10, detail, card) — an unpublished exam redirects those visitors to the exam
list, and the result card carries a *DRAFT* banner if printed anyway.

**Only an administrator can delete an exam** (the Exam department cannot). Use
that for a mistaken exam, not for routine corrections. Marks behind a published
exam are **locked** — see the next section for how a correction is made.

## 7. Correcting a published result

Publishing is what makes the sheet official, so the marks behind it are locked
from that moment: `Enter Marks` and `Import Marks` refuse to save anything for a
published exam and say so on the page.

To make a correction:

1. Open `Enter Marks` (or `Import Marks`) for that exam and press
   **Unlock to edit published result**.
2. Save the corrected marks — the register, summary, ranking and result cards
   all follow straight away.
3. Re-check the result sheet and **reprint** anything already issued: a corrected
   mark can change a GPA, a position and a Pass/Fail.

Both the unlock and every write made while unlocked are written to the audit
log, and so is every write the lock refused. The unlock lasts for your login
session on that exam; unpublishing clears it, so re-publishing starts locked
again. Set `EXAM_LOCK_PUBLISHED=False` to switch the lock off entirely — not
recommended, because it removes the only warning between a typo and a result
that has already gone home with a student.

### Getting to the right subject quickly (Ctrl/Cmd + Click)

While reading a published result, hold **Ctrl** (Windows/Linux) or **Cmd**
(macOS) and click a subject cell on the **Result Sheet** — that subject's
`Enter Marks` page opens **in a new tab**, on the same exam and the same group,
so the register you were reading stays open. The **Full Rank List** has no
subject columns, so there the same Ctrl/Cmd + Click opens that exam's marks
entry chooser instead.

A **plain click does nothing** on purpose: these pages are printed straight from
the browser, so nothing in the cell can navigate away or show up on the printout.
The Religion column opens the paper *that student* sits, never the column. If
your account cannot enter marks, the shortcut is switched off and the cell's
tooltip says *Ask Exam dept*.

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
