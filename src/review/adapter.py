import allauth.account.adapter
import allauth.socialaccount.adapter
import allauth.socialaccount.signals
from allauth.socialaccount.providers.base import AuthProcess
from django.conf import settings
from django.contrib.auth import get_user_model


class ApplicationAdapter(allauth.account.adapter.DefaultAccountAdapter):
    """Account adapter for communication with *non-account* holders
    (applicants, references, *etc.*).

    """
    period_prefix = getattr(settings, 'APPLICATION_EMAIL_SUBJECT_PREFIX', '')

    def format_email_subject(self, subject):
        return f'{self.period_prefix}{subject}'


class TrustingSocialAccountAdapter(allauth.socialaccount.adapter.DefaultSocialAccountAdapter):
    """Social account adapter allowing for automatic sign-in via trusted
    sources of email identification.

    By default automatic sign-UP via *novel* email addresses is of
    course allowed. However, sign-IN via social accounts that haven't
    already been connected is disallowed -- IF the identity provider
    can't be trusted to verify email addresses, then this is a security
    vulnerability!

    Here automatic sign-in (really automatic/unauthorized connection of
    social accounts) may be opted into per provider.

    """
    def pre_social_login(self, request, sociallogin):
        if (
            not request.user.is_authenticated and
            not sociallogin.is_existing and
            sociallogin.email_addresses and
            sociallogin.state.get('process') not in (AuthProcess.REDIRECT, AuthProcess.CONNECT) and
            sociallogin.account.provider in settings.SOCIALACCOUNT_AUTO_CONNECT_PROVIDERS
        ):
            User = get_user_model()
            emails = [email_address.email for email_address in sociallogin.email_addresses]

            try:
                user = User.objects.get(email__in=emails)
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                pass
            else:
                sociallogin.connect(request, user)
                allauth.socialaccount.signals.social_account_added.send(
                    sender=sociallogin.__class__, request=request, sociallogin=sociallogin
                )
