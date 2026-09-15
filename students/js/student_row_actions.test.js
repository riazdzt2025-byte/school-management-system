'use strict';

/*
 * Behavioural tests for static/students/js/student_row_actions.js — the
 * checkbox tracker that keeps the student list's row action buttons (Details,
 * Edit, ID Card, Marksheet, "More actions" dropdown) disabled until the row's
 * checkbox is ticked, mirroring the bulk-update buttons.
 *
 * Zero dependencies: node:test + node:vm over a minimal DOM stub that
 * implements exactly the APIs the script uses.
 *
 * Run with:  node --test students/js/
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SCRIPT_PATH = path.join(__dirname, '..', 'static', 'students', 'js', 'student_row_actions.js');
const SCRIPT_SOURCE = fs.readFileSync(SCRIPT_PATH, 'utf8');

/* ---- minimal DOM stub -------------------------------------------------- */

function makeClassList(initial = []) {
    const classes = new Set(initial);
    return {
        add: (...names) => names.forEach((n) => classes.add(n)),
        remove: (...names) => names.forEach((n) => classes.delete(n)),
        contains: (name) => classes.has(name),
        toggle: (name, force) => {
            const want = force === undefined ? !classes.has(name) : Boolean(force);
            if (want) classes.add(name);
            else classes.delete(name);
            return want;
        },
    };
}

class Element {
    constructor(tag, attrs = {}, classes = []) {
        this.tagName = String(tag).toUpperCase();
        this.attributes = { ...attrs };
        // A real DOM keeps classList in sync with the class attribute.
        const attrClasses = this.attributes.class
            ? String(this.attributes.class).split(/\s+/).filter(Boolean)
            : [];
        this.classList = makeClassList([...classes, ...attrClasses]);
        this.children = [];
        this.parent = null;
        this.listeners = Object.create(null);
        // The disabled IDL attribute reflects the disabled content attribute.
        this.disabled = this.tagName === 'BUTTON'
            ? Object.prototype.hasOwnProperty.call(attrs, 'disabled')
            : undefined;
        this.checked = this.tagName === 'INPUT' ? false : undefined;
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
        return child;
    }

    addEventListener(type, handler) {
        (this.listeners[type] = this.listeners[type] || []).push(handler);
    }

    emit(type, extra = {}) {
        const event = { defaultPrevented: false, ...extra };
        if (!event.target) event.target = this;
        if (!event.preventDefault) {
            event.preventDefault = () => { event.defaultPrevented = true; };
        }
        if (!event.stopPropagation) {
            event.stopPropagation = () => { event.stopped = true; };
        }
        for (const handler of this.listeners[type] || []) handler.call(this, event);
        return event;
    }

    matches(selector) {
        if (selector.startsWith('.')) return this.classList.contains(selector.slice(1));
        return this.tagName === String(selector).toUpperCase();
    }

    closest(selector) {
        let node = this;
        while (node) {
            if (node.matches && node.matches(selector)) return node;
            node = node.parent;
        }
        return null;
    }

    querySelectorAll(selector) {
        const found = [];
        const visit = (node) => {
            for (const child of node.children) {
                if (child.matches && child.matches(selector)) found.push(child);
                visit(child);
            }
        };
        visit(this);
        return found;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] || null;
    }
}

function makeDocument(root) {
    const listeners = Object.create(null);
    return {
        readyState: 'complete',
        addEventListener(type, handler) {
            (listeners[type] = listeners[type] || []).push(handler);
        },
        emit(type, extra = {}) {
            const event = { defaultPrevented: false, ...extra };
            event.preventDefault = event.preventDefault || (() => { event.defaultPrevented = true; });
            event.stopPropagation = event.stopPropagation || (() => { event.stopped = true; });
            for (const handler of listeners[type] || []) handler(event);
            return event;
        },
        querySelectorAll(selector) {
            return root.querySelectorAll(selector);
        },
        querySelector(selector) {
            return root.querySelectorAll(selector)[0] || null;
        },
    };
}

/* Build a table shaped like the real student list: one header row plus N
   student rows, each with a .row-checkbox and a locked action bar holding
   Details / Edit / ID Card links and the "More actions" dropdown toggle. */
function buildDocument({ rows = 3 } = {}) {
    const wrapper = new Element('div');
    const table = new Element('table');
    const thead = new Element('thead');
    thead.appendChild(new Element('tr'));
    const tbody = new Element('tbody');
    const rowRefs = [];

    for (let i = 0; i < rows; i += 1) {
        const row = new Element('tr');

        const checkboxCell = new Element('td');
        const checkbox = new Element(
            'input',
            { type: 'checkbox', name: 'student_ids', value: String(i + 1) },
            ['form-check-input', 'row-checkbox'],
        );
        checkboxCell.appendChild(checkbox);
        row.appendChild(checkboxCell);

        const actionsCell = new Element('td');
        const bar = new Element('div', {}, ['student-actions-bar', 'student-actions-locked']);
        const details = new Element('a', {
            href: `/students/${i + 1}/`,
            title: 'View Details',
            'aria-disabled': 'true',
            class: 'btn btn-outline-secondary student-action',
        });
        const edit = new Element('a', {
            href: `/students/${i + 1}/edit/`,
            title: 'Edit Student',
            'aria-disabled': 'true',
            class: 'btn btn-outline-primary student-action',
        });
        const idCard = new Element('a', {
            href: `/students/${i + 1}/id-card/`,
            title: 'Print ID Card',
            'aria-disabled': 'true',
            class: 'btn btn-outline-secondary student-action',
        });
        const moreToggle = new Element('button', {
            type: 'button',
            'data-bs-toggle': 'dropdown',
            'aria-disabled': 'true',
            disabled: 'true',
            class: 'btn btn-outline-secondary dropdown-toggle dropdown-toggle-split student-action',
        });
        bar.appendChild(details);
        bar.appendChild(edit);
        bar.appendChild(idCard);
        bar.appendChild(moreToggle);
        actionsCell.appendChild(bar);
        row.appendChild(actionsCell);

        tbody.appendChild(row);
        rowRefs.push({ row, checkbox, bar, details, edit, idCard, moreToggle });
    }

    table.appendChild(thead);
    table.appendChild(tbody);
    wrapper.appendChild(table);
    return { document: makeDocument(wrapper), rows: rowRefs };
}

function loadScript(document) {
    const context = vm.createContext({ document });
    vm.runInContext(SCRIPT_SOURCE, context, { filename: 'student_row_actions.js' });
    return context;
}

function tick(checkbox) {
    checkbox.checked = true;
    checkbox.emit('change');
}

function untick(checkbox) {
    checkbox.checked = false;
    checkbox.emit('change');
}

/* ---- tests -------------------------------------------------------------- */

test('initial state: every row starts locked, exactly as the server renders it', (t) => {
    const { document, rows } = buildDocument({ rows: 3 });
    const context = loadScript(document);
    const api = context.StudentRowActions;

    t.assert.ok(api, 'window.StudentRowActions is exported');
    for (const ref of rows) {
        t.assert.ok(ref.bar.classList.contains('student-actions-locked'), 'bar has locked class');
        for (const button of [ref.details, ref.edit, ref.idCard, ref.moreToggle]) {
            t.assert.equal(button.getAttribute('aria-disabled'), 'true');
        }
        t.assert.equal(ref.moreToggle.disabled, true, 'dropdown toggle is natively disabled');
        t.assert.equal(api.isRowLocked(ref.checkbox), true);
    }
});

test('checking one row tick enables only that row\'s action buttons', (t) => {
    const { document, rows } = buildDocument({ rows: 3 });
    loadScript(document);

    tick(rows[1].checkbox);

    const unlocked = [rows[1].details, rows[1].edit, rows[1].idCard, rows[1].moreToggle];
    for (const button of unlocked) {
        t.assert.equal(button.getAttribute('aria-disabled'), 'false');
    }
    t.assert.ok(!rows[1].bar.classList.contains('student-actions-locked'));
    t.assert.equal(rows[1].moreToggle.disabled, false);

    for (const other of [rows[0], rows[2]]) {
        t.assert.ok(other.bar.classList.contains('student-actions-locked'));
        t.assert.equal(other.details.getAttribute('aria-disabled'), 'true');
        t.assert.equal(other.moreToggle.disabled, true);
    }
});

test('unticking the checkbox re-locks the row\'s action buttons', (t) => {
    const { document, rows } = buildDocument({ rows: 1 });
    loadScript(document);

    tick(rows[0].checkbox);
    untick(rows[0].checkbox);

    t.assert.ok(rows[0].bar.classList.contains('student-actions-locked'));
    t.assert.equal(rows[0].details.getAttribute('aria-disabled'), 'true');
    t.assert.equal(rows[0].edit.getAttribute('aria-disabled'), 'true');
    t.assert.equal(rows[0].moreToggle.disabled, true);
});

test('Select All (every checkbox ticked) unlocks every row', (t) => {
    const { document, rows } = buildDocument({ rows: 3 });
    loadScript(document);

    // The page's Select All handler sets each checkbox and dispatches change.
    for (const ref of rows) tick(ref.checkbox);

    for (const ref of rows) {
        t.assert.ok(!ref.bar.classList.contains('student-actions-locked'));
        t.assert.equal(ref.details.getAttribute('aria-disabled'), 'false');
        t.assert.equal(ref.moreToggle.disabled, false);
    }
});

test('click guard blocks clicks on locked rows and allows clicks on selected rows', (t) => {
    const { document, rows } = buildDocument({ rows: 2 });
    loadScript(document);

    // Click on a locked row's link button -> navigation must be cancelled.
    const blockedEvent = document.emit('click', { target: rows[0].details });
    t.assert.equal(blockedEvent.defaultPrevented, true, 'locked Details click is prevented');

    // The locked dropdown toggle is blocked as well.
    const blockedToggleEvent = document.emit('click', { target: rows[0].moreToggle });
    t.assert.equal(blockedToggleEvent.defaultPrevented, true, 'locked dropdown click is prevented');

    // Tick the row: its buttons now work.
    tick(rows[0].checkbox);
    const allowedEvent = document.emit('click', { target: rows[0].details });
    t.assert.equal(allowedEvent.defaultPrevented, false, 'selected-row click is allowed');
    const allowedToggleEvent = document.emit('click', { target: rows[0].moreToggle });
    t.assert.equal(allowedToggleEvent.defaultPrevented, false, 'selected-row dropdown click is allowed');

    // A click on something that is not an action button is never touched.
    const neutralEvent = document.emit('click', { target: rows[1].row });
    t.assert.equal(neutralEvent.defaultPrevented, false);
});

test('isRowLocked helper treats missing/unticked checkboxes as locked', (t) => {
    const { document } = buildDocument({ rows: 1 });
    const api = loadScript(document).StudentRowActions;
    t.assert.equal(api.isRowLocked(null), true);
    t.assert.equal(api.isRowLocked(undefined), true);
    t.assert.equal(api.isRowLocked({ checked: false }), true);
    t.assert.equal(api.isRowLocked({ checked: true }), false);
});
