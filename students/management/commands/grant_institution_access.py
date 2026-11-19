"""
python manage.py grant_institution_access                                  # show who can log in
python manage.py grant_institution_access --list-users                     # every user and their access
python manage.py grant_institution_access office_rahim --institution 1     # grant, all departments
python manage.py grant_institution_access office_rahim --institution "Professor Kazi Faruky Kallan Trust" --department Office
python manage.py grant_institution_access office_rahim --institution 1 --department Office --revoke

Grants (or revokes) the InstitutionAccess rows the login screen needs.

Why this exists: a user who is not a superuser/staff can only log in against an
institution + department pair they hold an active InstitutionAccess row for.
Without a row the login is rejected with "Invalid username, password, or
institution access", which reads like a wrong password and sends people
hunting in the wrong place.

The department groups (Office / Exam / Accounts permissions) are created here
too, so a freshly granted user can actually open the pages their department
owns instead of hitting 403.

A teacher does not need this command: once the login is linked to an Employee
row in the HR screen, signing in with the Teacher department grants itself. Use
``--department Teacher`` only to force the row for a specific account.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from students.models import Institution, InstitutionAccess
from students.permissions import ensure_default_groups


# Departments a clerk signs in through, and the ones this command grants when
# --department is omitted. Teacher is granted by linking the login to an
# Employee row (Employee.user), not by a blanket grant, so it is left out.
CLERICAL_DEPARTMENTS = ('Office', 'Exam', 'Accounts')


class Command(BaseCommand):
    help = "Grant or revoke a user's institution access (the login screen needs it)."

    def add_arguments(self, parser):
        parser.add_argument('username', nargs='?', help='Username to grant access to.')
        parser.add_argument('--institution', help='Institution id or name.')
        parser.add_argument(
            '--department',
            choices=[label for label, _ in InstitutionAccess.DEPARTMENT_CHOICES],
            help=(
                'One department. Omit to grant every clerical department (Office, '
                'Exam, Accounts) — Teacher access comes from linking the login to '
                'an Employee row, so it is never granted blanket.'
            ),
        )
        parser.add_argument('--revoke', action='store_true', help='Remove the access instead of granting it.')
        parser.add_argument('--list-users', action='store_true', help='List every user and their access, then exit.')

    def handle(self, *args, **options):
        User = get_user_model()

        if options['list_users'] or not options['username']:
            self._report(User)
            if not options['username']:
                return

        user = User.objects.filter(username__iexact=options['username'].strip()).first()
        if user is None:
            raise CommandError(
                f"No user named '{options['username']}'. "
                f"Run with --list-users to see the accounts that exist."
            )

        institution = self._resolve_institution(options['institution'])
        departments = (
            [options['department']] if options['department']
            # Teacher is deliberately out of the blanket grant: that access is
            # granted by linking the login to an Employee row (Employee.user).
            else [value for value in CLERICAL_DEPARTMENTS]
        )

        if options['revoke']:
            removed = InstitutionAccess.objects.filter(
                user=user, institution=institution, department__in=departments,
            ).delete()[0]
            self.stdout.write(self.style.WARNING(
                f"Revoked {removed} access row(s) for {user.username} on {institution.name}."
            ))
        else:
            created = 0
            for department in departments:
                _, was_created = InstitutionAccess.objects.get_or_create(
                    user=user, institution=institution, department=department,
                    defaults={'is_active': True},
                )
                if was_created:
                    created += 1
            # A row that was revoked earlier comes back as active.
            reactivated = InstitutionAccess.objects.filter(
                user=user, institution=institution, department__in=departments, is_active=False,
            ).update(is_active=True)
            ensure_default_groups()
            self.stdout.write(self.style.SUCCESS(
                f"{user.username} can now log in to {institution.name} "
                f"({', '.join(departments)}): {created} new row(s), {reactivated} reactivated."
            ))

        self._report(User, only=user)

    def _resolve_institution(self, value):
        if not value:
            raise CommandError(
                'Pass --institution <id or name>. Available institutions:\n  '
                + '\n  '.join(f'{i.id}: {i.name}' for i in Institution.objects.order_by('id'))
            )
        institution = None
        if str(value).isdigit():
            institution = Institution.objects.filter(pk=int(value)).first()
        if institution is None:
            institution = Institution.objects.filter(name__iexact=str(value).strip()).first()
        if institution is None:
            raise CommandError(
                f"No institution matching '{value}'. Available:\n  "
                + '\n  '.join(f'{i.id}: {i.name}' for i in Institution.objects.order_by('id'))
            )
        return institution

    def _report(self, User, only=None):
        users = User.objects.order_by('username') if only is None else [only]
        self.stdout.write('Users and their institution access:')
        for user in users:
            kind = 'superuser' if user.is_superuser else ('staff' if user.is_staff else 'user')
            rows = InstitutionAccess.objects.filter(user=user).select_related('institution')
            self.stdout.write(f"  {user.username} ({kind}, active={user.is_active})")
            if user.is_superuser or user.is_staff:
                self.stdout.write('    - admin: can log in to any institution')
            for row in rows:
                state = '' if row.is_active else ' [INACTIVE]'
                self.stdout.write(f'    - {row.institution.name} / {row.department}{state}')
            if not rows and not (user.is_superuser or user.is_staff):
                self.stdout.write('    - no access: login will be refused')
