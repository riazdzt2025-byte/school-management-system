"""Excel and CSV downloads of the printed result sheets.

The office used to get a result out of the system in exactly one way: click
"Print / Save PDF" and pick *Save as PDF* in the browser dialog. That works,
but it hands the office a picture of a table — no sorting, no filtering, no
adding a column of its own — and it asks a clerk to find the right printer
dialog. Every sheet therefore also leaves the system as a file, in two shapes
that answer two different needs:

* **Excel, the paper's own layout** — the school letterhead (badge name in the
  red of the letterhead, founder/address/mobile, exam title), the class info
  box, the same table the page prints (black rules, bold grade column), the
  closing summary box, the signature lines, and a page footer. Print it and it
  reads like the sheet everyone already knows; work in it and it is a
  spreadsheet with a frozen header and a filter.
* **Data only** — one clean table, no letterhead and no decoration, for the
  clerk who wants to sort, pivot or paste it somewhere else. Available as Excel
  or CSV.

Three rules keep a download trustworthy:

1. **One source of truth.** The rows come from the same
   :func:`~students.result_utils.build_exam_results` computation the printed
   sheet renders, so a downloaded GPA can never disagree with the paper.
2. **No formula injection.** A name or comment that starts with ``=``, ``+``,
   ``-`` or ``@`` is prefixed with an apostrophe, so opening a file exported by
   a user cannot execute a spreadsheet formula.
3. **No surprise downloads.** Nothing here is reachable without signing in, and
   the exam must be in the caller's own institution and already published.
"""
from __future__ import annotations

import csv

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from .result_utils import (
    build_exam_results,
    build_sheet_columns,
    golden_a_plus,
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

#: ``fmt`` -> what the browser saves. ``xlsx`` is the paper's layout, ``data``
#: is the same rows without a letterhead, ``csv`` is the plainest of the three.
FORMATS = ('xlsx', 'data', 'csv')

#: Leading characters a spreadsheet treats as the start of a formula.
_FORMULA_STARTERS = ('=', '+', '-', '@', '\t', '\r')

# The paper's own colours: the letterhead is printed in this red, everything
# else is black on white.
LETTERHEAD_RED = 'FFA32121'
INK = 'FF000000'
RULE = 'FF000000'
SHADE = 'FFF2F3F5'
PAPER_FONT = 'Arial'


# --------------------------------------------------------------------------- #
# Cell helpers
# --------------------------------------------------------------------------- #
def safe_text(value):
    """A cell that can never be read as a formula.

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


def _sheet_spec(exam, results, sheet_columns):
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
    legend = _legend(sheet_columns)
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


def _summary_spec(exam, results, sheet_columns):
    """Results Summary: three small tables, so three worksheets.

    The grade × subject matrix prints its Total column on the right of every
    grade row and the per-subject Total row underneath — the office reads a
    grade row against the class total beside it, so both are kept.
    """
    report = grade_distribution_report(results, sheet_columns)
    counts = [
        [safe_text(row['label']), row['count']] for row in report['class_rows']
    ]
    counts.append(['Total Examinee', report['total_students']])

    matrix_headers = ['Grade'] + [col['subject'].code for col in sheet_columns] + ['Total']
    matrix_rows = [
        [safe_text(row['label'])] + list(row['counts']) + [row['total']]
        for row in report['matrix']
    ]
    matrix_rows.append(
        ['Total'] + list(report['column_totals']) + [report['matrix_total']]
    )
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
                'widths': [26] + [12] * (len(sheet_columns) + 1),
                'notes': [],
                'legend': _legend(sheet_columns),
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


def _legend(sheet_columns):
    return [
        f"{column['subject'].code} = {column['subject'].name}"
        + (f" (Full Marks {column['full_marks']})" if column['full_marks'] else '')
        for column in sheet_columns
    ]


def build_spec(exam, kind, group=None):
    """Everything a writer needs for one download, computed once.

    Returns ``None`` for an unknown ``kind``.
    """
    if kind not in KINDS:
        return None
    columns, results = build_exam_results(exam, group=group)
    results = register_order(results)
    sheet_columns = build_sheet_columns(exam, columns, group=group)

    if kind == 'sheet':
        spec = _sheet_spec(exam, results, sheet_columns)
    elif kind == 'published':
        spec = _published_spec(exam, results)
    elif kind == 'top10':
        ranked = [row for row in results if row['position']][:10]
        for row in ranked:
            row['comment'] = _merit_comment(row)
        spec = _top_ten_spec(exam, ranked)
    else:  # summary
        spec = _summary_spec(exam, results, sheet_columns)

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
    spec['info_box'] = _info_box(exam, results, group)
    spec['signatures'] = _signatures(kind)
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


def _info_box(exam, results, group=None):
    """The six cells of the letterhead's class info box, as the paper prints it."""
    from .models import Student

    total = len(results)
    passed = sum(1 for row in results if row['status'] == 'Pass')
    group_label = dict(Student.GROUP_CHOICES).get(group or exam.group or '', '')
    section_group = ' / '.join(
        part for part in (exam.section, group_label) if part
    ) or 'All'
    return [
        ('Year', _exam_year(exam)),
        ('Class', exam.admission_class),
        ('Section/Group', section_group),
        ('Pass Rate in Class', f'{int(100 * passed / total) if total else 0} %'),
        ('Total A Plus', sum(1 for row in results if (row.get('grade') or '') == 'A+')),
        ('Golden A Plus', sum(1 for row in results if golden_a_plus(row))),
    ]


def _signatures(kind):
    """Who signs the sheet, left to right, exactly as the paper prints it."""
    if kind == 'sheet':
        return ['Guide Teacher', 'Controller of Exam', 'Convener', 'Head Teacher']
    return ['Guide Teacher', 'Controller of Exam', 'Head Teacher']


def _exam_year(exam):
    if exam.exam_date:
        return exam.exam_date.year
    import re as _re

    years = _re.findall(r'(20\d{2})', exam.session or '')
    return int(years[-1]) if years else timezone.now().year


def _subtitle(exam, group=None):
    from .models import Student

    parts = []
    if exam.admission_class:
        parts.append(f'Class {exam.admission_class}')
    if exam.section:
        parts.append(f'Section {exam.section}')
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


def _write_paper_sheet(sheet, spec, sheet_spec, first=True):
    """One worksheet drawn like the printed sheet.

    Letterhead (red, centred) → class info box → the table with black rules →
    the closing summary box → the signature lines → the download footer. Rows
    and columns are laid out in the same order a reader's eye follows the paper.
    """
    headers = sheet_spec['headers']
    column_count = max(len(headers), 1)
    last_letter = get_column_letter(column_count)
    thin = Side(style='thin', color='FF000000')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    name, contact = _school_lines()
    exam = spec['exam']

    # ---- Letterhead -------------------------------------------------------
    sheet.merge_cells(f'A1:{last_letter}1')
    sheet['A1'] = name
    sheet['A1'].font = Font(name=PAPER_FONT, bold=True, size=16, color=LETTERHEAD_RED)
    sheet['A1'].alignment = Alignment(horizontal='center', vertical='center')
    sheet.row_dimensions[1].height = 26

    sheet.merge_cells(f'A2:{last_letter}2')
    sheet['A2'] = contact
    sheet['A2'].font = Font(name='Courier New', bold=True, size=9, color=LETTERHEAD_RED)
    sheet['A2'].alignment = Alignment(horizontal='center')

    sheet.merge_cells(f'A3:{last_letter}3')
    sheet['A3'] = exam.name
    sheet['A3'].font = Font(name=PAPER_FONT, bold=True, size=12, underline='single', color=INK)
    sheet['A3'].alignment = Alignment(horizontal='center')

    sheet.merge_cells(f'A4:{last_letter}4')
    sheet['A4'] = spec['title'] if first else f"{spec['title']} — {sheet_spec['name']}"
    sheet['A4'].font = Font(name=PAPER_FONT, bold=True, size=10.5, color=INK)
    sheet['A4'].alignment = Alignment(horizontal='center')

    # ---- Class info box (bottom-right of the letterhead) ------------------
    info_start = 6
    info_width = 2
    info_col = max(column_count - info_width + 1, 1)
    right_col = get_column_letter(column_count)
    for offset, (label, value) in enumerate(spec['info_box']):
        row = info_start + offset
        label_cell = sheet.cell(row=row, column=info_col, value=label)
        label_cell.font = Font(name=PAPER_FONT, bold=True, size=8.5)
        label_cell.border = border
        value_cell = sheet.cell(row=row, column=info_col + 1, value=_cell_value(value))
        value_cell.font = Font(name=PAPER_FONT, size=8.5)
        value_cell.border = border
        value_cell.alignment = Alignment(horizontal='center')

    # ---- Subject-code legend, on the left of the info box ------------------
    legend_row = info_start
    if sheet_spec.get('legend'):
        legend_last = max(info_col - 2, 1)
        sheet.merge_cells(
            start_row=legend_row, start_column=1, end_row=legend_row, end_column=legend_last
        )
        sheet.cell(row=legend_row, column=1, value='Subject codes').font = Font(
            name=PAPER_FONT, bold=True, size=8.5,
        )
        for line in sheet_spec['legend']:
            legend_row += 1
            sheet.merge_cells(
                start_row=legend_row, start_column=1,
                end_row=legend_row, end_column=legend_last,
            )
            cell = sheet.cell(row=legend_row, column=1, value=safe_text(line))
            cell.font = Font(name=PAPER_FONT, size=8.5)
            cell.alignment = Alignment(horizontal='left')

    # ---- The table --------------------------------------------------------
    header_row = max(info_start + len(spec['info_box']), legend_row) + 2
    for column_index, header in enumerate(headers, start=1):
        cell = sheet.cell(row=header_row, column=column_index, value=header)
        cell.font = Font(name=PAPER_FONT, bold=True, size=9)
        cell.fill = PatternFill('solid', fgColor=SHADE)
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border
    sheet.row_dimensions[header_row].height = 30

    for offset, row in enumerate(sheet_spec['rows'], start=1):
        for column_index, value in enumerate(row, start=1):
            cell = sheet.cell(
                row=header_row + offset, column=column_index, value=_cell_value(value),
            )
            cell.font = Font(
                name=PAPER_FONT, size=9,
                bold=column_index <= len(headers) and headers[column_index - 1] in ('Grade', 'Total'),
            )
            cell.border = border
            cell.alignment = Alignment(
                horizontal='left' if column_index <= 3 else 'center', vertical='center',
            )
            if isinstance(cell.value, float):
                cell.number_format = '0.00'
    table_end = header_row + len(sheet_spec['rows'])

    cursor = table_end + 2

    # ---- Closing summary box ---------------------------------------------
    if sheet_spec.get('notes'):
        sheet.cell(row=cursor, column=1, value='Summary').font = Font(
            name=PAPER_FONT, bold=True, size=9,
        )
        cursor += 1
        for label, value in sheet_spec['notes']:
            label_cell = sheet.cell(row=cursor, column=1, value=safe_text(label))
            label_cell.font = Font(name=PAPER_FONT, bold=True, size=8.5)
            label_cell.border = border
            value_cell = sheet.cell(row=cursor, column=2, value=_cell_value(value))
            value_cell.font = Font(name=PAPER_FONT, size=8.5)
            value_cell.border = border
            value_cell.alignment = Alignment(horizontal='center')
            cursor += 1

    # ---- Signature lines --------------------------------------------------
    cursor += 2
    signatures = spec['signatures']
    if signatures:
        line_row = cursor
        label_row = cursor + 1
        # Lay the signature blocks out evenly across the table's own columns,
        # so the sheet never grows a column the table does not have and two
        # names never share (or fight over) one merged range.
        count = len(signatures)
        span = max(column_count // count, 1)
        step = (column_count - span) / (count - 1) if count > 1 else 0
        for index, label in enumerate(signatures):
            start = 1 + round(index * step)
            end = min(start + span - 1, column_count)
            line = sheet.cell(row=line_row, column=start, value=None)
            line.border = Border(top=Side(style='thin', color='FF000000'))
            if end > start:
                sheet.merge_cells(
                    start_row=label_row, start_column=start, end_row=label_row, end_column=end
                )
            cell = sheet.cell(row=label_row, column=start, value=label)
            cell.font = Font(name=PAPER_FONT, bold=True, size=9)
            cell.alignment = Alignment(horizontal='center')
        cursor = label_row + 2

    # ---- Footer -----------------------------------------------------------
    stamped = timezone.localtime().strftime('%d-%b-%Y %H:%M')
    sheet.merge_cells(f'A{cursor}:{last_letter}{cursor}')
    sheet.cell(
        row=cursor, column=1,
        value=f'Downloaded {stamped} — {spec["title"]} · {spec["subtitle"]}',
    ).font = Font(name=PAPER_FONT, size=8, color='FF808080')

    for column_index, width in enumerate(sheet_spec['widths'], start=1):
        sheet.column_dimensions[get_column_letter(column_index)].width = width
    sheet.sheet_view.showGridLines = False
    sheet.print_title_rows = f'{header_row}:{header_row}'
    sheet.page_setup.orientation = 'landscape' if column_count > 6 else 'portrait'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.oddFooter.center.text = f'{name} — Page &P of &N'
    sheet.oddFooter.center.size = 8
    # Freezing keeps the header visible while scrolling; the filter is applied
    # to the table only, never to the letterhead above it.
    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
    if sheet_spec['rows']:
        sheet.auto_filter.ref = f'A{header_row}:{right_col}{table_end}'
    return header_row


def paper_workbook(spec):
    """The workbook that mirrors the printed sheet, letterhead and all."""
    if openpyxl is None:  # pragma: no cover - guarded by the view
        raise RuntimeError('openpyxl is not installed')
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for index, sheet_spec in enumerate(spec['sheets']):
        sheet = workbook.create_sheet(title=(sheet_spec['name'] or 'Sheet')[:31])
        _write_paper_sheet(sheet, spec, sheet_spec, first=index == 0)
    if not workbook.sheetnames:  # pragma: no cover - defensive
        workbook.create_sheet(title='Result')
    return workbook


def data_workbook(spec):
    """The same rows with no letterhead, no rules and no decoration.

    One row of column headers, then the data. Nothing else is added, so the
    sheet can be pasted into an existing workbook, read by a script, or fed to
    a pivot table without cleaning a page of titles off the top first.
    """
    if openpyxl is None:  # pragma: no cover - guarded by the view
        raise RuntimeError('openpyxl is not installed')
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for sheet_spec in spec['sheets']:
        sheet = workbook.create_sheet(title=(sheet_spec['name'] or 'Data')[:31])
        sheet.append([safe_text(header) for header in sheet_spec['headers']])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in sheet_spec['rows']:
            sheet.append([_cell_value(value) for value in row])
        for column_index, width in enumerate(sheet_spec['widths'], start=1):
            sheet.column_dimensions[get_column_letter(column_index)].width = width
        sheet.freeze_panes = 'A2'
        if sheet_spec['rows']:
            last_letter = get_column_letter(len(sheet_spec['headers']))
            sheet.auto_filter.ref = f'A1:{last_letter}{len(sheet_spec["rows"]) + 1}'
    if not workbook.sheetnames:  # pragma: no cover - defensive
        workbook.create_sheet(title='Data')
    return workbook


def _attach(workbook, filename, suffix):
    response = HttpResponse(content_type=XLSX_CONTENT_TYPE)
    response['Content-Disposition'] = f'attachment; filename="{filename}{suffix}.xlsx"'
    # A shared machine must not serve the last clerk's copy from cache.
    response['Cache-Control'] = 'private, no-store'
    workbook.save(response)
    return response


def xlsx_response(spec):
    """Excel in the paper's own layout."""
    return _attach(paper_workbook(spec), spec['filename'], '')


def data_response(spec):
    """Excel holding the rows only."""
    return _attach(data_workbook(spec), spec['filename'], '_data')


def csv_response(spec):
    sheet_spec = spec['sheets'][0]
    response = HttpResponse(content_type=CSV_CONTENT_TYPE)
    response['Content-Disposition'] = f'attachment; filename="{spec["filename"]}_data.csv"'
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
    """The file the browser saves, in the shape the caller asked for."""
    if fmt == 'csv':
        return csv_response(spec)
    if fmt == 'data':
        return data_response(spec)
    return xlsx_response(spec)
