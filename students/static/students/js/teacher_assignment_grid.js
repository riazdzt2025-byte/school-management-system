'use strict';

/*
 * Teacher search for the "assign a class" grid.
 *
 * Every subject row has one text box. As the clerk types a job number, a name
 * or just the branch serial, the script matches against the teacher list the
 * page already rendered (no request per keystroke) and shows a short list under
 * the box. Picking somebody fills the row's hidden employee id, shows their
 * number and name, and — because the same teacher usually takes several
 * subjects — puts their name on top of the next empty row as a one-click hint.
 *
 * Pure helpers are exported on window.TeacherAssignmentGrid so the behaviour
 * can be tested with node:test over a DOM stub (same pattern as
 * teacher_number_picker.js).
 */
(function (globalScope) {
    var BANGLA_DIGITS = '০১২৩৪৫৬৭৮৯';
    var LATIN_DIGITS = '0123456789';
    var YEAR_PREFIX = '2011';
    var BRANCH_WIDTH = 2;
    var SERIAL_WIDTH = 4;
    var MAX_MATCHES = 8;

    function toLatinDigits(value) {
        var text = value === null || value === undefined ? '' : String(value);
        var out = '';
        for (var i = 0; i < text.length; i += 1) {
            var index = BANGLA_DIGITS.indexOf(text[i]);
            out += index === -1 ? text[i] : LATIN_DIGITS[index];
        }
        return out;
    }

    function padBranch(branch) {
        var digits = String(branch);
        while (digits.length < BRANCH_WIDTH) {
            digits = '0' + digits;
        }
        return digits;
    }

    function padSerial(serial) {
        var digits = String(serial);
        while (digits.length < SERIAL_WIDTH) {
            digits = '0' + digits;
        }
        return digits;
    }

    function normalizeBranch(value) {
        var digits = toLatinDigits(value).replace(/\s/g, '');
        if (!/^\d{1,2}$/.test(digits)) {
            return '';
        }
        return padBranch(parseInt(digits, 10));
    }

    /*
     * "2011 02 0001" / "2011-02-0001" / "২০১১০২০০০১" / "02 0001" / "0001" -> compact
     * number. A serial on its own needs the branch (the institution the grid is
     * open in), which is why the page hands it in.
     */
    function normalizeNumber(value, defaultBranch) {
        var compact = toLatinDigits(value).replace(/[\s\-().]/g, '');
        if (!compact || !/^\d+$/.test(compact)) {
            return '';
        }
        var branch = normalizeBranch(defaultBranch);
        if (compact.indexOf(YEAR_PREFIX) === 0) {
            var tail = compact.slice(YEAR_PREFIX.length);
            if (tail.length === BRANCH_WIDTH + SERIAL_WIDTH) {
                return YEAR_PREFIX + padBranch(parseInt(tail.slice(0, BRANCH_WIDTH), 10)) +
                    padSerial(parseInt(tail.slice(BRANCH_WIDTH), 10));
            }
            if (branch && tail && tail.length <= SERIAL_WIDTH) {
                return YEAR_PREFIX + branch + padSerial(parseInt(tail, 10));
            }
            return '';
        }
        if (compact.length === BRANCH_WIDTH + SERIAL_WIDTH) {
            return YEAR_PREFIX + padBranch(parseInt(compact.slice(0, BRANCH_WIDTH), 10)) +
                padSerial(parseInt(compact.slice(BRANCH_WIDTH), 10));
        }
        if (branch && compact.length <= SERIAL_WIDTH) {
            return YEAR_PREFIX + branch + padSerial(parseInt(compact, 10));
        }
        return '';
    }

    /* "2011020001" -> "2011 02 0001" */
    function prettyNumber(value, defaultBranch) {
        var compact = normalizeNumber(value, defaultBranch);
        if (!compact) {
            return value ? String(value) : '';
        }
        return YEAR_PREFIX + ' ' +
            compact.slice(YEAR_PREFIX.length, YEAR_PREFIX.length + BRANCH_WIDTH) + ' ' +
            compact.slice(YEAR_PREFIX.length + BRANCH_WIDTH);
    }

    /*
     * What the typed text means:
     *   { kind: 'empty' }
     *   { kind: 'picked', teacher }
     *   { kind: 'choose', matches }
     *   { kind: 'unknown', query }
     */
    function resolveInput(rawValue, teachers, defaultBranch) {
        var raw = rawValue === null || rawValue === undefined ? '' : String(rawValue).trim();
        if (!raw) {
            return { kind: 'empty' };
        }
        var list = Array.isArray(teachers) ? teachers : [];
        var branch = normalizeBranch(defaultBranch);
        var digits = toLatinDigits(raw).replace(/[\s\-().]/g, '');
        if (/^\d+$/.test(digits)) {
            var normalized = normalizeNumber(digits, branch);
            if (normalized) {
                var exact = list.filter(function (teacher) { return teacher.number === normalized; });
                if (exact.length === 1) {
                    return { kind: 'picked', teacher: exact[0] };
                }
                if (exact.length > 1) {
                    return { kind: 'choose', matches: exact.slice(0, MAX_MATCHES) };
                }
            }
            if (digits.length >= 4) {
                var prefixed = list.filter(function (teacher) {
                    return String(teacher.number || '').indexOf(digits) === 0;
                });
                if (prefixed.length) {
                    return { kind: 'choose', matches: prefixed.slice(0, MAX_MATCHES) };
                }
            }
            if (digits.length <= SERIAL_WIDTH) {
                var serialPrefixes = [digits, padSerial(parseInt(digits, 10))];
                var bySerial = list.filter(function (teacher) {
                    var number = String(teacher.number || '');
                    if (branch && number.slice(YEAR_PREFIX.length, YEAR_PREFIX.length + BRANCH_WIDTH) !== branch) {
                        return false;
                    }
                    var serial = number.slice(YEAR_PREFIX.length + BRANCH_WIDTH);
                    return serialPrefixes.some(function (prefix) {
                        return serial.indexOf(prefix) === 0;
                    });
                });
                if (bySerial.length) {
                    return { kind: 'choose', matches: bySerial.slice(0, MAX_MATCHES) };
                }
            }
            return { kind: 'unknown', query: raw };
        }
        var needle = raw.toLowerCase();
        var byName = list.filter(function (teacher) {
            var haystack = (String(teacher.name || '') + ' ' +
                String(teacher.pretty || teacher.number || '')).toLowerCase();
            return haystack.indexOf(needle) !== -1;
        });
        if (byName.length === 1) {
            return { kind: 'picked', teacher: byName[0] };
        }
        if (byName.length > 1) {
            return { kind: 'choose', matches: byName.slice(0, MAX_MATCHES) };
        }
        return { kind: 'unknown', query: raw };
    }

    /* The label written into the (visible) row box once somebody is picked. */
    function pickedLabel(teacher) {
        if (!teacher) {
            return '';
        }
        var number = teacher.pretty || teacher.number || '';
        return number ? number + ' · ' + teacher.name : teacher.name;
    }

    function teacherKey(teacher) {
        return teacher && teacher.id !== undefined && teacher.id !== null
            ? String(teacher.id) : '';
    }

    /* A one-line "why" under the box; null when there is nothing to say. */
    function metaText(teacher) {
        if (!teacher) {
            return null;
        }
        var parts = [];
        if (teacher.designation) {
            parts.push(teacher.designation);
        }
        if (teacher.active === false) {
            parts.push(teacher.status || 'Inactive');
        }
        if (teacher.also && teacher.also.length) {
            parts.push('also teaches ' + teacher.also.join(', '));
        }
        return parts.length ? parts.join(' · ') : null;
    }

    function readJson(element, fallback) {
        if (!element) {
            return fallback;
        }
        try {
            return JSON.parse(element.textContent || '');
        } catch (error) {
            return fallback;
        }
    }

    function createController(doc) {
        var form = doc.getElementById('assignment-grid-form');
        var dataElement = doc.getElementById('grid-teacher-data');
        if (!form || !dataElement) {
            var noop = function () {};
            return { attach: noop, rows: 0, pick: noop, state: noop };
        }
        if (form.__gridController) {
            // The script auto-attaches on page load, so the page's controller is
            // the one and only owner of these listeners; a caller asking for
            // another gets the live one instead of a dead duplicate.
            return form.__gridController;
        }
        var teachers = readJson(dataElement, []);
        var branchData = readJson(doc.getElementById('grid-branch-data'), {});
        var pageBranch = normalizeBranch(branchData.number);
        var byId = {};
        teachers.forEach(function (teacher) {
            byId[String(teacher.id)] = teacher;
        });
        var rows = [];
        var attached = false;

        function each(nodeList, callback) {
            Array.prototype.forEach.call(nodeList || [], callback);
        }

        function classList(node) {
            if (!node) {
                return [];
            }
            if (node.className) {
                return String(node.className).split(/\s+/);
            }
            var attr = node.getAttribute ? node.getAttribute('class') : '';
            return String(attr || '').split(/\s+/);
        }

        /* First descendant whose class name contains ``name`` (real DOMs and
           the node stub both carry className/getAttribute). */
        function findIn(node, name) {
            if (!node) {
                return null;
            }
            var kids = node.children || [];
            for (var i = 0; i < kids.length; i += 1) {
                if (classList(kids[i]).indexOf(name.slice(1)) !== -1) {
                    return kids[i];
                }
                var nested = findIn(kids[i], name);
                if (nested) {
                    return nested;
                }
            }
            return null;
        }

        function buildRow(input) {
            var subject = input.getAttribute('data-subject') || '';
            var row = {
                subject: subject,
                input: input,
                hidden: doc.getElementById('employee_' + subject),
                results: doc.getElementById('results_' + subject),
                meta: doc.querySelector ? doc.querySelector('[data-picked-meta="' + subject + '"]') : null,
                state: findIn(input.parentElement, '.search-state'),
                matches: [],
                active: -1,
                picked: null,
            };
            return row;
        }

        function setState(row, text) {
            var label = row.state || (row.state = findIn(row.input.parentElement, '.search-state'));
            if (label) {
                label.textContent = text;
            }
        }

        function hideResults(row) {
            if (row.results) {
                row.results.hidden = true;
                if (typeof row.results.replaceChildren === 'function') {
                    row.results.replaceChildren();
                }
            }
            row.matches = [];
            row.active = -1;
        }

        function renderMeta(row) {
            if (!row.meta) {
                return;
            }
            row.meta.textContent = '';
            var text = metaText(row.picked);
            if (text) {
                var span = doc.createElement('span');
                // An inactive teacher or an "also teaches" note is worth the
                // gold colour; the plain designation line stays grey.
                span.className = (row.picked && row.picked.active === false) || (row.picked && row.picked.also && row.picked.also.length)
                    ? 'also' : '';
                span.textContent = text;
                row.meta.appendChild(span);
            }
        }

        function commit(row, teacher) {
            row.picked = teacher || null;
            if (row.hidden) {
                row.hidden.value = teacherKey(teacher);
            }
            if (teacher) {
                row.input.value = pickedLabel(teacher);
            }
            renderMeta(row);
            setState(row, teacher ? 'found' : 'search');
            hideResults(row);
            if (teacher) {
                suggestNextEmptyRow(teacher, row);
            }
        }

        /*
         * The point of the grid: the same teacher usually takes several
         * subjects and other classes. Once a teacher is picked, every empty
         * row is stamped with that teacher as the active suggestion — one
         * Enter/click on the next box takes them without retyping the number.
         */
        function suggestNextEmptyRow(teacher, exceptRow) {
            rows.forEach(function (row) {
                if (row === exceptRow || row.picked || String(row.input.value || '').trim()) {
                    return;
                }
                row.suggested = teacher;
            });
        }

        function renderMatches(row, matches) {
            if (!row.results) {
                return;
            }
            if (typeof row.results.replaceChildren !== 'function') {
                return;
            }
            var nodes = [];
            matches.forEach(function (teacher, index) {
                var item = doc.createElement('li');
                item.setAttribute('role', 'option');
                item.setAttribute('data-index', String(index));
                item.className = index === 0 ? 'active' : '';
                var num = doc.createElement('span');
                num.className = 'num';
                num.textContent = teacher.pretty || teacher.number || '';
                var who = doc.createElement('span');
                who.className = 'who';
                who.textContent = teacher.name + (teacher.designation ? ' · ' + teacher.designation : '') +
                    (teacher.active ? '' : ' · ' + (teacher.status || 'Inactive'));
                item.appendChild(num);
                item.appendChild(who);
                if (teacher.also && teacher.also.length) {
                    var also = doc.createElement('span');
                    also.className = 'also';
                    also.textContent = 'also: ' + teacher.also.slice(0, 2).join(', ');
                    item.appendChild(also);
                }
                nodes.push(item);
            });
            row.results.replaceChildren.apply(row.results, nodes);
            row.results.hidden = false;
            row.matches = matches;
            row.active = 0;
        }

        function renderMessage(row, message) {
            if (!row.results || typeof row.results.replaceChildren !== 'function') {
                return;
            }
            var item = doc.createElement('li');
            item.className = 'empty';
            item.textContent = message;
            row.results.replaceChildren.apply(row.results, [item]);
            row.results.hidden = false;
            row.matches = [];
            row.active = -1;
        }

        function onInput(row) {
            var raw = String(row.input.value || '').trim();
            if (!raw) {
                commit(row, null);
                return;
            }
            // Re-entering the label the picker itself wrote (an edit screen, or
            // a stray extra 'input' event) is not a new search.
            if (row.picked && raw === pickedLabel(row.picked)) {
                return;
            }
            row.picked = null;
            if (row.hidden) {
                row.hidden.value = '';
            }
            renderMeta(row);
            var result = resolveInput(raw, teachers, pageBranch);
            if (result.kind === 'picked') {
                commit(row, result.teacher);
                return;
            }
            if (result.kind === 'choose') {
                setState(row, 'choose');
                renderMatches(row, result.matches);
                return;
            }
            hideResults(row);
            if (result.kind === 'unknown') {
                setState(row, 'no match');
                renderMessage(row, 'No teacher matches. Numbers look like 2011 02 0001.');
                return;
            }
            setState(row, 'keep typing');
        }

        function onKeyDown(row, event) {
            var key = event.key;
            if (key === 'Escape') {
                hideResults(row);
                return;
            }
            if (!row.matches.length) {
                if (key === 'Enter' && row.suggested && !String(row.input.value || '').trim()) {
                    // The hint made by the row above: accept it without typing.
                    event.preventDefault();
                    commit(row, row.suggested);
                }
                return;
            }
            if (key === 'ArrowDown' || key === 'ArrowUp') {
                event.preventDefault();
                row.active = key === 'ArrowDown'
                    ? Math.min(row.active + 1, row.matches.length - 1)
                    : Math.max(row.active - 1, 0);
                if (row.results && row.results.children) {
                    Array.prototype.forEach.call(row.results.children, function (child, index) {
                        child.className = index === row.active ? 'active' : '';
                    });
                }
                return;
            }
            if (key === 'Enter') {
                event.preventDefault();
                var chosen = row.matches[row.active] || row.matches[0];
                if (chosen) {
                    commit(row, chosen);
                }
            }
        }

        function onResultsClick(row, event) {
            var target = event.target;
            while (target && target !== row.results) {
                if (target.getAttribute && target.getAttribute('data-index') !== null) {
                    var index = parseInt(target.getAttribute('data-index'), 10);
                    if (row.matches[index]) {
                        commit(row, row.matches[index]);
                    }
                    return;
                }
                target = target.parentElement;
            }
        }

        function onBlur(row) {
            // Let a click on the list land before the list disappears.
            setTimeout(function () {
                hideResults(row);
            }, 150);
        }

        function attach() {
            // Idempotent across controllers as well as instances: the script
            // auto-attaches on load, so a page that also builds its own
            // controller must not stack a second set of listeners (the second
            // handler would re-read the picked label and clear the row).
            if (attached || form.getAttribute('data-grid-attached') === '1') {
                return;
            }
            attached = true;
            form.setAttribute('data-grid-attached', '1');
            each(form.querySelectorAll('input.grid-teacher-input'), function (input) {
                var row = buildRow(input);
                rows.push(row);
                input.addEventListener('input', function () { onInput(row); });
                input.addEventListener('keydown', function (event) { onKeyDown(row, event); });
                input.addEventListener('blur', function () { onBlur(row); });
                if (row.results) {
                    row.results.addEventListener('mousedown', function (event) {
                        event.preventDefault();
                    });
                    row.results.addEventListener('click', function (event) {
                        onResultsClick(row, event);
                    });
                }
                // Edit/re-visit: the hidden id is the authority, so a row that
                // already has one starts as a picked row.
                if (row.hidden && row.hidden.value && byId[row.hidden.value]) {
                    row.picked = byId[row.hidden.value];
                    renderMeta(row);
                }
            });
            var clear = doc.getElementById('grid-clear-all');
            if (clear) {
                clear.addEventListener('click', function () {
                    rows.forEach(function (row) {
                        row.input.value = '';
                        commit(row, null);
                    });
                });
            }
        }

        function state() {
            return rows.map(function (row) {
                return {
                    subject: row.subject,
                    employee: row.hidden ? String(row.hidden.value || '') : '',
                };
            });
        }

        function pick(subject, employeeId) {
            var row = rows.filter(function (item) { return item.subject === String(subject); })[0];
            if (!row) {
                return false;
            }
            var teacher = byId[String(employeeId)];
            if (!teacher) {
                return false;
            }
            commit(row, teacher);
            return true;
        }

        var api = {
            attach: attach,
            get rows() { return rows.length; },
            pick: pick,
            state: state,
        };
        form.__gridController = api;
        return api;
    }

    globalScope.TeacherAssignmentGrid = {
        toLatinDigits: toLatinDigits,
        normalizeNumber: normalizeNumber,
        normalizeBranch: normalizeBranch,
        prettyNumber: prettyNumber,
        resolveInput: resolveInput,
        pickedLabel: pickedLabel,
        metaText: metaText,
        createController: createController,
        MAX_MATCHES: MAX_MATCHES,
        YEAR_PREFIX: YEAR_PREFIX,
    };

    if (typeof document !== 'undefined' && document && document.addEventListener) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function () {
                createController(document).attach();
            });
        } else {
            createController(document).attach();
        }
    }
})(typeof window !== 'undefined' ? window : globalThis);
