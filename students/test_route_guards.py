"""Route guard matrix (DB-03).

Every named route of the project is requested over real HTTP as an anonymous
visitor. Only the reviewed public routes below may answer 200; every other
route must refuse (redirect to login, 403 or 405). A new route that forgets
its guard therefore fails this test instead of silently going live.

The scoping helpers treat a non-admin user without an InstitutionAccess row as
unrestricted, so the login gate is the control that keeps such users out. It
is pinned here as well.
"""
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import get_resolver, reverse
from django.urls.resolvers import URLResolver

from .models import Institution, InstitutionAccess

# Reviewed on 2026-09-21. Each one is public on purpose:
#   login                      - the login page itself
#   public_admission_apply     - the public admission form (rate limited)
#   admission_dropdown_options - JSON for that form: group names and section
#                                letters only, no personal data
PUBLIC_ROUTE_NAMES = {'login', 'public_admission_apply', 'admission_dropdown_options'}

SKIPPED_PREFIXES = ('admin/', 'media', 'static')
REFUSED = {302, 403, 405}


def _walk(patterns, prefix=''):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _walk(pattern.url_patterns, prefix + str(pattern.pattern))
        else:
            yield prefix + str(pattern.pattern), pattern.name


def _fill(route):
    route = route.lstrip('^').rstrip('$')
    route = re.sub(r'<uuid:\w+>', '00000000-0000-0000-0000-000000000000', route)
    route = re.sub(r'<(?:str|slug|path):\w+>', 'x', route)
    route = re.sub(r'<\w+:\w+>', '1', route)
    route = re.sub(r'<\w+>', '1', route)
    return '/' + route


def _routes():
    routes = []
    for route, name in _walk(get_resolver().url_patterns):
        if route.lstrip('^').startswith(SKIPPED_PREFIXES):
            continue
        routes.append((_fill(route), name))
    return routes


class RouteGuardMatrixTests(TestCase):
    def test_walker_covers_the_whole_url_config(self):
        routes = _routes()
        self.assertGreater(len(routes), 90)
        unresolved = [url for url, _ in routes if '(' in url or '<' in url]
        self.assertEqual(unresolved, [])

    def test_public_allowlist_has_no_stale_names(self):
        names = {name for _, name in _routes()}
        self.assertEqual(PUBLIC_ROUTE_NAMES - names, set())

    def test_anonymous_visitor_is_refused_everywhere_except_public_routes(self):
        login_url = reverse('login')
        leaks = []
        for url, name in _routes():
            if name in PUBLIC_ROUTE_NAMES:
                continue
            for method in ('get', 'post'):
                response = getattr(self.client, method)(url)
                if response.status_code not in REFUSED:
                    leaks.append((method.upper(), url, name, response.status_code))
                elif response.status_code == 302 and login_url not in response['Location']:
                    leaks.append((method.upper(), url, name, response['Location']))
        self.assertEqual(leaks, [])

    def test_public_routes_stay_public_for_anonymous_visitors(self):
        for name in ('login', 'public_admission_apply'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


class LoginGateTests(TestCase):
    """Only staff/superusers or users with a matching active access row get in."""

    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name='Gate Institution', classes='1,2')
        cls.user_model = get_user_model()

    def _login(self, username, department='Office'):
        return self.client.post(reverse('login'), {
            'username': username,
            'password': 'password',
            'institution_id': self.institution.pk,
            'department': department,
        })

    def _is_logged_in(self):
        return '_auth_user_id' in self.client.session

    def test_user_without_any_access_row_cannot_log_in(self):
        self.user_model.objects.create_user(username='no-access', password='password')
        response = self._login('no-access')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._is_logged_in())

    def test_inactive_access_row_cannot_log_in(self):
        user = self.user_model.objects.create_user(username='inactive', password='password')
        InstitutionAccess.objects.create(
            user=user, institution=self.institution, department='Office', is_active=False,
        )
        self._login('inactive')
        self.assertFalse(self._is_logged_in())

    def test_access_row_for_another_department_cannot_log_in(self):
        user = self.user_model.objects.create_user(username='other-dept', password='password')
        InstitutionAccess.objects.create(
            user=user, institution=self.institution, department='Exam', is_active=True,
        )
        self._login('other-dept', department='Accounts')
        self.assertFalse(self._is_logged_in())

    def test_matching_active_access_row_can_log_in(self):
        user = self.user_model.objects.create_user(username='clerk', password='password')
        InstitutionAccess.objects.create(
            user=user, institution=self.institution, department='Office', is_active=True,
        )
        response = self._login('clerk')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self._is_logged_in())
