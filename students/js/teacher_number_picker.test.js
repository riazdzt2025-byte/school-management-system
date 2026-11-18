'use strict';

/*
 * Behavioural tests for static/students/js/teacher_number_picker.js — the
 * number-first "Assign a teacher" screen.
 *
 * Zero dependencies: node:test + node:vm over a minimal DOM stub implementing
 * only the APIs the script uses.
 *
 * Run with:  node --test students/js/
 */

const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SCRIPT_PATH = path.join(
    __dirname, '..', 'static', 'students', 'js', 'teacher_number_picker.js'
);
const SCRIPT_SOURCE = fs.readFileSync(SCRIPT_PATH, 'utf8');

/* ---- minimal DOM stub --------------------------------------------------- */

const LOWERCASE_TAGS = new Set(['datalist', 'select']);

class Element {
    constructor(tag, attrs = {}) {
        const name = String(tag);
        // HTML tag names are upper case in the DOM, bar a couple of exceptions.
        this.tagName = LOWERCASE_TAGS.has(name) ? name : name.toUpperCase();
        this.attributes = { ...attrs };
        this.children = [];
        this.parent = null;
        this.listeners = Object.create(null);
        this.ownerDocument = null;
        this.textContent = '';
        this.hidden = Object.prototype.hasOwnProperty.call(attrs, 'hidden');
        this.optionValue = Object.prototype.hasOwnProperty.call(attrs, 'value')
            ? String(attrs.value) : '';
        this.selected = Object.prototype.hasOwnProperty.call(attrs, 'value')
            ? String(attrs.value) : '';
        this.options = this.tagName === 'select' ? [] : undefined;
    }

    /* <option>.value reads the value attribute. */
    get value() {
        if (this.tagName === 'select') {
            const values = this.options.map((option) => option.value);
            return values.indexOf(this.selected) === -1 ? '' : this.selected;
        }
        return this.optionValue;
    }

    set value(next) {
        const text = String(next === undefined || next === null ? '' : next);
        if (this.tagName === 'select') {
            this.selected = text;
        }
        this.optionValue = text;
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    getAttribute(name) {
        return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
    }

    appendChild(child) {
        child.parent = this;
        this.children.push(child);
        if (child.ownerDocument === null) child.ownerDocument = this.ownerDocument;
        return child;
    }

    replaceChildren(...nodes) {
        this.children = [];
        for (const node of nodes) this.appendChild(node);
        this.syncOptions();
    }

    /* The browser derives <select>.options from the <option> children. */
    syncOptions() {
        if (this.tagName !== 'select') return;
        this.options = this.children.map((child) => ({
            value: child.value,
            textContent: child.textContent,
            label: child.textContent,
        }));
    }

    addEventListener(type, handler) {
        (this.listeners[type] = this.listeners[type] || []).push(handler);
    }

    emit(type, extra = {}) {
        const event = { defaultPrevented: false, target: this, ...extra };
        if (!event.preventDefault) event.preventDefault = () => { event.defaultPrevented = true; };
        for (const handler of this.listeners[type] || []) handler.call(this, event);
        return event;
    }
}

class Document {
    constructor() {
        this.readyState = 'complete';
        this.elements = Object.create(null);
        this.listeners = Object.create(null);
    }

    getElementById(id) {
        return this.elements[id] || null;
    }

    createElement(tag) {
        const node = new Element(tag);
        node.ownerDocument = this;
        return node;
    }

    addEventListener(type, handler) {
        (this.listeners[type] = this.listeners[type] || []).push(handler);
    }
}

/* A script block the view rendered with json_script: textContent is JSON. */
function jsonScript(id, payload) {
    const node = new Element('script', { id, type: 'application/json' });
    node.textContent = JSON.stringify(payload);
    return node;
}

/* Build the page the template renders (ids match the template exactly). */
function buildPage({ teachers, sectionsByClass, subjectsByClass, subjectOptions, initial = {}, branch = { number: BRANCH } }) {
    const document = new Document();
    const node = (tag, attrs = {}) => {
        const element = new Element(tag, attrs);
        element.ownerDocument = document;
        if (attrs.id) document.elements[attrs.id] = element;
        return element;
    };

    const subjectSelect = node('select', { id: 'id_subject' });
    subjectSelect.replaceChildren(...subjectOptions.map(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        return option;
    }));
    subjectSelect.value = initial.subject || '';

    node('input', { id: 'id_teacher_no_input', value: initial.teacherNo || '' });
    const employeeSelect = node('select', { id: 'id_employee' });
    employeeSelect.replaceChildren(...teachers.map((teacher) => {
        const option = document.createElement('option');
        option.value = teacher.id;
        option.textContent = teacher.name;
        return option;
    }));
    const institutionSelect = node('select', { id: 'id_institution' });
    institutionSelect.replaceChildren(...[1, 2].map((id) => {
        const option = document.createElement('option');
        option.value = id;
        option.textContent = 'Institution ' + id;
        return option;
    }));
    node('ul', { id: 'teacher-results', hidden: '' });
    node('div', { id: 'teacher-picked', hidden: '' });
    node('span', { id: 'teacher-picked-initials' });
    node('span', { id: 'teacher-picked-name' });
    node('span', { id: 'teacher-picked-meta' });
    node('span', { id: 'teacher-picked-badge' });
    node('span', { id: 'teacher-search-state' });
    node('input', { id: 'id_admission_class', value: initial.admissionClass || '' });
    node('input', { id: 'id_section', value: initial.section || '' });
    node('datalist', { id: 'teacher-section-options' });
    node('div', { id: 'subject-hint' });
    node('span', { id: 'assign-summary' });
    node('input', { id: 'id_session', value: '2026-2027' });
    node('span', { id: 'session-summary' });

    document.elements['teacher-lookup-data'] = jsonScript('teacher-lookup-data', teachers);
    document.elements['teacher-sections-data'] = jsonScript('teacher-sections-data', sectionsByClass);
    document.elements['teacher-subjects-data'] = jsonScript('teacher-subjects-data', subjectsByClass);
    document.elements['teacher-institution-classes'] = jsonScript('teacher-institution-classes', {});
    document.elements['teacher-branch-data'] = jsonScript('teacher-branch-data', branch);
    return document;
}

const get = (document, id) => document.elements[id] || null;
/* Arrays built inside the vm context are not the host realm's Array, so
   normalise them before a strict deep comparison. */
const arr = (value) => Array.from(value);

/* A <select> built from [[value, label], …] the way a template renders one. */
function buildSelect(document, options) {
    const select = document.createElement('select');
    select.replaceChildren(...options.map(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        return option;
    }));
    return select;
}

function load(document) {
    const context = vm.createContext({ document });
    vm.runInContext(SCRIPT_SOURCE, context, { filename: 'teacher_number_picker.js' });
    return context.TeacherNumberPicker;
}

const TEACHERS = [
    {
        id: 1, number: '2011020001', pretty: '2011 02 0001', name: 'Salma Akter',
        designation: 'Assistant Teacher', institution: 1, status: 'Active', active: true,
        initials: 'SA', branch_label: 'School 2',
    },
    {
        id: 2, number: '2011020002', pretty: '2011 02 0002', name: 'Karim Mia',
        designation: 'Senior Teacher', institution: 1, status: 'Active', active: true,
        initials: 'KM', branch_label: 'School 2',
    },
    {
        id: 3, number: '2011020007', pretty: '2011 02 0007', name: 'Retired Rahman',
        designation: 'Teacher', institution: 1, status: 'Resigned', active: false,
        initials: 'RR', branch_label: 'School 2',
    },
    {
        id: 4, number: '2011010001', pretty: '2011 01 0001', name: 'College Teacher',
        designation: 'Lecturer', institution: 2, status: 'Active', active: true,
        initials: 'CT', branch_label: 'College 1',
    },
];

/* The branch the page was opened in: School 2 -> "02". */
const BRANCH = '02';

const SECTIONS = { 9: ['A', 'B'], 10: ['A'] };
const SUBJECTS = { 9: ['11', '12'], 10: ['11'] };
const SUBJECT_OPTIONS = [['', '— pick a subject —'], ['11', 'Physics'], ['12', 'Chemistry'], ['13', 'Botany']];

const PAGE = {
    teachers: TEACHERS,
    sectionsByClass: SECTIONS,
    subjectsByClass: SUBJECTS,
    subjectOptions: SUBJECT_OPTIONS,
};

/* ---- pure helpers: normalising what a clerk types ----------------------- */

test('Bangla digits are read as the same numbers', (t) => {
    const api = load(new Document());
    t.assert.equal(api.toLatinDigits('২০১১০২০০০১'), '2011020001');
    t.assert.equal(api.normalizeNumber('২০১১০২০০০১'), '2011020001');
});

test('spacing, dashes and dots are ignored', (t) => {
    const api = load(new Document());
    for (const typed of ['2011 02 0001', '2011-02-0001', '2011.02.0001', '2011 020001']) {
        t.assert.equal(api.normalizeNumber(typed), '2011020001', typed);
    }
});

test('the branch code is the institution number', (t) => {
    const api = load(new Document());
    t.assert.equal(api.normalizeBranch(2), '02');
    t.assert.equal(api.normalizeBranch('02'), '02');
    t.assert.equal(api.normalizeBranch('1'), '01');
    t.assert.equal(api.normalizeBranch(''), '');
    t.assert.equal(api.normalizeBranch('abc'), '');
    t.assert.equal(api.normalizeBranch(100), '');
});

test('the bare serial becomes the branch number', (t) => {
    const api = load(new Document());
    t.assert.equal(api.normalizeNumber('1', BRANCH), '2011020001');
    t.assert.equal(api.normalizeNumber('0007', BRANCH), '2011020007');
    t.assert.equal(api.prettyNumber('7', BRANCH), '2011 02 0007');
    // Without a branch a bare serial is ambiguous — never guessed.
    t.assert.equal(api.normalizeNumber('1'), '');
});

test('a branch + serial typed together is a full number', (t) => {
    const api = load(new Document());
    for (const typed of ['02 0001', '02-0001', '020001']) {
        t.assert.equal(api.normalizeNumber(typed), '2011020001', typed);
    }
    t.assert.equal(api.normalizeNumber('01 0001'), '2011010001');
});

test('free text is not turned into a number', (t) => {
    const api = load(new Document());
    t.assert.equal(api.normalizeNumber('salma'), '');
    t.assert.equal(api.normalizeNumber(''), '');
});

test('the display form groups year, branch and serial', (t) => {
    const api = load(new Document());
    t.assert.equal(api.prettyNumber('2011020001'), '2011 02 0001');
    t.assert.equal(api.prettyNumber('2011010042'), '2011 01 0042');
});

/* ---- pure helpers: resolving what is typed ------------------------------ */

test('one exact number picks that teacher', (t) => {
    const api = load(new Document());
    const result = api.resolveInput('2011 02 0001', TEACHERS, BRANCH);
    t.assert.equal(result.kind, 'picked');
    t.assert.equal(result.teacher.name, 'Salma Akter');
});

test('another branch\'s number picks that branch\'s teacher', (t) => {
    const api = load(new Document());
    const result = api.resolveInput('2011 01 0001', TEACHERS, BRANCH);
    t.assert.equal(result.kind, 'picked');
    t.assert.equal(result.teacher.name, 'College Teacher');
});

test('the branch\'s own serial number picks its teacher', (t) => {
    const api = load(new Document());
    const result = api.resolveInput('0002', TEACHERS, BRANCH);
    t.assert.equal(result.kind, 'picked');
    t.assert.equal(result.teacher.name, 'Karim Mia');
});

test('a number nobody has is reported as unknown, not as empty', (t) => {
    const api = load(new Document());
    const result = api.resolveInput('2011 02 9999', TEACHERS, BRANCH);
    t.assert.equal(result.kind, 'unknown');
    t.assert.equal(result.query, '2011 02 9999');
});

test('a prefix offers the matching teachers to choose from', (t) => {
    const api = load(new Document());
    const result = api.resolveInput('2011 02 00', TEACHERS, BRANCH);
    t.assert.equal(result.kind, 'choose');
    t.assert.deepEqual(arr(result.matches).map((row) => row.number), ['2011020001', '2011020002', '2011020007']);
    // A serial on its own never offers another branch's teachers.
    const serialOnly = api.resolveInput('00', TEACHERS, BRANCH);
    t.assert.deepEqual(arr(serialOnly.matches).map((row) => row.number), ['2011020001', '2011020002', '2011020007']);
});

test('nothing typed yet is empty, not unknown', (t) => {
    const api = load(new Document());
    t.assert.equal(api.resolveInput('', TEACHERS, BRANCH).kind, 'empty');
    t.assert.equal(api.resolveInput('   ', TEACHERS, BRANCH).kind, 'empty');
});

test('a typed name finds its teacher', (t) => {
    const api = load(new Document());
    const result = api.resolveInput('karim', TEACHERS, BRANCH);
    t.assert.equal(result.kind, 'picked');
    t.assert.equal(result.teacher.number, '2011020002');
});

/* ---- pure helpers: fewer choices ---------------------------------------- */

test('sections come from the class the school actually uses', (t) => {
    const api = load(new Document());
    t.assert.deepEqual(arr(api.sectionsFor('9', SECTIONS)), ['A', 'B']);
    t.assert.deepEqual(arr(api.sectionsFor('10', SECTIONS)), ['A']);
    t.assert.deepEqual(arr(api.sectionsFor('', SECTIONS)), []);
    t.assert.deepEqual(arr(api.sectionsFor('12', SECTIONS)), []);
});

test('subjects are narrowed to the class curriculum', (t) => {
    const api = load(new Document());
    t.assert.deepEqual(arr(api.subjectsFor('9', SUBJECTS)), ['11', '12']);
    t.assert.deepEqual(arr(api.subjectsFor('10', SUBJECTS)), SUBJECTS[10]);
    t.assert.equal(api.subjectsFor('99', SUBJECTS), null, 'unknown class keeps every subject');
});

test('filtering a select drops subjects outside the curriculum', (t) => {
    const api = load(new Document());
    const select = buildSelect(new Document(), SUBJECT_OPTIONS);
    select.value = '13';
    const result = api.filterSelectOptions(select, ['11', '12'], '— pick a subject —');
    t.assert.equal(result.cleared, true, 'an out-of-curriculum choice is cleared');
    t.assert.deepEqual(select.options.map((option) => option.value), ['', '11', '12']);
    t.assert.equal(select.value, '');
});

test('filtering with no known curriculum keeps every option', (t) => {
    const api = load(new Document());
    const select = buildSelect(new Document(), SUBJECT_OPTIONS);
    select.value = '13';
    const result = api.filterSelectOptions(select, null);
    t.assert.equal(result.cleared, false);
    t.assert.equal(select.options.length, SUBJECT_OPTIONS.length);
    t.assert.equal(select.value, '13');
});

test('the section datalist is filled once, without duplicates', (t) => {
    const api = load(new Document());
    const document = new Document();
    const list = document.createElement('datalist');
    const count = api.fillDatalist(list, ['A', 'B', 'A', '', null]);
    t.assert.equal(count, 2);
    t.assert.deepEqual(list.children.map((child) => child.value), ['A', 'B']);
});

/* ---- the wired-up screen ------------------------------------------------ */

function buildScreen(initial = {}, branch = { number: BRANCH }) {
    const document = buildPage({ ...PAGE, initial, branch });
    const api = load(document);
    const controller = api.createController(document);
    controller.attach();
    return { document, controller, api };
}

test('typing a full number shows the name and fills the hidden employee', (t) => {
    const { document: page } = buildScreen();
    get(page, 'id_teacher_no_input').value = '2011 02 0001';
    get(page, 'id_teacher_no_input').emit('input');

    t.assert.equal(get(page, 'id_employee').value, '1');
    t.assert.equal(get(page, 'id_institution').value, '1');
    t.assert.equal(get(page, 'teacher-picked').hidden, false);
    t.assert.equal(get(page, 'teacher-picked-name').textContent, 'Salma Akter');
    t.assert.equal(get(page, 'teacher-picked-meta').textContent, '2011 02 0001 · Assistant Teacher');
    t.assert.equal(get(page, 'teacher-picked-badge').textContent, 'Active');
    t.assert.equal(get(page, 'teacher-search-state').textContent, 'found');
    t.assert.equal(get(page, 'teacher-results').hidden, true);
});

test('a resigned teacher is surfaced, not silently assigned', (t) => {
    const { document: page } = buildScreen();
    const input = get(page, 'id_teacher_no_input');
    input.value = '2011 02 0007';
    input.emit('input');
    t.assert.equal(get(page, 'teacher-picked-badge').textContent, 'Resigned');
    t.assert.equal(get(page, 'teacher-picked-badge').className, 'badge bg-secondary');
});

test('an unknown number says so and leaves the form unassigned', (t) => {
    const { document: page } = buildScreen();
    const input = get(page, 'id_teacher_no_input');
    input.value = '2011 02 9999';
    input.emit('input');

    t.assert.equal(get(page, 'teacher-search-state').textContent, 'no match');
    t.assert.equal(get(page, 'teacher-results').hidden, false);
    t.assert.equal(get(page, 'teacher-results').children.length, 1);
    t.assert.match(get(page, 'teacher-results').children[0].textContent, /No teacher has this number/);
    t.assert.equal(get(page, 'id_employee').value, '');
    t.assert.equal(get(page, 'teacher-picked').hidden, true);
});

test('clearing the box clears the selection', (t) => {
    const { document: page } = buildScreen();
    const input = get(page, 'id_teacher_no_input');
    input.value = '2011 02 0001';
    input.emit('input');
    input.value = '';
    input.emit('input');

    t.assert.equal(get(page, 'id_employee').value, '');
    t.assert.equal(get(page, 'teacher-picked').hidden, true);
    t.assert.equal(get(page, 'teacher-search-state').textContent, 'teachers only');
});

test('a partial number offers a short list; Enter picks the highlighted one', (t) => {
    const { document: page } = buildScreen();
    const input = get(page, 'id_teacher_no_input');
    input.value = '2011 02 00';
    input.emit('input');

    t.assert.equal(get(page, 'teacher-results').hidden, false);
    t.assert.equal(get(page, 'teacher-results').children.length, 3);
    t.assert.equal(get(page, 'teacher-search-state').textContent, 'choose below');

    input.emit('keydown', { key: 'ArrowDown' });   // second row
    const event = input.emit('keydown', { key: 'Enter' });
    t.assert.equal(event.defaultPrevented, true);
    t.assert.equal(get(page, 'id_employee').value, '2');
    t.assert.equal(input.value, '2011 02 0002');
});

test('clicking a match picks that teacher', (t) => {
    const { document: page } = buildScreen();
    const input = get(page, 'id_teacher_no_input');
    input.value = '2011 02 00';
    input.emit('input');

    const rows = get(page, 'teacher-results').children;
    t.assert.ok(rows.length >= 2);
    const target = rows[1];
    get(page, 'teacher-results').emit('click', { target });
    t.assert.equal(get(page, 'id_employee').value, String(TEACHERS[1].id));
});

test('choosing a class fills the section list and narrows the subjects', (t) => {
    const { document: page } = buildScreen();
    const classInput = get(page, 'id_admission_class');
    classInput.value = '9';
    classInput.emit('input');

    t.assert.deepEqual(
        get(page, 'teacher-section-options').children.map((child) => child.value), ['A', 'B']
    );
    t.assert.deepEqual(
        get(page, 'id_subject').options.map((option) => option.value), ['', '11', '12']
    );
    t.assert.match(get(page, 'subject-hint').textContent, /2 subjects in the class 9 curriculum/);
});

test('switching to a class without the chosen subject clears it', (t) => {
    const { document: page } = buildScreen({ admissionClass: '9', subject: '12' });
    const classInput = get(page, 'id_admission_class');
    classInput.value = '10';
    classInput.emit('input');

    t.assert.equal(get(page, 'id_subject').value, '');
    t.assert.match(get(page, 'subject-hint').textContent, /previous subject is not taught in class 10/i);
    t.assert.deepEqual(
        get(page, 'id_subject').options.map((option) => option.value), ['', '11']
    );
});

test('an unknown class leaves every subject available but says why', (t) => {
    const { document: page } = buildScreen();
    const classInput = get(page, 'id_admission_class');
    classInput.value = '12';
    classInput.emit('input');
    t.assert.match(get(page, 'subject-hint').textContent, /Pick a class/);
    t.assert.equal(get(page, 'id_subject').options.length, SUBJECT_OPTIONS.length);
});

test('the summary line states class, section and subject as they are picked', (t) => {
    const { document: page } = buildScreen();
    get(page, 'id_admission_class').value = '9';
    get(page, 'id_admission_class').emit('input');
    get(page, 'id_section').value = 'A';
    get(page, 'id_section').emit('change');
    get(page, 'id_subject').value = '11';
    get(page, 'id_subject').emit('change');
    t.assert.equal(get(page, 'assign-summary').textContent, 'Class 9 · Section A · Physics');
});

test('the session summary mirrors the session box', (t) => {
    const { document: page } = buildScreen();
    get(page, 'id_session').value = '2025-2026';
    get(page, 'id_session').emit('change');
    t.assert.equal(get(page, 'session-summary').textContent, '2025-2026');
});

test('an edit screen lands on the saved teacher, already narrowed', (t) => {
    const { document: page } = buildScreen({
        teacherNo: '2011 02 0001', admissionClass: '9', section: 'B', subject: '12',
    });
    t.assert.equal(get(page, 'id_employee').value, '1');
    t.assert.equal(get(page, 'teacher-picked').hidden, false);
    t.assert.equal(get(page, 'teacher-picked-name').textContent, 'Salma Akter');
    t.assert.deepEqual(
        get(page, 'id_subject').options.map((option) => option.value), ['', '11', '12']
    );
    t.assert.equal(get(page, 'id_subject').value, '12');
});

test('a screen without the number box is a silent no-op', (t) => {
    const document = new Document();
    const api = load(document);
    const controller = api.createController(document);
    t.assert.doesNotThrow(() => controller.attach());
    t.assert.doesNotThrow(() => controller.refresh());
});

test('the lookup data is read defensively', (t) => {
    const document = new Document();
    document.elements['id_teacher_no_input'] = document.createElement('input');
    const broken = document.createElement('script');
    broken.textContent = 'not json';
    document.elements['teacher-lookup-data'] = broken;
    const api = load(document);
    const controller = api.createController(document);
    t.assert.doesNotThrow(() => controller.attach());
});

test('attaching twice does not double-handle the input', (t) => {
    // The script auto-attaches on load; a page that includes it twice (or a
    // caller that builds its own controller) must still show one message.
    const { document: page, controller } = buildScreen({ admissionClass: '9', subject: '12' });
    controller.attach();  // second attach on the same page
    const classInput = get(page, 'id_admission_class');
    classInput.value = '10';
    classInput.emit('input');
    t.assert.equal(
        get(page, 'subject-hint').textContent,
        '1 subjects in the class 10 curriculum. The previous subject is not taught in '
        + 'class 10, so it was cleared.'
    );
});
