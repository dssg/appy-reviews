import collections
import enum
import re

from django.conf import settings
from django.contrib import auth
from django.contrib.auth import models as auth_models
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.fields import CIEmailField
from django.core.mail import send_mail
from django.db import connection, models
from django.db.models import fields
from django.utils import datastructures, safestring, timezone

from descriptors import cachedproperty


class StrEnum(str, enum.Enum):

    def __str__(self):
        return self.value


class SafeStrEnum(StrEnum):

    def __str__(self):
        return safestring.mark_safe(self.value)


class IntEnum(int, enum.Enum):

    def __str__(self):
        return str(self.value)


class EnumFieldMixin(object):

    member_cast = str

    @classmethod
    def prepare_init_kwargs(cls, enum, kws):
        if 'choices' in kws:
            raise TypeError("Unexpected keyword argument 'choices'")

        try:
            choices = enum.__members__.items()
        except AttributeError:
            choices = enum

        return dict(kws, choices=choices)

    def __init__(self, enum, **kws):
        super().__init__(**self.prepare_init_kwargs(enum, kws))

    def deconstruct(self):
        """Return a suitable description of this field for migrations.

        """
        (name, path, args, kwargs) = super().deconstruct()
        choices = [(key, self.member_cast(member))
                   for (key, member) in kwargs.pop('choices')]
        return (name, path, [choices] + args, kwargs)


class EnumCharField(EnumFieldMixin, fields.CharField):

    @classmethod
    def prepare_init_kwargs(cls, enum, kws):
        prepared = super().prepare_init_kwargs(enum, kws)
        choices = prepared['choices']
        prepared.setdefault(
            'max_length',
            max((len(name) for (name, _value) in choices), default=0)
        )
        return prepared

    def deconstruct(self):
        """Return a suitable description of this field for migrations.

        """
        (name, path, args, kwargs) = super().deconstruct()

        del kwargs['max_length']

        return (name, path, args, kwargs)


class EnumIntegerField(EnumFieldMixin, fields.IntegerField):
    pass


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

    # For compatibility with Django Admin site
    @property
    def is_superuser(self):
        return self.trusted

    @property
    def user_permissions(self):
        return self.permissions

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

    # For compatibility with Django Admin site
    def create_trusted(self, *args, **extra_fields):
        if not extra_fields.setdefault('trusted', True):
            raise TypeError("Cannot create untrusted superuser")
        return self.create_reviewer(*args, **extra_fields)

    create_superuser = create_trusted


class Reviewer(AbstractBaseUser, PermissionsMixin):

    reviewer_id = models.AutoField(primary_key=True)
    email = CIEmailField(
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
    # FIXME: In 2018, we used background to describe interviewers' experience
    # FIXME: with / connection to DSSG, (included in interview email).
    # FIXME: If we intend to use this field to describe the reviewer's
    # FIXME: background at all, (and e.g. to match reviewers with applications),
    # FIXME: then we should provision a new field and migrate
    # FIXME: currently-populated background values to it, e.g.:
    # FIXME: program_experience = CharField(max_length=250, blank=True)
    background = models.CharField(max_length=100, blank=True, choices=(
        ('soc-sci', 'Social Science'),
        ('comp-sci', 'Computer Science'),
        ('math-stat', 'Math/Statistics'),
    ))

    class Meta:
        db_table = 'reviewer'
        ordering = ('email',)

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

    # For compatibility with Django Admin site
    @property
    def is_staff(self):
        return self.trusted

    @cachedproperty
    def concession(self):
        try:
            return ReviewerConcession.objects.get(
                reviewer=self,
                program_year=settings.REVIEW_PROGRAM_YEAR,
            )
        except ReviewerConcession.DoesNotExist:
            return None


class ReviewerConcession(models.Model):

    reviewer_concession_id = models.AutoField(primary_key=True)
    program_year = models.IntegerField()
    reviewer = models.ForeignKey('review.Reviewer',
                                 on_delete=models.CASCADE,
                                 related_query_name='concessions',
                                 related_name='+')
    is_reviewer = models.BooleanField(default=False)
    is_interviewer = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reviewer_concession'
        ordering = ('-program_year', 'reviewer')
        unique_together = ('program_year', 'reviewer')

    def __str__(self):
        return ' and '.join(
            label for (label, condition) in (
                ('reviewer', self.is_reviewer),
                ('interviewer', self.is_interviewer),
            ) if condition
        ) + f' ({self.program_year})'


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

    def __str__(self):
        return self.email


#
# Application
#

class Application(models.Model):

    class FinalDecision(StrEnum):

        accept = 'Accept'
        reject = 'Reject'
        waitlist = 'Waitlist'

    application_id = models.AutoField(primary_key=True)
    applicant = models.ForeignKey('review.Applicant',
                                  on_delete=models.CASCADE,
                                  related_name='applications')

    review_decision = models.BooleanField(
        "Review?",
        default=True,
        help_text="Whether we intend to review this application",
    )
    interview1_decision = models.NullBooleanField(
        "Interview (Round 1)?",
        help_text="Whether we intend to interview this applicant",
    )
    interview2_decision = models.NullBooleanField(
        "Interview (Round 2)?",
        help_text="Whether we intend to give this applicant a second interview",
    )
    final_decision = EnumCharField(FinalDecision, blank=True)

    program_year = models.IntegerField()
    created = models.DateTimeField(auto_now_add=True)
    withdrawn = models.DateTimeField(null=True)

    class Meta:
        db_table = 'application'
        ordering = ('-created',)

    def __str__(self):
        return f'{self.applicant} ({self.program_year})'


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
        ordering = ('table_name', 'column_name', 'entity_code')
        unique_together = (
            ('table_name', 'column_name', 'entity_code'),
        )

    @cachedproperty
    def entry(self):
        with connection.cursor() as cursor:
            cursor.execute(
                f'''
                    select * from "{self.table_name}"
                    where "{self.table_name}"."{self.column_name}"=%(entity_code)s
                ''',
                {
                    'entity_code': self.entity_code,
                },
            )
            columns = [col[0] for col in cursor.description]
            row = cursor.fetchone()

            if row is None:
                raise self.DoesNotExist

            if cursor.fetchone() is not None:
                raise self.MultipleObjectsReturned

            cursor.execute(
                '''select field_id, field_title from "{table_name}"'''
                .format(table_name=re.sub(r'(_\d{4})$',
                                          r'_fields\1',
                                          self.table_name))
            )
            fields = dict(cursor)

        entry = datastructures.MultiValueDict()
        for (column, value) in zip(columns, row):
            key = fields.get(column, column)
            entry.appendlist(key, value)
        return entry

    def __str__(self):
        return str(self.entry)


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

class AbstractRating(models.Model):

    programming_rating = models.IntegerField("Programming", null=True)
    machine_learning_rating = models.IntegerField("Stats & Machine Learning", null=True)
    data_handling_rating = models.IntegerField("Data Handling & Manipulation", null=True)
    social_science = models.IntegerField("Social Science", null=True)
    interest_in_good_rating = models.IntegerField("Interest in Social Good", null=True)
    communication_rating = models.IntegerField("Communication Ability", null=True)
    teamwork_rating = models.IntegerField("Teamwork and Collaboration", null=True)

    class Meta:
        abstract = True

    @staticmethod
    def rating_fields():
        # Note: not appropriate to refer to `cls`, as we only want
        # AbstractRating's fields
        return collections.OrderedDict(
            (field.name, field.verbose_name)
            for field in AbstractRating._meta.fields
        )


class ApplicationLinkedQuerySet(models.QuerySet):

    def current_year(self):
        return self.filter(
            application__program_year=settings.REVIEW_PROGRAM_YEAR,
        )


class ApplicationReview(AbstractRating):

    class OverallRecommendation(SafeStrEnum):

        interview = "Interview &ndash; definitely!"
        maybe_interview = "Interview &hellip; maybe"
        only_if = "Interview <em>only</em> if you need a certain type of fellow (explain below)"
        reject = "Reject"

    review_id = models.AutoField(primary_key=True)
    reviewer = models.ForeignKey('review.Reviewer',
                                 on_delete=models.CASCADE,
                                 related_name='application_reviews')
    application = models.ForeignKey('review.Application',
                                    on_delete=models.CASCADE,
                                    related_name='application_reviews')
    submitted = models.DateTimeField(auto_now_add=True, db_index=True)

    overall_recommendation = EnumCharField(
        OverallRecommendation,
        help_text="Overall recommendation",
    )
    comments = models.TextField(
        blank=True,
        help_text="Any comments?",
    )
    interview_suggestions = models.TextField(
        blank=True,
        help_text="In an interview with this candidate, what should we focus on? "
                  "Any red flags? Anything you would ask them about that's hard to "
                  "judge from the application and references?",
    )
    would_interview = models.BooleanField(
        help_text="If this applicant moves to the interview round, would "
                  "you like to interview them?",
    )

    objects = ApplicationLinkedQuerySet.as_manager()

    class Meta:
        # TODO: migrate db table to "application_review"
        db_table = 'review'
        ordering = ('-submitted',)
        unique_together = (
            ('application', 'reviewer'),
        )

    def __str__(self):
        return (f'{self.reviewer} regarding {self.application}: '
                f'{self.overall_recommendation}')


class InterviewReview(AbstractRating):

    class OverallRecommendation(SafeStrEnum):

        accept = "Accept"
        reject = "Reject"
        only_if = "Accept <em>only</em> if you need a certain type of fellow (explain below)"

    interview_assignment = models.OneToOneField('review.InterviewAssignment',
                                                primary_key=True,
                                                on_delete=models.CASCADE,
                                                related_name='interview_review')

    overall_recommendation = EnumCharField(
        OverallRecommendation,
        help_text="Overall recommendation",
    )
    comments = models.TextField(
        blank=True,
        help_text="Any comments?",
    )
    candidate_rank = models.TextField(
        blank=True,
        help_text="How does this candidate compare to others you've "
                  "interviewed? Once you've completed all of your interviews, "
                  "please rank this candidate within your interview pool."
    )

    submitted = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'interview_review'
        ordering = ('-submitted',)


class InterviewAssignment(models.Model):

    class InterviewRound(IntEnum):

        round_one = 1
        round_two = 2

    interview_assignment_id = models.AutoField(primary_key=True)
    application = models.ForeignKey('review.Application',
                                    on_delete=models.CASCADE,
                                    related_name='interview_assignments')
    reviewer = models.ForeignKey('review.Reviewer',
                                 on_delete=models.CASCADE,
                                 related_name='interview_assignments')
    interview_round = EnumIntegerField(InterviewRound)  # FIXME: key/value backwards in choices?
    assigned = models.DateTimeField(auto_now_add=True, db_index=True)
    notified = models.DateTimeField(null=True, db_index=True)

    objects = ApplicationLinkedQuerySet.as_manager()

    class Meta:
        db_table = 'interview_assignment'
        ordering = ('-assigned',)
        unique_together = (
            ('application', 'reviewer', 'interview_round'),
        )
