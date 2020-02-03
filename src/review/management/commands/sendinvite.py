import os

from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.conf import settings
from django.core.management.base import LabelCommand, CommandError
from django.db import IntegrityError
from django.urls import reverse

from review.models import Reviewer


SLACK_URL = os.getenv('SLACK_URL', None)


class Command(LabelCommand):

    label = 'email'
    help = "Send email(s) to invite reviewer(s) to use Appy"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adapter = get_adapter(None)

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '-c', '--create',
            action='store_true',
            help="create reviewer(s) with given email address(es) as necessary",
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
        reviewer = None

        try:
            if create:
                try:
                    reviewer = Reviewer.objects.create_reviewer(email, None)
                except IntegrityError:
                    pass
                else:
                    try:
                        email_address = EmailAddress.objects.get_for_user(reviewer, email)
                    except EmailAddress.DoesNotExist:
                        email_address = EmailAddress.objects.create(
                            user=reviewer,
                            email=email,
                        )

            if not reviewer:
                try:
                    email_address = EmailAddress.objects.get(email__iexact=email)
                except EmailAddress.MultipleObjectsReturned:
                    raise CommandError(f'{email}: multiple records')
                except EmailAddress.DoesNotExist:
                    raise CommandError(f'{email}: no such reviewer')
                else:
                    reviewer = email_address.user
        except CommandError as exc:
            if force:
                self.stderr.write(f'✘ {exc}')
                return
            raise

        self.send_email(reviewer, email_address, template)
        self.stdout.write(f'✔ {email}')

    def send_email(self, reviewer, email_address, template):
        site_url = 'https://' + settings.CANONICAL_HOST
        if email_address.verified:
            activate_url = site_url + '/'
        else:
            confirmation = EmailConfirmationHMAC(email_address)
            activate_url = site_url + reverse('account_confirm_email',
                                              args=[confirmation.key])

        self.adapter.send_mail(template, email_address.email, {
            'user': reviewer,
            'email': email_address.email,
            'activate_url': activate_url,
            'domain': settings.CANONICAL_HOST,
            'program_year': settings.REVIEW_PROGRAM_YEAR,
            'slack_url': SLACK_URL,
            'verified': email_address.verified,
        })
