from django.contrib import auth
from django.contrib.auth import models as auth_models
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone


#
# Reviewer
#

class PermissionsMixin(models.Model):
    """Add the fields and methods necessary to support the Group and Permission
    models using the ModelBackend.

    """
    trusted = models.BooleanField(
        'trusted status',
        default=False,
        help_text='Designates that this reviewer can accept or reject '
                  'applicant without submitting review.'
    )
    groups = models.ManyToManyField(
        'auth.Group',
        blank=True,
        help_text='The groups this reviewer belongs to. A reviewer will get '
                  'all permissions granted to each of their groups.',
        related_name="reviewers",
        related_query_name="reviewer",
    )
    permissions = models.ManyToManyField(
        'auth.Permission',
        blank=True,
        help_text='Specific permissions for this reviewer.',
        related_name="reviewers",
        related_query_name="reviewer",
    )

    class Meta:
        abstract = True

    def get_group_permissions(self, obj=None):
        """Return a list of permission strings that this reviewer has
        through their groups.

        Query all available auth backends. If an object is passed in,
        return only permissions matching this object.

        """
        permissions = set()
        for backend in auth.get_backends():
            if hasattr(backend, "get_group_permissions"):
                permissions.update(backend.get_group_permissions(self, obj))
        return permissions

    def get_all_permissions(self, obj=None):
        return auth_models._user_get_all_permissions(self, obj)

    def has_perm(self, perm, obj=None):
        """Return True if the reviewer has the specified permission. Query all
        available auth backends, but return immediately if any backend returns
        True. Thus, a reviewer who has permission from a single auth backend is
        assumed to have permission in general. If an object is provided, check
        permissions for that object.
        """
        # Active superusers have all permissions.
        if self.is_active and self.trusted:
            return True

        # Otherwise we need to check the backends.
        return auth_models._user_has_perm(self, perm, obj)

    def has_perms(self, perm_list, obj=None):
        """
        Return True if the reviewer has each of the specified permissions. If
        object is passed, check if the reviewer has all required perms for it.
        """
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_module_perms(self, app_label):
        """
        Return True if the reviewer has any permissions in the given app label.
        Use simlar logic as has_perm(), above.
        """
        # Active superusers have all permissions.
        if self.is_active and self.trusted:
            return True

        return auth_models._user_has_module_perms(self, app_label)


class ReviewerManager(BaseUserManager):

    use_in_migrations = True

    def create_reviewer(self, email, password, **extra_fields):
        """Create and save a reviewer with the given email and password.

        """
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        email = self.model.normalize_username(email)
        reviewer = self.model(email=email, **extra_fields)
        reviewer.set_password(password)
        reviewer.save(using=self._db)
        return reviewer


class Reviewer(AbstractBaseUser, PermissionsMixin):

    reviewer_id = models.AutoField(primary_key=True)
    email = models.EmailField(
        'email address',
        unique=True,
        error_messages={
            'unique': "A reviewer with that email already exists.",
        },
    )
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(
        'active',
        default=True,
        help_text='Designates whether this reviewer should be treated as '
                  'active. Unselect this instead of deleting accounts.'
    )
    date_joined = models.DateTimeField(default=timezone.now)
    background = models.CharField(max_length=100, blank=True, choices=(
        ('soc-sci', 'Social Science'),
        ('comp-sci', 'Computer Science'),
        ('math-stat', 'Math/Statistics'),
    ))

    class Meta:
        db_table = 'reviewer'

    objects = ReviewerManager()

    USERNAME_FIELD = EMAIL_FIELD = 'email'

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name

    def email_user(self, subject, message, from_email=None, **kwargs):
        """Send an email to this user."""
        send_mail(subject, message, from_email, [self.email], **kwargs)


#
# Applicant
#

class Applicant(models.Model):

    applicant_id = models.AutoField(primary_key=True)
    email = models.EmailField(
        'email address',
        unique=True,
        error_messages={
            'unique': "An applicant with that email already exists.",
        },
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'applicant'


#
# Application
#

class Application(models.Model):

    application_id = models.AutoField(primary_key=True)
    applicant = models.ForeignKey('review.Applicant',
                                  on_delete=models.CASCADE,
                                  related_name='applications')
    decision = models.CharField(max_length=6, choices=(
        ('accept', 'Accept'),
        ('reject', 'Reject'),
    ))
    program_year = models.IntegerField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'application'


#
# SurveyEntries
#

class SurveyEntry(models.Model):

    table_name = models.CharField(max_length=300)
    column_name = models.CharField(max_length=300)
    entity_code = models.CharField(max_length=200)
    application = models.ForeignKey('review.Application', on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        unique_together = (
            ('table_name', 'column_name', 'entity_code'),
        )


class ApplicationPage(SurveyEntry):

    application_page_id = models.AutoField(primary_key=True)

    class Meta(SurveyEntry.Meta):
        db_table = 'application_page'


class Reference(SurveyEntry):

    reference_id = models.AutoField(primary_key=True)

    class Meta(SurveyEntry.Meta):
        db_table = 'reference'


#
# Review
#

class Review(models.Model):

    review_id = models.AutoField(primary_key=True)
    reviewer = models.ForeignKey('review.Reviewer', on_delete=models.CASCADE)
    application = models.ForeignKey('review.Application', on_delete=models.CASCADE)
    submitted = models.DateTimeField(auto_now_add=True)
    comments = models.TextField()  # FIXME

    # TODO

    class Meta:
        db_table = 'review'
        unique_together = (
            ('application', 'reviewer'),
        )
