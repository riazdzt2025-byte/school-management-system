"""Tests for developer branding: developer name and copyright holder.

Defaults live in settings (DEVELOPER_NAME, COPYRIGHT_HOLDER). A single
SiteBranding row, editable by a super admin in the Django admin, overrides
them. Templates read both through the context processor, and no template may
carry a hard-coded or old developer name.
"""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import SiteBranding


def _superuser(username='brand-admin'):
    return get_user_model().objects.create_user(
        username=username, password='password', is_superuser=True, is_staff=True,
    )


class DeveloperBrandingDefaultsTests(TestCase):
    def test_defaults_are_defined_in_settings(self):
        self.assertEqual(settings.DEVELOPER_NAME, 'riOn Dev')
        self.assertEqual(settings.COPYRIGHT_HOLDER, 'PKFSC')

    def test_migration_creates_the_single_row_with_defaults(self):
        self.assertEqual(SiteBranding.objects.count(), 1)
        row = SiteBranding.objects.get()
        self.assertEqual(row.pk, 1)
        self.assertEqual(row.developer_name, 'riOn Dev')
        self.assertEqual(row.copyright_holder, 'PKFSC')

    def test_login_page_shows_developer_credit(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Developed by')
        self.assertContains(response, 'riOn Dev')

    def test_dashboard_footer_shows_developer_credit(self):
        self.client.force_login(_superuser())
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Developed by')
        self.assertContains(response, 'riOn Dev')

    def test_no_template_contains_old_developer_name(self):
        base = Path(settings.BASE_DIR)
        offenders = []
        for folder in (base / 'students' / 'templates', base / 'school_system' / 'templates'):
            for path in folder.rglob('*.html'):
                if 'itoxide' in path.read_text(encoding='utf-8').lower():
                    offenders.append(str(path.relative_to(base)))
        self.assertEqual(offenders, [])

    def test_result_sheet_footer_uses_the_branding_values(self):
        path = Path(settings.BASE_DIR) / 'students' / 'templates' / 'students' / 'result_sheet.html'
        source = path.read_text(encoding='utf-8')
        self.assertIn('Software by {{ DEVELOPER_NAME }}', source)
        self.assertIn('{{ COPYRIGHT_HOLDER }}', source)
        self.assertIn('{% now "Y" %}', source)


class SiteBrandingEditTests(TestCase):
    def test_changing_the_row_changes_the_pages(self):
        SiteBranding.objects.update_or_create(
            pk=1, defaults={'developer_name': 'Acme Web', 'copyright_holder': 'Acme School'},
        )
        response = self.client.get(reverse('login'))
        self.assertContains(response, 'Acme Web')
        self.assertNotContains(response, 'riOn Dev')

    def test_only_one_row_can_exist(self):
        SiteBranding(developer_name='Second', copyright_holder='Second').save()
        self.assertEqual(SiteBranding.objects.count(), 1)
        self.assertEqual(SiteBranding.objects.get().developer_name, 'Second')

    def test_blank_values_fall_back_to_settings(self):
        SiteBranding.objects.filter(pk=1).update(developer_name='', copyright_holder='')
        self.assertEqual(SiteBranding.current(), ('riOn Dev', 'PKFSC'))

    def test_super_admin_can_open_the_change_page(self):
        self.client.force_login(_superuser())
        response = self.client.get(reverse('admin:students_sitebranding_change', args=[1]))
        self.assertEqual(response.status_code, 200)

    def test_admin_cannot_add_a_second_row_or_delete_the_row(self):
        self.client.force_login(_superuser())
        self.assertEqual(self.client.get(reverse('admin:students_sitebranding_add')).status_code, 403)
        self.assertEqual(
            self.client.get(reverse('admin:students_sitebranding_delete', args=[1])).status_code, 403,
        )

    def test_normal_user_cannot_open_the_admin_page(self):
        user = get_user_model().objects.create_user(username='plain', password='password')
        self.client.force_login(user)
        response = self.client.get(reverse('admin:students_sitebranding_change', args=[1]))
        self.assertIn(response.status_code, (302, 403))
