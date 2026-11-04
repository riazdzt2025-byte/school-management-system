"""Excel and CSV downloads of the printed result sheets.

The office used to get a result out of the system in exactly one way: click
"Print / Save PDF" and pick *Save as PDF* in the browser dialog. That works,
but it hands the office a picture of a table — no sorting, no filtering, no
adding a column of its own — and it asks a clerk to find the right printer
dialog. Every sheet therefore also leaves the system as a **data** file:

* **Excel (.xlsx)** — the same sheet the paper prints (letterhead rows, the
  table, the closing totals), styled for reading, with the header row frozen
  and a filter so the office can sort by GPA or filter a fail list.
* **CSV** — the plain table only, so it opens in anything (a phone, Google
  Sheets, a legacy desktop tool) without needing Excel.

Three rules keep the download trustworthy:

1. **One source of truth.** The rows come from the same
   :func:`~students.result_utils.build_exam_results` computation the printed
   sheet renders, so a downloaded GPA can never disagree with the paper.
2. **No formula injection.** A name or comment that starts with ``=``, ``+``,
   ``-`` or ``@`` is prefixed with an apostrophe in CSV, so opening a file
   exported by a user cannot execute a spreadsheet formula.
3. **No surprise downloads.** Nothing here is reachable without signing in,
   and the exam must be in the caller's own institution.
"""
from __future__ import annotations

import csv
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from .result_utils import (
    build_exam_results,
    build_sheet_columns,
    grade_distribution_report,
    grade_scale_rows,
    result_summary_totals,
)

try:  # openpyxl is a declared requirement, but never fail a whole page over it
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover - exercised only when the wheel is missing
    openpyxl = None


XLSX_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
CSV_CONTENT_TYPE = 'text/csv; charset=utf-8'

#: Kind slug -> the sheet the office asked for, used for titles and filenames.
KINDS = {
    'sheet': 'Full Mark Sheet',
    'published': 'Published Result Sheet',
    'top10': 'Top Ten',
    'summary': 'Results Summary',
}

#: Leading characters a spreadsheet treats as the start of a formula.
_FORMULA_STARTERS = ('=', '+', '-', '@', '\t', '\r')


# --------------------------------------------------------------------------- #
# Cell helpers
# --------------------------------------------------------------------------- #
def safe_text(value):
    """A CSV/XLSX text cell that can never be read as a formula.

    Excel and LibreOffice execute a cell that begins with ``=``, ``+``, ``-`` or
    ``@``. A guardian can type any of those into a name, so every free-text
    cell is neutralised with a leading apostrophe (Excel's own "treat as text"
    marker) instead of being written straight from the database.
    """
    text = '' if value is None else str(value)
    if text[:1] in _FORMULA_STARTERS:
        return "'" + text
    return text


def number(value):
    """openpyxl writes numbers, never ``Decimal`` objects."""
    if value is None:
        return ''
    try:
        return float(value)
    except (TypeError, ValueError):
        return safe_text(value)


def _cell_value(value):
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (int, float)):
        return value
    if hasattr(value, 'as_tuple'):  # Decimal
        return float(value)
    return safe_text(value)


def _place(value):
    """Merit position as printed on the sheet: '' when unranked."""
    return value or ''


def _mark_cell(cell):
    """One subject cell of the register exactly as the paper prints it."""
    if cell.get('not_applicable') or cell.get('religion_unassigned'):
        return '-'
    if cell.get('absent'):
        return 'AB'
    return number(cell.get('obtained'))


# --------------------------------------------------------------------------- #
# Sheet specifications
# --------------------------------------------------------------------------- #
def register_order(results):
    """Register order: numeric roll, then name — the order the paper prints."""
    return sorted(results, key=lambda row: (
        row['student'].roll_no is None,
        row['student'].roll_no if row['student'].roll_no is not None else 0,
        row['student'].name.lower(),
        row['student'].pk,
    ))


def _sheet_spec(exam, columns, results, sheet_columns):
    """The Full Mark Sheet: one row per student, one column per paper."""
    headers = ['Roll No.', 'Student ID', 'Student Name']
    headers += [column['subject'].code for column in sheet_columns]
    headers += ['Total', 'Full Marks', 'GPA', 'Grade', 'Result',
                'A+', 'F', 'Place']
    rows = []
    for result in results:
        row = [
            _place(result['student'].roll_no),
            safe_text(result['student'].student_id),
            safe_text(result['student'].name),
        ]
        row += [_mark_cell(cell) for cell in result['subject_results']]
        row += [
            number(result['total_obtained']),
            number(result['total_full']),
            number(result['gpa']),
            safe_text(result['grade']),
            safe_text(result['status']),
            result['a_plus_count'],
            result['failed_subject_count'],
            _place(result['position']),
        ]
        rows.append(row)

    brief, _subject_wise = result_summary_totals(results, sheet_columns)
    notes = [
        ('Total Students', brief['total_students']),
        ('Passed', brief['pass_count']),
        ('Failed', brief['fail_count']),
        ('No Marks', brief['no_marks_count']),
        ('A+ Students', brief['a_plus_students']),
        ('Pass Rate', f"{brief['pass_rate']} %"),
        ('Total Subject A+', brief['total_subject_a_plus']),
    ]
    legend = [
        f"{column['subject'].code} = {column['subject'].name}"
        + (f" (Full Marks {column['full_marks']})" if column['full_marks'] else '')
        for column in sheet_columns
    ]
    widths = [8, 12, 28] + [10] * len(sheet_columns) + [9, 10, 8, 8, 9, 6, 6, 7]
    return {
        'title': 'Full Mark Sheet',
        'headers': headers,
        'rows': rows,
        'widths': widths,
        'notes': notes,
        'legend': legend,
    }


def _published_spec(exam, results):
    """The Published Result Sheet: the one-page summary the office hands out."""
    headers = ['Roll No.', 'ID No.', 'Student Name', 'Grade', 'GP', 'Total',
               'Place', 'A Plus', 'Fail', 'Comments']
    rows = []
    for result in results:
        rows.append([
            _place(result['student'].roll_no),
            safe_text(result['student'].student_id),
            safe_text(result['student'].name),
            safe_text(result['grade']),
            number(result['gpa']),
            number(result['total_obtained']),
            _place(result['position']),
            result['a_plus_count'],
            result['failed_subject_count'],
            safe_text(result.get('comment', '')),
        ])
    total = len(results)
    passed = sum(1 for row in results if row['status'] == 'Pass')
    notes = [
        ('Total Student', total),
        ('Total Pass', passed),
        ('Total Fail', total - passed),
        ('Total A Plus', sum(1 for row in results if (row.get('grade') or '') == 'A+')),
        ('Pass Rate', f'{int(100 * passed / total) if total else 0} %'),
    ]
    return {
        'title': 'Published Result Sheet',
        'headers': headers,
        'rows': rows,
        'widths': [9, 12, 30, 8, 8, 9, 7, 8, 6, 16],
        'notes': notes,
        'legend': [],
    }


def _top_ten_spec(exam, results):
    """Top Ten: merit order, with the Golden / Potential comment."""
    spec = _published_spec(exam, results)
    spec['title'] = 'Top Ten'
    return spec


def _summary_spec(exam, columns, results, sheet_columns):
    """Results Summary: three small tables, so three worksheets."""
    report = grade_distribution_report(results, sheet_columns)
    counts = [
        [safe_text(row['label']), row['count']] for row in report['class_rows']
    ]
    counts.append(['Total Examinee', report['total_students']])

    matrix_headers = ['Grade'] + [col['subject'].code for col in sheet_columns]
    matrix_rows = [
        [safe_text(row['label'])] + list(row['counts']) for row in report['matrix']
    ]
    scale = [
        [safe_text(row['band']), safe_text(row['grade']), number(row['point'])]
        for row in grade_scale_rows()
    ]
    return {
        'title': 'Results Summary',
        'sheets': [
            {
                'name': 'Grade Count',
                'headers': ['Grade', 'Students'],
                'rows': counts,
                'widths': [26, 12],
                'notes': [],
                'legend': [],
            },
            {
                'name': 'Grade x Subject',
                'headers': matrix_headers,
                'rows': matrix_rows,
                'widths': [26] + [12] * len(sheet_columns),
                'notes': [],
                'legend': [
                    f"{col['subject'].code} = {col['subject'].name}"
                    + (f" (Full Marks {col['full_marks']})" if col['full_marks'] else '')
                    for col in sheet_columns
                ],
            },
            {
                'name': 'Grading Scale',
                'headers': ['Full Marks', 'Grade', 'G.P.'],
                'rows': scale,
                'widths': [18, 10, 10],
                'notes': [],
                'legend': [],
            },
        ],
    }


def build_spec(exam, kind, group=None):
    """Everything a writer needs for one download, computed once.

    Returns ``None`` for an unknown ``kind``. The exam must be published when
    the caller renders a published sheet; that rule lives in the view so the
    download can never be a back door around it.
    """
    if kind not in KINDS:
        return None
    columns, results = build_exam_results(exam, group=group)
    results = register_order(results)
    sheet_columns = build_sheet_columns(exam, columns, group=group)

    if kind == 'sheet':
        spec = _sheet_spec(exam, columns, results, sheet_columns)
    elif kind == 'published':
        spec = _published_spec(exam, results)
    elif kind == 'top10':
        ranked = [row for row in results if row['position']][:10]
        for row in ranked:
            row['comment'] = _merit_comment(row)
        spec = _top_ten_spec(exam, ranked)
    else:  # summary
        spec = _summary_spec(exam, columns, results, sheet_columns)

    if 'sheets' not in spec:
        spec['sheets'] = [{
            'name': spec['title'],
            'headers': spec['headers'],
            'rows': spec['rows'],
            'widths': spec['widths'],
            'notes': spec['notes'],
            'legend': spec['legend'],
        }]
    spec['kind'] = kind
    spec['exam'] = exam
    spec['subtitle'] = _subtitle(exam, group)
    spec['filename'] = _filename(exam, kind)
    return spec


def _merit_comment(result):
    """Golden / Potential, the same wording the Top Ten paper prints."""
    graded = [
        cell for cell in result.get('subject_results', [])
        if not cell.get('not_applicable') and not cell.get('pending')
    ]
    if not graded:
        return ''
    a_plus = sum(1 for cell in graded if (cell.get('grade') or '') == 'A+')
    if a_plus == len(graded):
        return 'Golden'
    if a_plus == len(graded) - 1:
        return 'Potential'
    return ''


def _subtitle(exam, group=None):
    parts = []
    klass = exam.admission_class
    if klass:
        parts.append(f'Class {klass}')
    if exam.section:
        parts.append(f'Section {exam.section}')
    from .models import Student
    group_label = dict(Student.GROUP_CHOICES).get(group or exam.group or '', '')
    if group_label:
        parts.append(group_label)
    if exam.session:
        parts.append(f'Session {exam.session}')
    return ' | '.join(parts)


def _filename(exam, kind):
    """A filename a clerk can read in the downloads folder."""

    def clean(value):
        return ''.join(
            char for char in str(value or '') if char.isalnum() or char in '-_'
        )[:24]

    stamp = timezone.localdate().isoformat()
    pieces = [
        KINDS[kind].replace(' ', '-'),
        f'Class-{clean(exam.admission_class)}' if exam.admission_class else '',
        f'Section-{clean(exam.section)}' if exam.section else '',
        f'Session-{clean(exam.session)}' if exam.session else '',
        stamp,
    ]
    return '_'.join(piece for piece in pieces if piece)


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def _school_lines():
    info = getattr(settings, 'SCHOOL_INFO', {}) or {}
    name = info.get('school_name') or 'School'
    address = info.get('address') or ''
    phone = info.get('school_phone') or ''
    contact = ' | '.join(piece for piece in (address, phone) if piece)
    return name, contact


def _write_xlsx(spec):
    if openpyxl is None:  # pragma: no cover - guarded by the view
        raise RuntimeError('openpyxl is not installed')

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    name, contact = _school_lines()
    exam = spec['exam']
    thin = Side(style='thin', color='FF9AA5B1')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill('solid', fgColor='FF0F2D52')
    band_fill = PatternFill('solid', fgColor='FFF6F7FA')
    power_fill = PatternFill('solid', fgColor='FFC9A227')

    for index, sheet_spec in enumerate(spec['sheets']):
        title = sheet_spec['name'][:31] or 'Sheet'
        sheet = workbook.create_sheet(title=title)
        column_count = max(len(sheet_spec['headers']), 1)
        last_letter = get_column_letter(column_count)

        # Letterhead: the school identifies itself on every download, exactly
        # like the paper it mirrors.
        sheet.merge_cells(f'A1:{last_letter}1')
        sheet['A1'] = name
        sheet['A1'].font = Font(bold=True, size=15, color='FF0F2D52')
        sheet['A1'].alignment = Alignment(horizontal='center')

        sheet.merge_cells(f'A2:{last_letter}2')
        sheet['A2'] = contact
        sheet['A2'].font = Font(size=9, color='FF44546A')
        sheet['A2'].alignment = Alignment(horizontal='center')

        sheet.merge_cells(f'A3:{last_letter}3')
        sheet['A3'] = f"{exam.name} | {spec['subtitle']}"
        sheet['A3'].font = Font(size=10, color='FF44546A')
        sheet['A3'].alignment = Alignment(horizontal='center')

        sheet.merge_cells(f'A4:{last_letter}4')
        sheet['A4'] = spec['title'] if index == 0 else f"{spec['title']} — {sheet_spec['name']}"
        sheet['A4'].font = Font(bold=True, size=12, color='FFFFFFFF')
        sheet['A4'].fill = head_fill
        sheet['A4'].alignment = Alignment(horizontal='center', vertical='center')
        sheet.row_dimensions[4].height = 22

        header_row = 6
        for column_index, header in enumerate(sheet_spec['headers'], start=1):
            cell = sheet.cell(row=header_row, column=column_index, value=header)
            cell.font = Font(bold=True, color='FFFFFFFF')
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = border

        for offset, row in enumerate(sheet_spec['rows'], start=1):
            for column_index, value in enumerate(row, start=1):
                cell = sheet.cell(
                    row=header_row + offset, column=column_index,
                    value=_cell_value(value),
                )
                cell.border = border
                cell.alignment = Alignment(
                    horizontal='left' if column_index <= 3 else 'center',
                    vertical='center',
                )
                if isinstance(cell.value, float):
                    cell.number_format = '0.00'
                if offset % 2 == 0:
                    cell.fill = band_fill

        row_cursor = header_row + len(sheet_spec['rows']) + 1
        if sheet_spec.get('notes'):
            sheet.cell(row=row_cursor, column=1, value='Summary').font = Font(bold=True)
            row_cursor += 1
            for label, value in sheet_spec['notes']:
                label_cell = sheet.cell(row=row_cursor, column=1, value=safe_text(label))
                label_cell.font = Font(bold=True, size=9)
                value_cell = sheet.cell(row=row_cursor, column=2, value=_cell_value(value))
                value_cell.font = Font(size=9)
                value_cell.alignment = Alignment(horizontal='center')
                row_cursor += 1

        if sheet_spec.get('legend'):
            row_cursor += 1
            sheet.cell(row=row_cursor, column=1, value='Subject codes').font = Font(bold=True, size=9)
            for line in sheet_spec['legend']:
                row_cursor += 1
                cell = sheet.cell(row=row_cursor, column=1, value=safe_text(line))
                cell.font = Font(size=9, color='FF44546A')

        row_cursor += 2
        stamped = timezone.localtime().strftime('%d-%b-%Y %H:%M')
        sheet.cell(
            row=row_cursor, column=1,
            value=f'Downloaded {stamped} — {spec["title"]} · {spec["subtitle"]}',
        ).font = Font(size=8, color='FF808080')

        # Widths, frozen header and a filter: the three things that make an
        # office spreadsheet pleasant rather than merely complete.
        for column_index, width in enumerate(sheet_spec['widths'], start=1):
            sheet.column_dimensions[get_column_letter(column_index)].width = width
        sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
        if sheet_spec['rows']:
            sheet.auto_filter.ref = (
                f'A{header_row}:{last_letter}{header_row + len(sheet_spec["rows"])}'
            )
        sheet.sheet_view.showGridLines = False
        sheet.print_title_rows = f'{header_row}:{header_row}'
        sheet.page_setup.orientation = 'landscape' if column_count > 6 else 'portrait'
        sheet.page_setup.fitToWidth = 1
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.oddFooter.center.text = f'{name} — Page &P of &N'
        sheet.oddFooter.center.size = 8

    if not workbook.sheetnames:  # pragma: no cover - defensive
        workbook.create_sheet(title='Result')
    return workbook


def xlsx_response(spec):
    workbook = _write_xlsx(spec)
    response = HttpResponse(content_type=XLSX_CONTENT_TYPE)
    response['Content-Disposition'] = f'attachment; filename="{spec["filename"]}.xlsx"'
    # Cache-control keeps a shared machine from serving the last clerk's copy.
    response['Cache-Control'] = 'private, no-store'
    workbook.save(response)
    return response


def csv_response(spec):
    sheet_spec = spec['sheets'][0]
    response = HttpResponse(content_type=CSV_CONTENT_TYPE)
    response['Content-Disposition'] = f'attachment; filename="{spec["filename"]}.csv"'
    response['Cache-Control'] = 'private, no-store'
    response.write('\ufeff')  # BOM: Excel opens UTF-8 names correctly
    writer = csv.writer(response)
    writer.writerow([safe_text(header) for header in sheet_spec['headers']])
    for row in sheet_spec['rows']:
        writer.writerow([
            '' if value is None else (
                f'{value:g}' if isinstance(value, float) else safe_text(value)
            )
            for value in row
        ])
    return response


def build_response(spec, fmt):
    """The file the browser saves, in the format the caller asked for."""
    if fmt == 'csv':
        return csv_response(spec)
    return xlsx_response(spec)


def download_stamp():
    """Timestamp used in the reply header (kept separate for easy testing)."""
    return datetime.now().isoformat(timespec='seconds')
