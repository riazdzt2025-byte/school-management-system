/*
 * student_row_actions.js
 *
 * Keeps the per-row action buttons on the student list table (Details, Edit,
 * ID Card, Marksheet and the "More actions" dropdown) disabled by default and
 * enabled only while that row's checkbox is ticked — the same checkbox-tracking
 * pattern the Bulk Update / Auto Registration / Archive Selected buttons use.
 *
 * The server renders the locked state (`.student-actions-locked` on the action
 * bar, `aria-disabled="true"` on the buttons, `disabled` on the dropdown
 * toggle) so the buttons are already blocked before any script runs; this file
 * only keeps that state in sync with the checkboxes afterwards:
 *
 *   - a row's checkbox  change -> that row's buttons lock/unlock
 *   - a click on a locked row's button is cancelled (defence in depth in case
 *     the stylesheet or the ARIA state is unavailable, e.g. keyboard activation)
 *
 * Exposed for the automated tests (node --test students/js/):
 *   window.StudentRowActions.isRowLocked(checkbox)
 *   window.StudentRowActions.applyLockedState(row, locked)
 *   window.StudentRowActions.createController(document)
 */
(function (globalScope) {
    'use strict';

    var ROW_CHECKBOX_SELECTOR = '.row-checkbox';
    var ACTION_BAR_SELECTOR = '.student-actions-bar';
    var ACTION_BUTTON_SELECTOR = '.student-action';
    var LOCKED_CLASS = 'student-actions-locked';

    function isRowLocked(checkbox) {
        return !checkbox || checkbox.checked !== true;
    }

    function applyLockedState(row, locked) {
        if (!row) {
            return;
        }
        var bar = row.querySelector(ACTION_BAR_SELECTOR);
        if (bar && bar.classList) {
            bar.classList.toggle(LOCKED_CLASS, locked);
        }
        var buttons = row.querySelectorAll(ACTION_BUTTON_SELECTOR);
        for (var i = 0; i < buttons.length; i++) {
            var button = buttons[i];
            button.setAttribute('aria-disabled', locked ? 'true' : 'false');
            if (button.tagName === 'BUTTON') {
                button.disabled = locked;
            }
        }
    }

    function createController(doc) {
        function rowOf(element) {
            return element && element.closest ? element.closest('tr') : null;
        }

        function syncRow(row) {
            if (!row) {
                return;
            }
            applyLockedState(row, isRowLocked(row.querySelector(ROW_CHECKBOX_SELECTOR)));
        }

        function onChange(event) {
            syncRow(rowOf(event && event.target));
        }

        function guardClick(event) {
            var target = event && event.target;
            var button = target && target.closest ? target.closest(ACTION_BUTTON_SELECTOR) : null;
            if (!button) {
                return;
            }
            var row = rowOf(button);
            var checkbox = row ? row.querySelector(ROW_CHECKBOX_SELECTOR) : null;
            if (isRowLocked(checkbox)) {
                if (event.preventDefault) {
                    event.preventDefault();
                }
                if (event.stopPropagation) {
                    event.stopPropagation();
                }
            }
        }

        function attach() {
            var rows = doc.querySelectorAll('tr');
            for (var i = 0; i < rows.length; i++) {
                var row = rows[i];
                var checkbox = row.querySelector(ROW_CHECKBOX_SELECTOR);
                if (!checkbox || !checkbox.addEventListener) {
                    continue;
                }
                syncRow(row);
                checkbox.addEventListener('change', onChange);
            }
            doc.addEventListener('click', guardClick, true);
        }

        return {
            attach: attach,
            syncRow: syncRow,
            isRowLocked: isRowLocked,
            applyLockedState: applyLockedState,
            selectors: {
                rowCheckbox: ROW_CHECKBOX_SELECTOR,
                actionBar: ACTION_BAR_SELECTOR,
                actionButton: ACTION_BUTTON_SELECTOR,
                lockedClass: LOCKED_CLASS
            }
        };
    }

    if (globalScope) {
        globalScope.StudentRowActions = {
            isRowLocked: isRowLocked,
            applyLockedState: applyLockedState,
            createController: createController,
            ROW_CHECKBOX_SELECTOR: ROW_CHECKBOX_SELECTOR,
            ACTION_BAR_SELECTOR: ACTION_BAR_SELECTOR,
            ACTION_BUTTON_SELECTOR: ACTION_BUTTON_SELECTOR,
            LOCKED_CLASS: LOCKED_CLASS
        };
    }

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
