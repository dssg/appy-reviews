from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.conf import settings
from django.core.management.base import LabelCommand, CommandError
from django.db import IntegrityError
from django.urls import reverse

from review.models import Reviewer


class Command(LabelCommand):

    label = 'email'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adapter = get_adapter(None)

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '-c', '--create',
            action='store_true',
            help="create reviewer(s) with given email address(es)",
        )
        parser.add_argument(
            '-f', '--force',
            action='store_true',
            help="continue regardless of errors",
        )
        parser.add_argument(
            '-t', '--template',
            default='account/email/reviewer_invitation',
            help="email template prefix "
                 "(default: account/email/reviewer_invitation)",
        )

    def handle(self, *emails, **options):
        output = super().handle(*emails, **options)
        return output + '\ndone' if output else 'done'

    def handle_label(self, email, create, force, template, **_options):
        try:
            if create:
                try:
                    reviewer = Reviewer.objects.create_reviewer(email, None)
                except IntegrityError:
                    raise CommandError(f'{email}: reviewer already exists')
            else:
                try:
                    reviewer = Reviewer.objects.get(email=email)
                except Reviewer.DoesNotExist:
                    raise CommandError(f'{email}: no such reviewer')
        except CommandError as exc:
            if force:
                self.stderr.write(f'✘ {exc}')
                return
            raise

        self.send_email(reviewer, template)
        self.stdout.write(f'✔ {email}')

    def send_email(self, reviewer, template):
        try:
            email_address = EmailAddress.objects.get_for_user(reviewer,
                                                              reviewer.email)
        except EmailAddress.DoesNotExist:
            email_address = EmailAddress.objects.create(
                user=reviewer,
                email=reviewer.email,
            )

        site_url = 'http://' + settings.CANONICAL_HOST
        if email_address.verified:
            activate_url = site_url + '/'
        else:
            confirmation = EmailConfirmationHMAC(email_address)
            activate_url = site_url + reverse('account_confirm_email',
                                              args=[confirmation.key])

        self.adapter.send_mail(template, reviewer.email, {
            'user': reviewer,
            'activate_url': activate_url,
            'domain': settings.CANONICAL_HOST,
            'program_year': settings.REVIEW_PROGRAM_YEAR,
            'verified': email_address.verified,
        })
