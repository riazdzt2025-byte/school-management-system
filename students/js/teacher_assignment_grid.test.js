'use strict';

/*
 * Behavioural tests for static/students/js/teacher_assignment_grid.js — the
 * per-subject teacher search on the "assign a class" grid.
 *
 * Zero dependencies: node:test + node:vm over a DOM stub implementing only the
 * APIs the script uses.
 *
 * Run with:  node --test students/js/
 */

const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SCRIPT_PATH = path.join(
    __dirname, '..', 'static', 'students', 'js', 'teacher_assignment_grid.js'
);
const SCRIPT_SOURCE = fs.readFileSync(SCRIPT_PATH, 'utf8');

/* ---- minimal DOM stub --------------------------------------------------- */

class ClassList {
    constructor(initial) {
        this.names = new Set(String(initial || '').split(/\s+/).filter(Boolean));
    }
    add(name) { this.names.add(name); }
    contains(name) { return this.names.has(name); }
    toString() { return Array.from(this.names).join(' '); }
}

class Element {
    constructor(tag, attrs = {}) {
        this.tagName = String(tag).toUpperCase();
        this.attributes = { ...attrs };
        this.children = [];
        this.parent = null;
        this.parentElement = null;
        this.listeners = Object.create(null);
        this.ownerDocument = null;
        this.textContent = '';
        this.hidden = Object.prototype.hasOwnProperty.call(attrs, 'hidden');
        this.value = Object.prototype.hasOwnProperty.call(attrs, 'value') ? String(attrs.value) : '';
        this.classList = new ClassList(attrs.class);
    }

    set className(value) {
        this.classList = new ClassList(value);
    }

    get className() {
        return this.classList.toString();
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
        this.syncParent();
        return child;
    }

    syncParent() {
        if (!this.parentElement) {
            for (const child of this.children) {
                child.parentElement = this;
                child.syncParent();
            }
        }
    }

    replaceChildren(...nodes) {
        this.children = [];
        for (const node of nodes) this.appendChild(node);
    }

    querySelector(selector) {
        const match = /^\.([\w-]+)$/.exec(String(selector));
        if (match) {
            for (const child of this.children) {
                if (child.classList.contains(match[1])) return child;
                const nested = child.querySelector(selector);
                if (nested) return nested;
            }
            return null;
        }
        const attr = /^\[([\w-]+)="?([^"\]]+)"?\]$/.exec(String(selector));
        if (attr) {
            for (const child of this.children) {
                if (child.getAttribute(attr[1]) === attr[2]) return child;
                const nested = child.querySelector(selector);
                if (nested) return nested;
            }
        }
        return null;
    }

    querySelectorAll(selector) {
        const match = /^([a-z]*)(?:\.([\w-]+))?$/.exec(String(selector));
        const tag = match && match[1] ? match[1].toUpperCase() : '';
        const cls = match && match[2] ? match[2] : '';
        const found = [];
        const walk = (node) => {
            for (const child of node.children) {
                if ((!tag || child.tagName === tag) && (!cls || child.classList.contains(cls))) {
                    found.push(child);
                }
                walk(child);
            }
        };
        walk(this);
        return found;
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
        this.timers = [];
        this.body = new Element('body');
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

    querySelector(selector) {
        return this.body.querySelector(selector);
    }
}

function jsonScript(document, id, payload) {
    const node = new Element('script', { id, type: 'application/json' });
    node.ownerDocument = document;
    node.textContent = JSON.stringify(payload);
    document.elements[id] = node;
    return node;
}

const TEACHERS = [
    {
        id: 1, number: '2011020001', pretty: '2011 02 0001', name: 'Salma Akter',
        designation: 'Assistant Teacher', status: 'Active', active: true,
        also: ['Class 10 (A) · Physics'],
    },
    {
        id: 2, number: '2011020002', pretty: '2011 02 0002', name: 'Karim Mia',
        designation: 'Senior Teacher', status: 'Active', active: true, also: [],
    },
    {
        id: 3, number: '2011020007', pretty: '2011 02 0007', name: 'Retired Rahman',
        designation: 'Teacher', status: 'Resigned', active: false, also: [],
    },
    {
        id: 4, number: '2011010001', pretty: '2011 01 0001', name: 'College Teacher',
        designation: 'Lecturer', status: 'Active', active: true, also: [],
    },
];

const BRANCH = { number: '02', name: 'Grid School' };

/*
 * Build the page exactly as the template renders it: one row per subject, the
 * hidden employee id, the text box, the meta line and the results list.
 */
function buildPage({ rows = [{ subject: '11' }, { subject: '12' }], initial = {} } = {}) {
    const document = new Document();
    const form = document.createElement('form');
    form.setAttribute('id', 'assignment-grid-form');
    document.elements['assignment-grid-form'] = form;
    document.body.appendChild(form);

    for (const row of rows) {
        const cell = document.createElement('td');
        cell.className = 'teacher-cell';
        const hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.value = initial[row.subject] ? String(initial[row.subject]) : '';
        hidden.setAttribute('id', 'employee_' + row.subject);
        document.elements['employee_' + row.subject] = hidden;
        cell.appendChild(hidden);

        const wrap = document.createElement('div');
        wrap.className = 'search-wrap';
        const input = document.createElement('input');
        input.setAttribute('data-subject', row.subject);
        input.className = 'grid-teacher-input';
        wrap.appendChild(input);
        const state = document.createElement('span');
        state.className = 'search-state';
        state.textContent = 'search';
        wrap.appendChild(state);
        cell.appendChild(wrap);

        const meta = document.createElement('div');
        meta.setAttribute('data-picked-meta', row.subject);
        cell.appendChild(meta);

        const results = document.createElement('ul');
        results.setAttribute('id', 'results_' + row.subject);
        results.hidden = true;
        cell.appendChild(results);
        document.elements['results_' + row.subject] = results;

        form.appendChild(cell);
        cell.syncParent();
    }

    jsonScript(document, 'grid-teacher-data', TEACHERS);
    jsonScript(document, 'grid-branch-data', BRANCH);
    return document;
}

function load(document) {
    // The page's own <script> runs once per page: a second load on the same
    // document would evaluate the script twice, so tests reuse the first api.
    if (document.__gridApi) {
        return document.__gridApi;
    }
    const context = vm.createContext({
        document,
        window: undefined,
        setTimeout: (fn) => fn(),
    });
    vm.runInContext(SCRIPT_SOURCE, context, { filename: 'teacher_assignment_grid.js' });
    document.__gridApi = context.TeacherAssignmentGrid;
    return context.TeacherAssignmentGrid;
}

function controller(page) {
    const api = load(page);
    const control = api.createController(page);
    control.attach();
    return { api, control };
}

const subject = (page, id) => page.elements['teacher_' + id] || page.getElementById('teacher_' + id);
const rowOf = (page, id) => page.getElementById('results_' + id);

/* Every subject box by id, because the page keys them by subject pk. */
function queryInput(page, id) {
    return page.getElementById('employee_' + id).parentElement.querySelectorAll('input.grid-teacher-input')[0];
}

/* ---- pure helpers ------------------------------------------------------- */

test('Bangla digits and separators are read as the same number', (t) => {
    const api = load(new Document());
    t.assert.equal(api.normalizeNumber('২০১১০২০০০১'), '2011020001');
    t.assert.equal(api.normalizeNumber('2011-02-0001'), '2011020001');
    t.assert.equal(api.normalizeNumber('2011 02 0001'), '2011020001');
});

test('a bare serial is read against the page branch', (t) => {
    const api = load(new Document());
    t.assert.equal(api.normalizeNumber('0007', '02'), '2011020007');
    t.assert.equal(api.normalizeNumber('7', '2'), '2011020007');
    t.assert.equal(api.normalizeNumber('0007'), '');
});

test('the display form groups year, branch and serial', (t) => {
    const api = load(new Document());
    t.assert.equal(api.prettyNumber('2011020001'), '2011 02 0001');
    t.assert.equal(api.pickedLabel(TEACHERS[0]), '2011 02 0001 · Salma Akter');
});

test('an exact number picks one teacher; the branch serial picks its own', (t) => {
    const api = load(new Document());
    const exact = api.resolveInput('2011 02 0001', TEACHERS, '02');
    t.assert.equal(exact.kind, 'picked');
    t.assert.equal(exact.teacher.name, 'Salma Akter');
    const serial = api.resolveInput('0002', TEACHERS, '02');
    t.assert.equal(serial.kind, 'picked');
    t.assert.equal(serial.teacher.name, 'Karim Mia');
});

test('another branch number picks that branch teacher', (t) => {
    const api = load(new Document());
    const result = api.resolveInput('2011 01 0001', TEACHERS, '02');
    t.assert.equal(result.kind, 'picked');
    t.assert.equal(result.teacher.branch_label || result.teacher.name, 'College Teacher');
});

test('a typed name finds its teacher, an unknown name says so', (t) => {
    const api = load(new Document());
    const byName = api.resolveInput('salma', TEACHERS, '02');
    t.assert.equal(byName.kind, 'picked');
    t.assert.equal(byName.teacher.name, 'Salma Akter');
    t.assert.equal(api.resolveInput('nobody here', TEACHERS, '02').kind, 'unknown');
    t.assert.equal(api.resolveInput('', TEACHERS, '02').kind, 'empty');
});

test('a partial number lists the candidates instead of guessing', (t) => {
    const api = load(new Document());
    const result = api.resolveInput('2011 02 00', TEACHERS, '02');
    t.assert.equal(result.kind, 'choose');
    t.assert.equal(result.matches.length, 3);
});

test('the meta line names an inactive teacher and the other classes', (t) => {
    const api = load(new Document());
    t.assert.equal(api.metaText(TEACHERS[2]), 'Teacher · Resigned');
    t.assert.match(api.metaText(TEACHERS[0]), /Assistant Teacher/);
    t.assert.match(api.metaText(TEACHERS[0]), /also teaches Class 10 \(A\) · Physics/);
    t.assert.equal(api.metaText(null), null);
});

/* ---- the grid itself ---------------------------------------------------- */

test('typing an exact number fills the row, its id and its meta line', (t) => {
    const page = buildPage();
    controller(page);
    const input = queryInput(page, '11');
    input.value = '0001';
    input.emit('input');
    t.assert.equal(page.getElementById('employee_11').value, '1');
    t.assert.equal(input.value, '2011 02 0001 · Salma Akter');
    t.assert.match(page.getElementById('results_11').hidden ? '' : 'x', /^$/);
    t.assert.match(page.body.querySelector('[data-picked-meta="11"]').children[0].textContent, /also teaches/);
});

test('an unknown number is reported and the row stays unassigned', (t) => {
    const page = buildPage();
    controller(page);
    const input = queryInput(page, '11');
    input.value = '2011 02 0099';
    input.emit('input');
    t.assert.equal(page.getElementById('employee_11').value, '');
    const results = rowOf(page, '11');
    t.assert.equal(results.hidden, false);
    t.assert.equal(results.children[0].className, 'empty');
});

test('a partial number offers the candidates and Enter picks one', (t) => {
    const page = buildPage();
    controller(page);
    const input = queryInput(page, '11');
    input.value = '2011 02 00';
    input.emit('input');
    t.assert.equal(rowOf(page, '11').hidden, false);
    t.assert.equal(rowOf(page, '11').children.length, 3);
    const event = input.emit('keydown', { key: 'Enter' });
    t.assert.equal(event.defaultPrevented, true);
    t.assert.equal(page.getElementById('employee_11').value, '1');
});

test('arrow down moves the highlight before Enter picks', (t) => {
    const page = buildPage();
    controller(page);
    const input = queryInput(page, '11');
    input.value = '2011 02 00';
    input.emit('input');
    input.emit('keydown', { key: 'ArrowDown' });
    input.emit('keydown', { key: 'Enter' });
    t.assert.equal(page.getElementById('employee_11').value, '2');
});

test('clicking a result picks that teacher', (t) => {
    const page = buildPage();
    controller(page);
    const input = queryInput(page, '11');
    input.value = '2011 02 00';
    input.emit('input');
    const item = rowOf(page, '11').children[1];
    rowOf(page, '11').emit('click', { target: item });
    t.assert.equal(page.getElementById('employee_11').value, '2');
});

test('clearing a box clears the picked teacher', (t) => {
    const page = buildPage({ initial: { 11: 1 } });
    controller(page);
    const input = queryInput(page, '11');
    input.value = '';
    input.emit('input');
    t.assert.equal(page.getElementById('employee_11').value, '');
});

test('a picked teacher is suggested on the next empty row (the whole point)', (t) => {
    const page = buildPage();
    const { control } = controller(page);
    t.assert.equal(control.pick('11', 1), true);
    t.assert.equal(page.getElementById('employee_11').value, '1');
    // The second row was empty: Enter there takes the same teacher without
    // typing the number again.
    const next = queryInput(page, '12');
    const event = next.emit('keydown', { key: 'Enter' });
    t.assert.equal(event.defaultPrevented, true);
    t.assert.equal(page.getElementById('employee_12').value, '1');
});

test('the controller state is exactly what the form will post', (t) => {
    const page = buildPage();
    const { control } = controller(page);
    control.pick('11', 1);
    control.pick('12', 2);
    t.assert.deepEqual(control.state(), [
        { subject: '11', employee: '1' },
        { subject: '12', employee: '2' },
    ]);
    t.assert.equal(control.rows, 2);
});

test('an edit screen lands on the saved teacher', (t) => {
    const page = buildPage({ initial: { 11: 3 } });
    controller(page);
    const meta = page.body.querySelector('[data-picked-meta="11"]');
    // The stub's textContent is not aggregated from children, so read the span.
    t.assert.match(meta.children[0].textContent, /Resigned/);
    t.assert.equal(page.getElementById('employee_11').value, '3');
});

test('a screen without the grid is a silent no-op', (t) => {
    const document = new Document();
    const api = load(document);
    const control = api.createController(document);
    t.assert.doesNotThrow(() => control.attach());
    t.assert.equal(control.rows, 0);
});

test('attaching twice does not double-handle the input', (t) => {
    const page = buildPage();
    const { control } = controller(page);
    control.attach();
    const input = queryInput(page, '11');
    input.value = '0001';
    input.emit('input');
    t.assert.equal(page.getElementById('employee_11').value, '1');
});

test('broken lookup data is read defensively', (t) => {
    const document = new Document();
    const form = document.createElement('form');
    form.setAttribute('id', 'assignment-grid-form');
    document.elements['assignment-grid-form'] = form;
    const broken = new Element('script', { id: 'grid-teacher-data' });
    broken.textContent = 'not json';
    document.elements['grid-teacher-data'] = broken;
    const api = load(document);
    t.assert.doesNotThrow(() => api.createController(document).attach());
});
