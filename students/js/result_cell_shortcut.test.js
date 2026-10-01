'use strict';

/*
 * Behavioural tests for static/students/js/result_cell_shortcut.js — the E8
 * Ctrl/Cmd+Click correction shortcut on a published result (result sheet cells
 * -> that subject's marks entry, Full Rank List rows -> the exam's marks entry),
 * always in a new tab so the register is never lost.
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

const SCRIPT_PATH = path.join(
    __dirname, '..', 'static', 'students', 'js', 'result_cell_shortcut.js',
);
const SCRIPT_SOURCE = fs.readFileSync(SCRIPT_PATH, 'utf8');

const ENTER_MARKS_BASE = '/students/exams/7/marks/';

/* ---- minimal DOM stub -------------------------------------------------- */

class Element {
    constructor(tag, attrs = {}, children = []) {
        this.tagName = String(tag).toUpperCase();
        this.attributes = { ...attrs };
        this.children = [];
        this.parent = null;
        this.listeners = Object.create(null);
        for (const child of children) this.appendChild(child);
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    getAttribute(name) {
        return Object.prototype.hasOwnProperty.call(this.attributes, name)
            ? this.attributes[name]
            : null;
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
        for (const handler of this.listeners[type] || []) handler.call(this, event);
        return event;
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
            for (const handler of listeners[type] || []) handler(event);
            return event;
        },
    };
}

/* A result-sheet fragment: one group-filtered table whose cells carry the
   subject pk of their own column plus the group in view. The Religion cell
   holds the paper that student sits (42), not the REL column. */
function buildResultSheet() {
    const banglaCell = new Element('td', {
        'data-subject-pk': '11',
        'data-group': 'SCI',
        class: 'mark-cell',
    }, [new Element('span', { class: 'mark-number' })]);
    const physicsCell = new Element('td', {
        'data-subject-pk': '23',
        'data-group': 'SCI',
        class: 'mark-cell',
    }, [new Element('span', { class: 'grade-badge' })]);
    const religionCell = new Element('td', {
        'data-subject-pk': '42',
        'data-group': 'SCI',
        class: 'mark-cell',
    });
    const ungroupedCell = new Element('td', { 'data-subject-pk': '31', class: 'mark-cell' });
    const forbiddenCell = new Element('td', {
        'data-subject-pk': '99',
        'data-group': 'SCI',
        'data-shortcut-disabled': 'true',
        title: 'Ask Exam dept',
        class: 'mark-cell',
    });

    const row = new Element('tr', {}, [banglaCell, physicsCell, religionCell, ungroupedCell, forbiddenCell]);
    const tbody = new Element('tbody', {}, [row]);
    const table = new Element('table', {}, [tbody]);
    const wrapper = new Element('div', { 'data-enter-marks-base': ENTER_MARKS_BASE }, [table]);

    return {
        document: makeDocument(wrapper),
        cells: { banglaCell, physicsCell, religionCell, ungroupedCell, forbiddenCell },
    };
}

/* A Full Rank List fragment: no subject columns, so each row carries a
   ready-made shortcut URL to this exam's marks entry. */
function buildRankList() {
    const rankRow = new Element('tr', { 'data-shortcut-url': '/students/exams/7/select-subject/?group=SCI' }, [
        new Element('td', {}, [new Element('a', { href: '/students/exams/7/results/5/' })]),
    ]);
    const tbody = new Element('tbody', {}, [rankRow]);
    const table = new Element('table', {}, [tbody]);
    const wrapper = new Element('div', {}, [table]);
    return { document: makeDocument(wrapper), rankRow, link: rankRow.children[0].children[0] };
}

function loadScript(document) {
    const opened = [];
    const context = vm.createContext({
        document,
        open: (url, target, features) => {
            opened.push({ url, target, features });
            return {};
        },
    });
    vm.runInContext(SCRIPT_SOURCE, context, { filename: 'result_cell_shortcut.js' });
    return { api: context.ResultCellShortcut, opened };
}

/* ---- tests -------------------------------------------------------------- */

test('Ctrl+Click on a subject cell opens that subject\'s marks entry in a new tab', (t) => {
    const { document, cells } = buildResultSheet();
    const { api, opened } = loadScript(document);

    t.assert.ok(api, 'window.ResultCellShortcut is exported');

    const event = document.emit('click', { ctrlKey: true, target: cells.physicsCell });

    t.assert.equal(opened.length, 1, 'exactly one window is opened');
    t.assert.equal(opened[0].url, `${ENTER_MARKS_BASE}23/?group=SCI`);
    t.assert.equal(opened[0].target, '_blank', 'opens a new tab, never replaces the register');
    t.assert.equal(opened[0].features, 'noopener');
    t.assert.equal(event.defaultPrevented, true);
});

test('the group in view travels with the shortcut as a querystring', (t) => {
    const { document, cells } = buildResultSheet();
    const { opened } = loadScript(document);

    document.emit('click', { ctrlKey: true, target: cells.banglaCell });

    t.assert.equal(opened.length, 1);
    t.assert.equal(opened[0].url, `${ENTER_MARKS_BASE}11/?group=SCI`);
});

test('Cmd+Click (macOS) behaves exactly like Ctrl+Click', (t) => {
    const { document, cells } = buildResultSheet();
    const { opened } = loadScript(document);

    document.emit('click', { metaKey: true, target: cells.religionCell });

    t.assert.equal(opened.length, 1);
    // 42 is the paper this student sits, not the REL column itself.
    t.assert.equal(opened[0].url, `${ENTER_MARKS_BASE}42/?group=SCI`);
});

test('a plain click does nothing, so the printed sheet never navigates away', (t) => {
    const { document, cells } = buildResultSheet();
    const { opened } = loadScript(document);

    const event = document.emit('click', { target: cells.physicsCell });

    t.assert.equal(opened.length, 0, 'no window opened on a plain click');
    t.assert.equal(event.defaultPrevented, false, 'the plain click is left alone');
});

test('a cell the user may not correct is inert, even with Ctrl held', (t) => {
    const { document, cells } = buildResultSheet();
    const { opened } = loadScript(document);

    const event = document.emit('click', { ctrlKey: true, target: cells.forbiddenCell });

    t.assert.equal(opened.length, 0);
    t.assert.equal(event.defaultPrevented, false);
    t.assert.equal(cells.forbiddenCell.getAttribute('title'), 'Ask Exam dept');
});

test('a cell with no group in view builds the URL without a querystring', (t) => {
    const { document, cells } = buildResultSheet();
    const { opened } = loadScript(document);

    document.emit('click', { ctrlKey: true, target: cells.ungroupedCell });

    t.assert.equal(opened.length, 1);
    t.assert.equal(opened[0].url, `${ENTER_MARKS_BASE}31/`);
    t.assert.ok(!opened[0].url.includes('?'), 'no empty ?group= is appended');
});

test('a Full Rank List row opens the exam\'s marks entry from its own URL', (t) => {
    const { document, rankRow } = buildRankList();
    const { opened } = loadScript(document);

    // A non-link cell finds its containing row. Links retain native behavior.
    document.emit('click', { ctrlKey: true, target: rankRow.children[0] });

    t.assert.equal(opened.length, 1);
    t.assert.equal(opened[0].url, '/students/exams/7/select-subject/?group=SCI');
    t.assert.equal(opened[0].target, '_blank');
});

test('buildEnterMarksUrl normalises the base and encodes both parts', (t) => {
    const { document } = buildResultSheet();
    const { api } = loadScript(document);

    t.assert.equal(api.buildEnterMarksUrl('/students/exams/7/marks/', '11', 'SCI'), '/students/exams/7/marks/11/?group=SCI');
    t.assert.equal(api.buildEnterMarksUrl('/students/exams/7/marks', '11', ''), '/students/exams/7/marks/11/');
    t.assert.equal(api.buildEnterMarksUrl('/students/exams/7/marks/', '11', 'B&S'), '/students/exams/7/marks/11/?group=B%26S');
    t.assert.equal(api.buildEnterMarksUrl('', '11', 'SCI'), '', 'no base means no shortcut');
    t.assert.equal(api.buildEnterMarksUrl('/students/exams/7/marks/', '', 'SCI'), '', 'no subject means no shortcut');
});


for (const [label, flags] of [
    ['Shift only', { shiftKey: true }],
    ['Ctrl+Shift', { ctrlKey: true, shiftKey: true }],
    ['Cmd+Alt', { metaKey: true, altKey: true }],
    ['middle-click', { ctrlKey: true, button: 1 }],
    ['right-click', { metaKey: true, button: 2 }],
    ['keyboard activation', { ctrlKey: true, detail: 0 }],
    ['touch click', { ctrlKey: true, pointerType: 'touch' }],
    ['pen click', { ctrlKey: true, pointerType: 'pen' }],
    ['legacy synthetic touch click', { ctrlKey: true, sourceCapabilities: { firesTouchEvents: true } }],
    ['already handled click', { ctrlKey: true, defaultPrevented: true }],
]) {
    test(`${label} never opens correction`, () => {
        const { document, cells } = buildResultSheet();
        const { opened } = loadScript(document);
        const event = document.emit('click', { target: cells.physicsCell, ...flags });
        assert.equal(opened.length, 0);
        assert.equal(event.defaultPrevented, Boolean(flags.defaultPrevented));
    });
}

test('nested subject text opens correction, while existing links/controls remain native', () => {
    const { document, cells } = buildResultSheet();
    const { opened } = loadScript(document);
    document.emit('click', { ctrlKey: true, target: cells.physicsCell.children[0] });
    assert.equal(opened.length, 1);
    for (const tag of ['a', 'button', 'input', 'select', 'textarea', 'label']) {
        const control = cells.physicsCell.appendChild(new Element(tag));
        const text = control.appendChild(new Element('span'));
        const event = document.emit('click', { ctrlKey: true, target: text });
        assert.equal(event.defaultPrevented, false);
    }
    assert.equal(opened.length, 1);
});

test('rank-row result links retain plain, Ctrl, Shift and middle-click navigation', () => {
    const { document, link } = buildRankList();
    const { opened } = loadScript(document);
    for (const flags of [{}, { ctrlKey: true }, { shiftKey: true }, { button: 1 }]) {
        const event = document.emit('click', { target: link, ...flags });
        assert.equal(event.defaultPrevented, false);
    }
    assert.equal(opened.length, 0);
});

test('missing subject/base/URL/event attributes fail safely without cancelling a click', () => {
    const { document } = buildResultSheet();
    const { api, opened } = loadScript(document);
    for (const target of [null, {}, new Element('td'),
        new Element('td', { 'data-subject-pk': '11' }),
        new Element('tr', { 'data-shortcut-url': '' })]) {
        const event = document.emit('click', { ctrlKey: true, target });
        assert.equal(event.defaultPrevented, false);
    }
    const controller = api.createController(null);
    controller.attach();
    assert.equal(controller.handleClick(null), false);
    assert.equal(api.urlFor(null), '');
    assert.equal(opened.length, 0);
});

test('touchstart blocks a synthetic click; a subsequent mouse pointerdown restores shortcut', () => {
    const { document, cells } = buildResultSheet();
    const { opened } = loadScript(document);
    document.emit('touchstart', { target: cells.physicsCell });
    document.emit('click', { ctrlKey: true, target: cells.physicsCell });
    assert.equal(opened.length, 0);
    document.emit('pointerdown', { pointerType: 'mouse', target: cells.physicsCell });
    document.emit('click', { ctrlKey: true, pointerType: 'mouse', button: 0, detail: 1, target: cells.physicsCell });
    assert.equal(opened.length, 1);
});

test('auxclick and long-press contextmenu have no shortcut handler', () => {
    const { document, cells } = buildResultSheet();
    const { opened } = loadScript(document);
    for (const type of ['auxclick', 'contextmenu']) {
        const event = document.emit(type, { ctrlKey: true, target: cells.physicsCell });
        assert.equal(event.defaultPrevented, false);
    }
    assert.equal(opened.length, 0);
});
