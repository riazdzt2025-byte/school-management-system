/*
 * result_cell_shortcut.js
 *
 * E8 — Ctrl/Cmd+Click on a cell of a published result opens the marks-entry
 * page for that subject in a NEW TAB, so an office user can correct a mark
 * without losing the register they were reading.
 *
 * The server does the deciding, this file only reacts to it:
 *
 *   - each result cell carries data-subject-pk (its own subject; on the single
 *     Religion column that is the paper the student actually sits, never the
 *     column) and data-group, inside a container carrying data-enter-marks-base
 *     — this exam's marks-entry URL with the subject slot left open;
 *   - a cell that the user has no permission to correct is rendered with
 *     data-shortcut-disabled="true" and its tooltip says "Ask Exam dept", so
 *     there is nothing for this script to do;
 *   - the Full Rank List has no subject columns, so its rows carry a ready-made
 *     data-shortcut-url to this exam's marks entry instead.
 *
 * A plain click is deliberately ignored: the result sheet is printed straight
 * from this page and must not navigate away, and no link is rendered in the
 * cell, so the printout stays clean.
 *
 * Exposed for the automated tests (node --test students/js/):
 *   window.ResultCellShortcut.buildEnterMarksUrl(base, subjectPk, group)
 *   window.ResultCellShortcut.urlFor(element)
 *   window.ResultCellShortcut.isDisabled(element)
 *   window.ResultCellShortcut.createController(document, openFn)
 */
(function (globalScope) {
    'use strict';

    var SUBJECT_ATTRIBUTE = 'data-subject-pk';
    var GROUP_ATTRIBUTE = 'data-group';
    var URL_ATTRIBUTE = 'data-shortcut-url';
    var BASE_ATTRIBUTE = 'data-enter-marks-base';
    var DISABLED_ATTRIBUTE = 'data-shortcut-disabled';
    var NEW_TAB_FEATURES = 'noopener';

    function attribute(node, name) {
        if (!node || typeof node.getAttribute !== 'function') return null;
        var value = node.getAttribute(name);
        return value === undefined ? null : value;
    }

    function parentOf(node) {
        return node.parentNode || node.parent || null;
    }

    /* Walk up from the clicked node. Attributes are read directly instead of
       through closest()/matches() so the behaviour is identical in a browser
       and in the dependency-free DOM stub the Node tests use. */
    function ancestorWith(node, name) {
        var current = node;
        while (current) {
            var value = attribute(current, name);
            if (value !== null && value !== '') return value;
            current = parentOf(current);
        }
        return null;
    }

    function findShortcutTarget(node) {
        var current = node;
        while (current) {
            if (attribute(current, SUBJECT_ATTRIBUTE) || attribute(current, URL_ATTRIBUTE)) {
                return current;
            }
            current = parentOf(current);
        }
        return null;
    }

    function isDisabled(node) {
        var flag = attribute(node, DISABLED_ATTRIBUTE);
        return flag === 'true' || flag === '1' || flag === '';
    }

    /* <base>/<subjectPk>/ and, when the exam was narrowed to a group, ?group=.
       The group always travels so the correction page shows the same students
       the register was showing. */
    function buildEnterMarksUrl(baseUrl, subjectPk, group) {
        if (!baseUrl) return '';
        if (subjectPk === null || subjectPk === undefined || subjectPk === '') return '';
        var url = String(baseUrl).replace(/\/+$/, '') + '/' + encodeURIComponent(subjectPk) + '/';
        if (group) url += '?group=' + encodeURIComponent(group);
        return url;
    }

    function urlFor(node) {
        var direct = attribute(node, URL_ATTRIBUTE);
        if (direct) return direct;
        var subjectPk = attribute(node, SUBJECT_ATTRIBUTE);
        if (!subjectPk) return '';
        var base = ancestorWith(node, BASE_ATTRIBUTE);
        if (!base) return '';
        return buildEnterMarksUrl(base, subjectPk, attribute(node, GROUP_ATTRIBUTE));
    }

    function defaultOpen(url) {
        if (typeof globalScope.open !== 'function') return null;
        return globalScope.open(url, '_blank', NEW_TAB_FEATURES);
    }

    function createController(doc, openFn) {
        var opener = typeof openFn === 'function' ? openFn : defaultOpen;

        function handleClick(event) {
            /* Only Ctrl (Windows/Linux) or Cmd (macOS). A plain click does
               nothing on purpose — see the note at the top of this file. */
            if (!event || !(event.ctrlKey || event.metaKey)) return false;
            var cell = findShortcutTarget(event.target);
            if (!cell) return false;
            /* No permission to enter marks: the tooltip already says why. */
            if (isDisabled(cell)) return false;
            var url = urlFor(cell);
            if (!url) return false;
            if (typeof event.preventDefault === 'function') event.preventDefault();
            opener(url);
            return true;
        }

        return {
            attach: function () {
                if (doc && typeof doc.addEventListener === 'function') {
                    doc.addEventListener('click', handleClick);
                }
            },
            handleClick: handleClick
        };
    }

    globalScope.ResultCellShortcut = {
        buildEnterMarksUrl: buildEnterMarksUrl,
        findShortcutTarget: findShortcutTarget,
        urlFor: urlFor,
        isDisabled: isDisabled,
        createController: createController,
        SUBJECT_ATTRIBUTE: SUBJECT_ATTRIBUTE,
        GROUP_ATTRIBUTE: GROUP_ATTRIBUTE,
        URL_ATTRIBUTE: URL_ATTRIBUTE,
        BASE_ATTRIBUTE: BASE_ATTRIBUTE,
        DISABLED_ATTRIBUTE: DISABLED_ATTRIBUTE
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
