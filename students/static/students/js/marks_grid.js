/*
 * marks_grid.js
 *
 * The Result Grid page is a thin input surface over ExamMark: every box on
 * the sheet is one (student, subject, part) mark. This file only moves boxes
 * to the server and paints the answer back:
 *
 *   - typing in a box queues a change; the queue is flushed after a short
 *     pause, so a whole column can be typed without a request per keystroke;
 *   - the POST goes to the page's own save URL as JSON, with the CSRF token
 *     from the page, and the server re-runs the real result calculation and
 *     sends every row back;
 *   - the right-hand Subject total / Total / GPA / Grade / F/S / A+ / Place
 *     cells are then replaced with the server's numbers — the page never
 *     computes a grade itself, so it cannot disagree with the Result Sheet.
 *
 * A value above the box's maximum is refused locally and shows red: marks
 * above a part total are exactly what the per-subject page rejects too.
 */
(function () {
    'use strict';

    var BANGLA_DIGITS = '০১২৩৪৫৬৭৮৯';

    function toEnglishDigits(value) {
        return String(value == null ? '' : value).replace(/[০-৯]/g, function (digit) {
            return String(BANGLA_DIGITS.indexOf(digit));
        });
    }

    function cleanValue(value) {
        var text = toEnglishDigits(value).replace(/[^0-9.]/g, '');
        // Keep a single decimal point.
        var firstDot = text.indexOf('.');
        if (firstDot !== -1) {
            text = text.slice(0, firstDot + 1) + text.slice(firstDot + 1).replace(/\./g, '');
        }
        return text;
    }

    function isNumber(value) {
        return value !== '' && !isNaN(Number(value));
    }

    function create(config) {
        var table = document.getElementById('marks-grid-table');
        if (!table) return null;

        var statusBox = document.getElementById('mg-status');
        var timer = null;
        var pending = new Map();
        var inFlight = false;
        var lastError = '';

        function setStatus(text, tone) {
            if (!statusBox) return;
            statusBox.textContent = text || '';
            statusBox.className = 'mg-status' + (tone ? ' is-' + tone : '');
        }

        function queue(input) {
            var key = input.dataset.student + '|' + input.dataset.subject + '|' + input.dataset.part;
            pending.set(key, {
                student: Number(input.dataset.student),
                subject: Number(input.dataset.subject),
                part: input.dataset.part,
                value: input.value
            });
            setStatus('না-সেভ হওয়া পরিবর্তন আছে…', 'pending');
            if (timer) clearTimeout(timer);
            timer = setTimeout(flush, 700);
        }

        function flush() {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
            if (inFlight || pending.size === 0) return;
            var changes = Array.from(pending.values());
            pending.clear();
            inFlight = true;
            setStatus('সেভ হচ্ছে…', 'pending');

            fetch(config.saveUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': config.csrfToken
                },
                credentials: 'same-origin',
                body: JSON.stringify({ changes: changes })
            }).then(function (response) {
                return response.json().catch(function () {
                    return { ok: false, errors: ['সার্ভার থেকে সঠিক উত্তর আসেনি।'] };
                }).then(function (data) {
                    return { data: data, status: response.status };
                });
            }).then(function (result) {
                inFlight = false;
                var data = result.data || {};
                if (result.status === 403 && data.locked) {
                    // Published result, locked again (or never unlocked here):
                    // stop quietly and say so instead of retrying forever.
                    pending.clear();
                    setStatus(data.message || 'ফল প্রকাশিত — নম্বর লক করা আছে।', 'error');
                    disableInputs();
                    return;
                }
                if (data.rows) applyRows(data.rows);
                if (data.summary) applySummary(data.summary);
                if (data.errors && data.errors.length) {
                    lastError = data.errors[0];
                    setStatus('⚠ ' + data.errors[0], 'error');
                } else {
                    lastError = '';
                    var stamp = new Date().toLocaleTimeString();
                    setStatus('✔ সেভ হয়েছে (' + stamp + ')', 'ok');
                }
                if (pending.size) {
                    timer = setTimeout(flush, 200);
                }
            }).catch(function () {
                inFlight = false;
                setStatus('⚠ নেটওয়ার্ক সমস্যা — আবার চেষ্টা করুন।', 'error');
            });
        }

        function disableInputs() {
            table.querySelectorAll('input.mg-input').forEach(function (input) {
                input.readOnly = true;
                input.classList.add('is-locked');
            });
            // Highlight the row being typed in, so the name stays in view on a
        // sheet that is wider than the screen.
        table.addEventListener('focusin', function (event) {
            var input = event.target;
            if (!input.classList || !input.classList.contains('mg-input')) return;
            var row = input.closest('tr');
            table.querySelectorAll('tr.mg-current').forEach(function (element) {
                element.classList.remove('mg-current');
            });
            if (row) row.classList.add('mg-current');
        });

        var saveAll = document.getElementById('mg-save-all');
            if (saveAll) saveAll.disabled = true;
        }

        function gradeClass(grade, cell) {
            if (cell.absent) return 'is-absent';
            if (cell.failed) return 'is-fail';
            if (grade === 'A+') return 'is-aplus';
            return '';
        }

        function renderDerived(cellElement, cell) {
            if (!cellElement) return;
            if (!cell.applicable) {
                cellElement.textContent = '·';
                cellElement.className = 'mg-derived mg-na';
                return;
            }
            cellElement.className = 'mg-derived ' + gradeClass(cell.grade, cell);
            if (cell.absent) {
                cellElement.textContent = '—';
                return;
            }
            cellElement.innerHTML = '';
            var number = document.createElement('span');
            number.className = 'mg-der-num';
            number.textContent = cell.obtained == null ? '' : String(cell.obtained);
            cellElement.appendChild(number);
            if (cell.grade) {
                var badge = document.createElement('span');
                badge.className = 'mg-grade';
                badge.textContent = cell.grade;
                cellElement.appendChild(badge);
            }
        }

        function renderOverall(element, key, row) {
            if (!element) return;
            if (key === 'fails') {
                element.textContent = String(row.fails);
            } else if (key === 'a_plus') {
                element.textContent = String(row.a_plus);
            } else if (key === 'grade') {
                element.textContent = row.grade || '—';
                if (row.golden) {
                    var star = document.createElement('span');
                    star.className = 'mg-golden';
                    star.title = 'Golden A+ — সব বিষয়ে A+';
                    star.textContent = '★';
                    element.appendChild(document.createTextNode(' '));
                    element.appendChild(star);
                }
                element.className = 'mg-grade-cell' + (
                    row.status === 'Fail' ? ' is-fail' : (row.grade === 'A+' ? ' is-aplus' : '')
                );
            } else if (key === 'gpa') {
                element.textContent = row.gpa || '';
                element.className = 'mg-gpa' + (row.status === 'Fail' ? ' is-fail' : '');
            } else if (key === 'total') {
                element.textContent = row.total == null ? '' : String(row.total);
            } else if (key === 'position') {
                element.textContent = row.position || '—';
            }
        }

        function applySummary(summary) {
            if (!summary) return;
            Object.keys(summary).forEach(function (key) {
                var chip = document.querySelector('[data-summary="' + key + '"]');
                if (chip) chip.textContent = String(summary[key]);
            });
        }

        function applyRows(rows) {
            rows.forEach(function (row) {
                (row.cells || []).forEach(function (cell) {
                    var derived = table.querySelector(
                        '[data-grid-cell="' + row.student + '-' + cell.subject + '"]'
                    );
                    renderDerived(derived, cell);
                    if (!cell.values) return;
                    Object.keys(cell.values).forEach(function (part) {
                        var input = table.querySelector(
                            'input.mg-input[data-student="' + row.student + '"]' +
                            '[data-subject="' + cell.subject + '"]' +
                            '[data-part="' + part + '"]'
                        );
                        if (!input) return;
                        var fresh = cell.values[part];
                        // Never overwrite the box the teacher is typing in.
                        if (document.activeElement !== input) {
                            input.value = fresh == null ? '' : fresh;
                        }
                        input.classList.toggle('is-bad', !boxIsValid(input));
                    });
                });
                ['total', 'gpa', 'grade', 'fails', 'a_plus', 'position'].forEach(function (key) {
                    var element = table.querySelector(
                        '[data-grid-overall="' + key + '"][data-student="' + row.student + '"]'
                    );
                    renderOverall(element, key, row);
                });
            });
        }

        function boxIsValid(input) {
            var raw = input.value.trim();
            if (raw === '') return true;
            if (!isNumber(raw)) return false;
            var max = Number(input.dataset.max);
            if (!isNaN(max) && Number(raw) > max) return false;
            return true;
        }

        table.addEventListener('input', function (event) {
            var input = event.target;
            if (!input.classList || !input.classList.contains('mg-input')) return;
            var cleaned = cleanValue(input.value);
            if (cleaned !== input.value) input.value = cleaned;
            var valid = boxIsValid(input);
            input.classList.toggle('is-bad', !valid);
            if (!valid) {
                setStatus(
                    '⚠ ' + (input.dataset.label || 'নম্বর') + ' ঘরের সর্বোচ্চ ' +
                    input.dataset.max + ' — মানটি সেভ হবে না।',
                    'error'
                );
                var key = input.dataset.student + '|' + input.dataset.subject + '|' + input.dataset.part;
                pending.delete(key);
                return;
            }
            queue(input);
        });

        table.addEventListener('keydown', function (event) {
            var input = event.target;
            if (!input.classList || !input.classList.contains('mg-input')) return;
            var step = 0;
            if (event.key === 'Enter' || event.key === 'ArrowDown') step = 1;
            else if (event.key === 'ArrowUp') step = -1;
            else return;
            var inputs = Array.prototype.slice.call(
                table.querySelectorAll(
                    'input.mg-input[data-subject="' + input.dataset.subject + '"]' +
                    '[data-part="' + input.dataset.part + '"]'
                )
            );
            var index = inputs.indexOf(input);
            var next = inputs[index + step];
            if (next) {
                event.preventDefault();
                next.focus();
                next.select();
            }
        });

        var saveAll = document.getElementById('mg-save-all');
        if (saveAll) {
            saveAll.addEventListener('click', function () {
                if (timer) {
                    clearTimeout(timer);
                    timer = null;
                }
                flush();
            });
        }

        window.addEventListener('beforeunload', function (event) {
            if (pending.size) {
                flush();
                event.preventDefault();
                event.returnValue = '';
            }
        });

        return {
            flush: flush, queue: queue, applyRows: applyRows,
            applySummary: applySummary, setStatus: setStatus
        };
    }

    window.MarksGrid = { create: create, cleanValue: cleanValue, toEnglishDigits: toEnglishDigits };

    document.addEventListener('DOMContentLoaded', function () {
        var configElement = document.getElementById('marks-grid-config');
        if (!configElement) return;
        var config;
        try {
            config = JSON.parse(configElement.textContent);
        } catch (error) {
            return;
        }
        window.MarksGrid.controller = create(config);
    });
})();
