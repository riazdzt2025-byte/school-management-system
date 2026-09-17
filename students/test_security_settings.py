"""Deployment settings guards (SEC session-02, task 1 audit).

The settings module already refuses to boot with the fallback SECRET_KEY when
DEBUG=False. These tests lock the companion rule: DEBUG=False with the
wildcard ALLOWED_HOSTS fallback (the dev default) must surface as a deploy
Error so the build gate fails before the app ships with Host-header
validation disabled.
"""
from django.core.checks import Tags, run_checks
from django.test import SimpleTestCase, override_settings

from .checks import check_production_allowed_hosts_explicit


class ProductionAllowedHostsCheckTests(SimpleTestCase):
    """students.E016 — wildcard ALLOWED_HOSTS with DEBUG=False is an Error."""

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['*'])
    def test_wildcard_hosts_flagged_as_error(self):
        issues = list(check_production_allowed_hosts_explicit())
        self.assertEqual([issue.id for issue in issues], ['students.E016'])

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['school.example.com', 'myschool.edu.bd'])
    def test_explicit_hosts_pass(self):
        self.assertEqual(list(check_production_allowed_hosts_explicit()), [])

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['.onrender.com'])
    def test_subdomain_wildcard_is_not_the_catch_all(self):
        # Django's own documented pattern: a leading dot matches subdomains,
        # which is an explicit host choice, not the catch-all '*'.
        self.assertEqual(list(check_production_allowed_hosts_explicit()), [])

    @override_settings(DEBUG=True, ALLOWED_HOSTS=['*'])
    def test_development_wildcard_is_fine(self):
        # DEBUG=True keeps the previous dev/preview behaviour entirely.
        self.assertEqual(list(check_production_allowed_hosts_explicit()), [])

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['*'])
    def test_error_reaches_the_security_system_checks(self):
        ids = {
            issue.id
            for issue in run_checks(tags=[Tags.security], include_deployment_checks=True)
        }
        self.assertIn('students.E016', ids)
