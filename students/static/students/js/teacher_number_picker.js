'use strict';

/*
 * Teacher-number picker for the "Assign a teacher" screen.
 *
 * The clerk types the number they already know from the staff register
 * ("2011 000 001", "2011-000-001", Bangla digits, or just the serial "1"). The
 * script matches it against the teacher list rendered with the page — no
 * request per keystroke — shows the name underneath, and narrows the two
 * dependent pickers:
 *
 *   1. Class → Section   (sections the school actually uses for that class)
 *   2. Class → Subject   (only the subjects in that class's curriculum)
 *
 * Pure helpers are exported on `window.TeacherNumberPicker` so the behaviour can
 * be tested with node:test + a DOM stub (same pattern as student_row_actions.js).
 */
(function (globalScope) {
    var BANGLA_DIGITS = '০১২৩৪৫৬৭৮৯';
    var LATIN_DIGITS = '0123456789';
    var YEAR_PREFIX = '2011';
    var SERIAL_WIDTH = 6;

    function toLatinDigits(value) {
        var text = value === null || value === undefined ? '' : String(value);
        var out = '';
        for (var i = 0; i < text.length; i += 1) {
            var index = BANGLA_DIGITS.indexOf(text[i]);
            out += index === -1 ? text[i] : LATIN_DIGITS[index];
        }
        return out;
    }

    /* "2011 000 001" / "2011-000001" / "০০০০০১" / "1" -> "2011000001" */
    function normalizeNumber(value) {
        var compact = toLatinDigits(value).replace(/[\s\-().]/g, '');
        if (!compact || !/^\d+$/.test(compact)) {
            return '';
        }
        if (compact.indexOf(YEAR_PREFIX) === 0) {
            var tail = compact.slice(YEAR_PREFIX.length);
            if (!tail) {
                return '';
            }
            return YEAR_PREFIX + padSerial(parseInt(tail, 10));
        }
        if (compact.length <= SERIAL_WIDTH) {
            return YEAR_PREFIX + padSerial(parseInt(compact, 10));
        }
        return '';
    }

    function padSerial(serial) {
        var digits = String(serial);
        while (digits.length < SERIAL_WIDTH) {
            digits = '0' + digits;
        }
        return digits;
    }

    /* "2011000001" -> "2011 000 001" */
    function prettyNumber(value) {
        var compact = normalizeNumber(value);
        if (!compact) {
            return value ? String(value) : '';
        }
        var tail = compact.slice(YEAR_PREFIX.length);
        return YEAR_PREFIX + ' ' + tail.slice(0, 3) + ' ' + tail.slice(3);
    }

    /*
     * What to show for the typed text:
     *   { kind: 'picked', teacher }   one exact hit
     *   { kind: 'choose', matches }   several hits (e.g. just "1")
     *   { kind: 'empty' }             nothing typed yet
     *   { kind: 'unknown', query }    a full number nobody has
     *   { kind: 'searching', query }  a prefix of a number — keep typing
     */
    function resolveInput(rawValue, teachers) {
        var raw = rawValue === null || rawValue === undefined ? '' : String(rawValue).trim();
        if (!raw) {
            return { kind: 'empty' };
        }
        var list = Array.isArray(teachers) ? teachers : [];
        var digits = toLatinDigits(raw).replace(/[\s\-().]/g, '');
        if (/^\d+$/.test(digits)) {
            var normalized = normalizeNumber(digits);
            if (normalized) {
                var exact = list.filter(function (t) { return t.number === normalized; });
                if (exact.length === 1) {
                    return { kind: 'picked', teacher: exact[0] };
                }
                if (exact.length > 1) {
                    return { kind: 'choose', matches: exact };
                }
            }
            // Still being typed: show who could still match. A clerk who has
            // typed "2011 000 00" should see the shortlist, not "no match".
            if (digits.length >= 4) {
                var prefixed = list.filter(function (t) {
                    return String(t.number).indexOf(digits) === 0;
                });
                if (prefixed.length) {
                    return { kind: 'choose', matches: prefixed.slice(0, 8) };
                }
            }
            if (digits.length <= SERIAL_WIDTH) {
                var serial = padSerial(parseInt(digits, 10));
                var bySerial = list.filter(function (t) {
                    return String(t.number).slice(YEAR_PREFIX.length).indexOf(serial) === 0;
                });
                if (bySerial.length) {
                    return { kind: 'choose', matches: bySerial.slice(0, 8) };
                }
            }
            return { kind: 'unknown', query: raw };
        }
        var byName = list.filter(function (t) {
            return String(t.name || '').toLowerCase().indexOf(raw.toLowerCase()) !== -1;
        });
        if (byName.length === 1) {
            return { kind: 'picked', teacher: byName[0] };
        }
        if (byName.length > 1) {
            return { kind: 'choose', matches: byName.slice(0, 8) };
        }
        return { kind: 'searching', query: raw };
    }

    /* Sections the school uses for `admissionClass` (never null/undefined). */
    function sectionsFor(admissionClass, sectionsByClass) {
        var key = String(admissionClass === undefined || admissionClass === null ? '' : admissionClass).trim();
        if (!key || !sectionsByClass) {
            return [];
        }
        return (sectionsByClass[key] || []).slice();
    }

    /* Subject ids that belong to `admissionClass`, or null when unknown. */
    function subjectsFor(admissionClass, subjectsByClass) {
        var key = String(admissionClass === undefined || admissionClass === null ? '' : admissionClass).trim();
        if (!key || !subjectsByClass || !subjectsByClass[key]) {
            return null;
        }
        return subjectsByClass[key].slice();
    }

    /*
     * Rebuild a <select>'s options so only `allowedIds` survive; a selected
     * value that is no longer allowed is cleared and reported back.
     * Returns { kept, cleared }.
     */
    function filterSelectOptions(select, allowedIds, placeholderText) {
        if (!select || !select.options) {
            return { kept: 0, cleared: false };
        }
        var allowed = allowedIds === null ? null : allowedIds.map(String);
        var kept = [];
        var options = Array.prototype.slice.call(select.options || []);
        for (var i = 0; i < options.length; i += 1) {
            var option = options[i];
            var value = String(option.value);
            var keep = value === '' || allowed === null || allowed.indexOf(value) !== -1;
            if (keep) {
                kept.push(option);
            }
        }
        var cleared = false;
        var current = String(select.value || '');
        if (allowed !== null && current && allowed.indexOf(current) === -1) {
            cleared = true;
        }
        if (typeof select.replaceChildren === 'function') {
            select.replaceChildren.apply(select, kept);
        }
        if (cleared) {
            select.value = '';
        }
        if (placeholderText !== undefined && select.options && select.options.length) {
            select.options[0].textContent = current && !cleared ? select.options[0].textContent : placeholderText;
        }
        return { kept: kept.length, cleared: cleared };
    }

    /* Fill a <datalist> with the given values, skipping empties/duplicates. */
    function fillDatalist(datalist, values) {
        if (!datalist || typeof datalist.replaceChildren !== 'function') {
            return 0;
        }
        var doc = datalist.ownerDocument;
        var seen = {};
        var nodes = [];
        (values || []).forEach(function (value) {
            var text = value === undefined || value === null ? '' : String(value).trim();
            if (!text || seen[text]) {
                return;
            }
            seen[text] = true;
            var option = doc.createElement('option');
            option.value = text;
            nodes.push(option);
        });
        datalist.replaceChildren.apply(datalist, nodes);
        return nodes.length;
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
        var input = doc.getElementById('id_teacher_no_input');
        var hiddenEmployee = doc.getElementById('id_employee');
        var hiddenInstitution = doc.getElementById('id_institution');
        var results = doc.getElementById('teacher-results');
        var picked = doc.getElementById('teacher-picked');
        var stateLabel = doc.getElementById('teacher-search-state');
        var classInput = doc.getElementById('id_admission_class');
        var sectionInput = doc.getElementById('id_section');
        var sectionList = doc.getElementById('teacher-section-options');
        var subjectSelect = doc.getElementById('id_subject');
        var subjectHint = doc.getElementById('subject-hint');
        if (!subjectHint) {
            subjectHint = doc.createElement('div');
            subjectHint.setAttribute('data-created-by', 'teacher-picker');
        }
        var summary = doc.getElementById('assign-summary');
        var sessionInput = doc.getElementById('id_session');
        var sessionSummary = doc.getElementById('session-summary');
        var teachers = readJson(doc.getElementById('teacher-lookup-data'), []);
        var sectionsByClass = readJson(doc.getElementById('teacher-sections-data'), {});
        var subjectsByClass = readJson(doc.getElementById('teacher-subjects-data'), {});
        var subjectLabels = {};
        if (subjectSelect && subjectSelect.options) {
            Array.prototype.forEach.call(subjectSelect.options, function (option) {
                subjectLabels[String(option.value)] = option.textContent;
            });
        }
        var activeIndex = -1;
        var visibleMatches = [];

        if (!input) {
            // Not the assignment screen (or the markup changed): do nothing,
            // but keep the controller's shape so callers stay simple.
            var noop = function () {};
            return { attach: noop, refresh: noop, summary: noop };
        }

        function setState(text) {
            if (stateLabel) {
                stateLabel.textContent = text;
            }
        }

        function hideResults() {
            if (results) {
                results.hidden = true;
                if (typeof results.replaceChildren === 'function') {
                    results.replaceChildren();
                }
            }
            activeIndex = -1;
            visibleMatches = [];
        }

        function showPicked(teacher) {
            if (hiddenEmployee) {
                hiddenEmployee.value = teacher.id !== undefined ? String(teacher.id) : '';
            }
            if (hiddenInstitution) {
                hiddenInstitution.value = teacher.institution !== null && teacher.institution !== undefined
                    ? String(teacher.institution) : '';
            }
            if (picked) {
                var initials = doc.getElementById('teacher-picked-initials');
                var name = doc.getElementById('teacher-picked-name');
                var meta = doc.getElementById('teacher-picked-meta');
                var badge = doc.getElementById('teacher-picked-badge');
                if (initials) { initials.textContent = teacher.initials || ''; }
                if (name) { name.textContent = teacher.name || ''; }
                if (meta) {
                    meta.textContent = (teacher.pretty || teacher.number || '') +
                        (teacher.designation ? ' · ' + teacher.designation : '');
                }
                if (badge) {
                    badge.textContent = teacher.active ? 'Active' : (teacher.status || 'Inactive');
                    badge.className = teacher.active ? 'badge bg-success' : 'badge bg-secondary';
                }
                picked.hidden = false;
            }
            setState('found');
            hideResults();
            refreshDependentPickers();
        }

        function clearPicked() {
            if (hiddenEmployee) { hiddenEmployee.value = ''; }
            if (hiddenInstitution) { hiddenInstitution.value = ''; }
            if (picked) { picked.hidden = true; }
        }

        function renderMatches(matches) {
            if (!results) {
                return;
            }
            if (typeof results.replaceChildren !== 'function') {
                return;
            }
            var nodes = [];
            matches.forEach(function (teacher, index) {
                var row = doc.createElement('li');
                row.setAttribute('role', 'option');
                row.setAttribute('data-index', String(index));
                row.className = index === 0 ? 'active' : '';
                var num = doc.createElement('span');
                num.className = 'num';
                num.textContent = teacher.pretty || teacher.number;
                var who = doc.createElement('span');
                who.className = 'meta';
                who.textContent = teacher.name + (teacher.designation ? ' · ' + teacher.designation : '') +
                    (teacher.active ? '' : ' · ' + (teacher.status || 'Inactive'));
                row.appendChild(num);
                row.appendChild(who);
                nodes.push(row);
            });
            results.replaceChildren.apply(results, nodes);
            results.hidden = false;
            activeIndex = 0;
            visibleMatches = matches;
        }

        function renderEmpty(message) {
            if (!results || typeof results.replaceChildren !== 'function') {
                return;
            }
            var row = doc.createElement('li');
            row.className = 'empty';
            row.textContent = message;
            results.replaceChildren.apply(results, [row]);
            results.hidden = false;
            activeIndex = -1;
            visibleMatches = [];
        }

        function refreshDependentPickers() {
            var admissionClass = classInput ? String(classInput.value || '').trim() : '';
            var sections = sectionsFor(admissionClass, sectionsByClass);
            fillDatalist(sectionList, sections);
            if (sectionInput) {
                sectionInput.setAttribute(
                    'placeholder',
                    sections.length ? 'e.g. ' + sections.join(' / ') : 'e.g. A (optional)'
                );
            }
            var allowedSubjects = subjectsFor(admissionClass, subjectsByClass);
            var restricted = filterSelectOptions(subjectSelect, allowedSubjects, '— pick a subject —');
            if (subjectHint) {
                var note = restricted.cleared
                    // Say why the subject box went empty — otherwise it looks
                    // like the screen lost the choice on its own.
                    ? ' The previous subject is not taught in class ' + admissionClass +
                      ', so it was cleared.'
                    : '';
                if (restricted.cleared) {
                    // Remember why the box went empty; the hint below says so.
                    subjectHint.setAttribute('data-cleared', '1');
                }
                if (allowedSubjects === null) {
                    subjectHint.textContent = 'Pick a class to see its subjects.';
                } else if (!allowedSubjects.length) {
                    subjectHint.textContent = 'No curriculum has been set up for this class yet.';
                } else {
                    subjectHint.textContent = allowedSubjects.length + ' subjects in the class ' +
                        admissionClass + ' curriculum.' + note;
                }
            }
            updateSummary();
        }

        function updateSummary() {
            if (!summary) {
                return;
            }
            var parts = [];
            if (classInput && String(classInput.value || '').trim()) {
                parts.push('Class ' + String(classInput.value).trim());
            }
            if (sectionInput && String(sectionInput.value || '').trim()) {
                parts.push('Section ' + String(sectionInput.value).trim());
            }
            if (subjectSelect && subjectSelect.value) {
                parts.push(subjectLabels[String(subjectSelect.value)] || '');
            }
            summary.textContent = parts.filter(Boolean).join(' · ');
            if (sessionInput && sessionSummary) {
                sessionSummary.textContent = sessionInput.value;
            }
        }

        function commit(teacher) {
            input.value = teacher.pretty || teacher.number;
            showPicked(teacher);
        }

        function onInput() {
            var result = resolveInput(input.value, teachers);
            if (result.kind === 'empty') {
                clearPicked();
                setState('teachers only');
                hideResults();
                return;
            }
            if (result.kind === 'picked') {
                showPicked(result.teacher);
                if (result.teacher.pretty && result.teacher.pretty !== input.value) {
                    input.value = result.teacher.pretty;
                }
                return;
            }
            clearPicked();
            if (result.kind === 'choose') {
                setState('choose below');
                renderMatches(result.matches);
                return;
            }
            hideResults();
            if (result.kind === 'unknown') {
                setState('no match');
                renderEmpty('No teacher has this number. Numbers start with 2011.');
                return;
            }
            setState('keep typing');
        }

        function onKeyDown(event) {
            var key = event.key;
            if (!visibleMatches.length) {
                return;
            }
            if (key === 'ArrowDown' || key === 'ArrowUp') {
                event.preventDefault();
                activeIndex = key === 'ArrowDown'
                    ? Math.min(activeIndex + 1, visibleMatches.length - 1)
                    : Math.max(activeIndex - 1, 0);
                if (results && results.children) {
                    Array.prototype.forEach.call(results.children, function (child, index) {
                        child.className = index === activeIndex ? 'active' : '';
                    });
                }
                return;
            }
            if (key === 'Enter') {
                event.preventDefault();
                var chosen = visibleMatches[activeIndex] || visibleMatches[0];
                if (chosen) {
                    commit(chosen);
                }
                return;
            }
            if (key === 'Escape') {
                hideResults();
            }
        }

        function onResultsClick(event) {
            var target = event.target;
            while (target && target !== results) {
                if (target.getAttribute && target.getAttribute('data-index') !== null) {
                    var index = parseInt(target.getAttribute('data-index'), 10);
                    if (visibleMatches[index]) {
                        commit(visibleMatches[index]);
                    }
                    return;
                }
                target = target.parentElement;
            }
        }

        function attach() {
            // Idempotent: a page that loads the script twice (or a test that
            // builds its own controller) must not stack duplicate listeners,
            // which would run the refresh twice and drop the "why it cleared"
            // note on the second pass.
            if (input.getAttribute('data-teacher-picker') === 'attached') {
                return;
            }
            input.setAttribute('data-teacher-picker', 'attached');
            input.addEventListener('input', onInput);
            input.addEventListener('keydown', onKeyDown);
            input.addEventListener('blur', function () {
                // Clicking a match blurs the input first; let the click land.
                setTimeout(hideResults, 150);
            });
            if (results) {
                results.addEventListener('click', onResultsClick);
            }
            if (classInput) {
                classInput.addEventListener('input', refreshDependentPickers);
                classInput.addEventListener('change', refreshDependentPickers);
            }
            if (sectionInput) {
                sectionInput.addEventListener('change', updateSummary);
            }
            if (subjectSelect) {
                subjectSelect.addEventListener('change', updateSummary);
            }
            if (sessionInput) {
                sessionInput.addEventListener('change', updateSummary);
            }
            // Edit screen: land on the saved values, already narrowed.
            var current = resolveInput(input.value, teachers);
            if (current.kind === 'picked') {
                showPicked(current.teacher);
            } else {
                refreshDependentPickers();
            }
            updateSummary();
        }

        return {
            attach: attach,
            refresh: refreshDependentPickers,
            summary: updateSummary,
        };
    }

    globalScope.TeacherNumberPicker = {
        toLatinDigits: toLatinDigits,
        normalizeNumber: normalizeNumber,
        prettyNumber: prettyNumber,
        resolveInput: resolveInput,
        sectionsFor: sectionsFor,
        subjectsFor: subjectsFor,
        filterSelectOptions: filterSelectOptions,
        fillDatalist: fillDatalist,
        createController: createController,
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
