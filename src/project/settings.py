"""Django settings for appy-reviews project.

Generated by 'django-admin startproject' using Django 2.0.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.0/ref/settings/

"""
import os

import dj_database_url
import requests
from django.utils.log import DEFAULT_LOGGING


def bool_environ(key, default=''):
    value = os.getenv(key, default).lower()
    if value in ('', 'n', 'no', 'f', 'false', '0'):
        return False
    if value in ('y', 'yes', 't', 'true', '1'):
        return True
    raise ValueError(key)


# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '2n3(z!1*qc(&*-7((1$myom)7oyn@pr!348s&unjxr7-9-npm('

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = bool_environ('APPY_DEBUG')

CANONICAL_HOST = 'review.dssg.io'
STAGING_HOST = f's.{CANONICAL_HOST}'
EXTRA_HOSTS = [
    extra_host1 for extra_host1 in (
	extra_host0.strip() for extra_host0 in os.getenv('ALLOWED_HOSTS', '').split(',')
    ) if extra_host1
]

if DEBUG:
    EC2_PRIVATE_IP = None
else:
    ALLOWED_HOSTS = [
        CANONICAL_HOST,
	STAGING_HOST,
    ]
    ALLOWED_HOSTS.extend(EXTRA_HOSTS)

    try:
        response = requests.get(
            'http://169.254.169.254/latest/meta-data/local-ipv4',
            timeout=0.01
        )
    except requests.exceptions.RequestException:
        EC2_PRIVATE_IP = None
    else:
        EC2_PRIVATE_IP = response.text

    if EC2_PRIVATE_IP:
        ALLOWED_HOSTS.append(EC2_PRIVATE_IP)

    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Application definition

INSTALLED_APPS = [
    #
    # our apps
    #
    'review',

    #
    # 3rd-party
    #
    # allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    # allauth enabled providers
    # 'allauth.socialaccount.providers.amazon',
    # 'allauth.socialaccount.providers.bitbucket',
    # 'allauth.socialaccount.providers.bitbucket_oauth2',
    # 'allauth.socialaccount.providers.facebook',
    'allauth.socialaccount.providers.github',
    # 'allauth.socialaccount.providers.gitlab',
    'allauth.socialaccount.providers.google',
    # 'allauth.socialaccount.providers.linkedin',
    # 'allauth.socialaccount.providers.linkedin_oauth2',
    # 'allauth.socialaccount.providers.openid',
    # 'allauth.socialaccount.providers.reddit',
    # 'allauth.socialaccount.providers.slack',
    # 'allauth.socialaccount.providers.stackexchange',
    # 'allauth.socialaccount.providers.trello',
    # 'allauth.socialaccount.providers.twitter',
    #

    'django_tables2',

    # django-mathfilters
    'mathfilters',

    #
    # Django "contrib"
    #
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
]

MIDDLEWARE = [
    'review.middleware.ping_middleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'project.urls'

SITE_ID = 1

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/2.0/ref/settings/#databases

DATABASE_SCHEMA = 'appy_reviews'
DATABASE_URL = os.getenv('DATABASE_URL')

DATABASES = {
    # Reads from environment variable DATABASE_URL
    # E.g., for production:
    #   postgres://appy_reviews:PASSWORD@postgres.dssg.io/appy_reviews
    'default': dict(
        dj_database_url.config(),
        OPTIONS={
            'options': f'-c search_path={DATABASE_SCHEMA}',
        },
    ),
}


# Email

DEFAULT_FROM_EMAIL = 'DSSG application review <appy@review.dssg.io>'

APPLICATION_REPLY_TO_EMAIL = ('dssg@datascienceforsocialgood.org',)

EMAIL_HOST = 'email-smtp.us-west-2.amazonaws.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('SMTP_USER')
EMAIL_HOST_PASSWORD = os.getenv('SMTP_PASSWORD')


# Password validation
# https://docs.djangoproject.com/en/2.0/ref/settings/#auth-password-validators

AUTH_USER_MODEL = 'review.Reviewer'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

LOGIN_REDIRECT_URL = '/'

# allauth

ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 30
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_PRESERVE_USERNAME_CASING = False
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USERNAME_REQUIRED = False

SOCIALACCOUNT_ADAPTER = 'review.adapter.TrustingSocialAccountAdapter'
SOCIALACCOUNT_AUTO_CONNECT_PROVIDERS = {'google', 'github'}


# review

REVIEW_SLACK_JOIN_URL = os.getenv('SLACK_JOIN_URL', None)
REVIEW_SLACK_CHANNEL_URL = os.getenv('SLACK_CHANNEL_URL', None)

REVIEW_PROGRAM_YEAR = 2022
REVIEW_SURVEY_LENGTH = 2
REVIEW_REVIEWER_APPROVED = True
REVIEW_WHITELIST = set(filter(None, os.getenv('REVIEW_WHITELIST', '').split(' ')))
REVIEW_APPLICATION_FIELDS = {
    # <"page" table>: (
    #       <pretty table name>, (
    #           <pretty field name>,
    #           (<look-up (composite) key, (if different from pretty name)>)
    #            <OR>
    #           None,
    #       ),
    #       ...
    # FIXME: For many of these, would be at least as easy and
    # FIXME: reliable (if not more so) to use FieldIds....
    f'survey_application_1_{REVIEW_PROGRAM_YEAR}': (
        'Basics', (
        ('Full Name', (('First', 0), ('Last', 0))),
        ('Email', [('Email', 0)]),
        ('Program Interests', ('Please consider me for:',)),
        ('Gender Identification', ('What gender do you identify with?',)),
        ('Do you identify as LGBTQ+?', None),
        #('What races or ethnicities do you identify with?', (
            #'Asian', 'Black', 'Hispanic, Latino, Latina, or Latinx',
            #'Indigenous, Native, or First Nation',
            #'Middle Eastern or North African',
            #'White',
            #'Prefer not to answer',
            #'Not listed here or prefer to self-describe',)),
        ('Physical/other accommodation required?', (
            '''Do you have a long-lasting or chronic condition '''
            '''(such as physical, visual, auditory, cognitive, emotional, '''
            '''or other) that requires ongoing accommodations for you to '''
            '''conduct daily life activities?''',
        )),
    )),
    f'survey_application_2_{REVIEW_PROGRAM_YEAR}': (
        'Main', (
        ('Preferred Name', None),
        ('Locale', ('City', 'State / Province / Region', 'Country')),
        ('Country of Citizenship and Visa Status for US', None),
        ('Self-description', ('Which of these best describes you:',)),
        ('University Name', ('Most Recent University Name',)),
        ('Major/department', None),
        ('Advisor Name', (('First', 1), ('Last', 1))),
        ('Expected Graduation Date (or date when you last graduated)', None),
        ('Transcripts', ('Upload your unofficial transcripts '
                         '(copy of your grades) from your current degree '
                         'program (or from the most recent degree you have received).',)),
        ('Computer Programming', None),
        ('Computer Science (Algorithms)', None),
        ('Traditional Statistics', None),
        ('Machine Learning', None),
        ('Social Science (Economics, Sociology, PoliSci, ...)', None),
        ('Experience working on real-world problems using data', None),
        ('Experimental Design and Methods (RCTs, A/B testing, etc.)', None),
        ('Data Manipulation and ETL Skills', None),
        ('Visualization', None),
        ('Python', None),
        ('C/C++/C#/Java', None),
        ('Other', [('Other', 0)]),
        ('Programming Experience', (
            '''Tell us more about your programming experience. '''
            '''What projects have you worked on, what was your role, and '''
            '''what tools and languages did you use?  \n\n'''
            '''You don't need to be an expert coder to be part of DSSG, but '''
            '''you need some coding experience. We want to know more about '''
            '''your skills so we can create the right teams  for each project.''',
        )),
        ('R', None),
        ('SQL', None),
        ('GIS tools', None),
        ('Matlab', None),
        ('SAS', None),
        ('SPSS', None),
        ('Stata', None),
        ('Julia', None),
        ('Other', [('Other', 1)]),
        ('Analysis Experience', (
            "Tell us more about projects you have done with data analysis, and the types of analysis you did",
        )),
        ('Regression Models', None),
        ('Decision Trees', None),
        ('SVMs', None),
        ('Random Forests', None),
        ('Neural Networks / Deep Learning', None),
        ('Time Series Models', None),
        ('Unsupervised models', None),
        ('Semi-supervised models', None),
        ('Graphical models', None),
        ('Other', [('Other', 2)]),
        ('Modeling/machine-learning experience', (
            '''Tell us more about your experience with modeling and machine '''
            '''learning algorithms and methods. \n\n'''
            '''Which algorithms and methods have you used? \n'''
            '''Which ones are you comfortable with?\n\n'''
            '''Tell us about a project you've done using  machine learning \n'''
            '''- What was the goal of the project?\n'''
            '''- What did you do?\n'''
            '''- How were the results used?\n'''
            '''- Did anyone else have to use your work?''',
        )),
        ('Causal inference', None),
        ('Matching (e.g., Propensity Score Matching )', None),
        ('Instrumental Variables', None),
        ('Regression Discontinuity', None),
        ('Natural Experiments', None),
        ('Other', [('Other', 3)]),
        ('Social science experience', (
            '''Tell us more about your experience with quantitative social '''
            '''science methods. What methods have you used? What was the '''
            '''goal of the work you were doing? How were the results used?''',
        )),
        ('Data in Text Files', None),
        ('Data in Relational Databases', None),
        ('Text Data (NLP)', None),
        ('Network/Graph Data', None),
        ('Multimedia Data (Video or Audio)', None),
        ('Data from Sensors', None),
        ('Data > 1TB', None),
        ('Geospatial', None),
        ('Other', [('Other', 4)]),
        ('Data experience', (
            '''Tell us more about your experience using data. What type of '''
            '''data are you most experienced and comfortable with? \n\n'''
            '''Text files? databases? natural language text data? '''
            '''graphs/networks? images? multimedia?''',
        )),
        ('Data projects', (
            '''Tell us about data-related projects you’ve worked on recently. \n\n'''
            '''For example:\n'''
            '''What was the goal of the project?\n'''
            '''What methods and tools did you use? \n'''
            '''What did you do? \n'''
            '''Were these projects that you worked on independently, or as '''
            '''part of a team? \n'''
            '''What was your role if it was done as part of a team?\n'''
            '''What was the outcome and impact?\n\n'''
            '''If any materials about the projects are available online, '''
            '''please include links here (papers, web pages, Github repos, '''
            '''blog posts, etc.).''',
        )),
        ('Github / code sample', (
            '''Link to your GitHub Account, if you have one (or a code sample '''
            '''that is online)''',
        )),
        ('Experienced in working on problems related to: Education', [('Education', 0)]),
        ('...Health', [('Health', 0)]),
        ('...Energy', [('Energy', 0)]),
        ('...Environment', [('Environment', 0)]),
        ('...Transportation', [('Transportation', 0)]),
        ('...Poverty', [('Poverty', 0)]),
        ('...Housing/Land Use', [('Housing/Land Use', 0)]),
        ('...Public Safety', [('Public Safety', 0)]),
        ('...International Development', [('International Development', 0)]),
        ('...Other', [('Other', 5)]),
        ('Other experience', ('If experience in problem area is "Other", please describe:',)),
        ('Interested in working on problems related to: Education', [('Education', 1)]),
        ('...Health', [('Health', 1)]),
        ('...Energy', [('Energy', 1)]),
        ('...Environment', [('Environment', 1)]),
        ('...Transportation', [('Transportation', 1)]),
        ('...Poverty', [('Poverty', 1)]),
        ('...Housing/Land Use', [('Housing/Land Use', 1)]),
        ('...Public Safety', [('Public Safety', 1)]),
        ('...International Development', [('International Development', 1)]),
        ('...Other', [('Other', 6)]),
        ('Other interest', ('If interest in problem area is "Other", please describe:',)),
        ('Motivation / public sector experience', (
            '''What is it about ‘social good’ work that you find compelling? \n\n'''
            '''Tell us about your past experiences working in (or with) the public sector '''
            '''(this can mean work or projects with governments and nonprofits, volunteer '''
            '''work, or for-profit work with a social mission). \n\n'''
            '''What accomplishment are you most proud of in this area? '''
            '''In two sentences, tell us what you found a) the most rewarding and '''
            '''b) the most frustrating about these experiences.''',
        )),
        ('Teamwork', (
            '''DSSG is a team-centric environment. Tell us the three best '''
            '''qualities that you bring to a team (your experiences can be '''
            '''from school or from a job). \n\n'''
            '''Additionally, tell us one element of teamwork that you find '''
            '''frustrating, and walk us through the process of how you like '''
            '''to work through disagreements.\n\n'''
            '''How do you organize your work when working with a team? What '''
            '''collaboration tools did you use to work with a team? '''
            '''(Calendars, Email, Slack, GitHub, Trello, etc)''',
        )),
        ('Future plans', (
            '''Tell us about your future plans (post-DSSG and post-summer as '''
            '''well as longer term) and what you want to get out of this '''
            '''summer at DSSG''',
        )),
        ('How did you hear about this program?', None),
        ('''Have you applied to DSSG in the past?''', None),
        ('Additional information', (
            '''Anything else you'd like to tell us? If you have applied for '''
            '''DSSG in the past, please tell us what's new since you '''
            '''last applied''',
        )),
        ('Resume/CV', (
            '''Please attach your resume or CV as an additional Word, PDF, '''
            '''or text document.''',
        )),
        # ('University Housing requested', (
        #     '''I would like to be considered for a space in University Housing''',
        # )),
        ('Interested in DSaPP', (
            '''I am currently available and interested in a post-summer job opportunity''',
        )),
        ('May share info', (
            '''I would like DSSG to share my info with social-good '''
            '''organizations who are looking for help (Don't worry: we won't '''
            '''sell your info.)''',
        )),
    )),
    f'survey_recommendation_{REVIEW_PROGRAM_YEAR}': (
        'Reference {{ count }}', (
            ('Reference Name', ('First', 'Last')),
            ('Reference Email', ('Your Email',)),
            ('Reference Organization/University', ('Your Organization/University',)),
            ('Applicant Email', ('Applicant Email Address',)),
            ('Reference has known applicant for', ('How long have you known the applicant?',)),
            ('In the capacity of', ('In what capacity?',)),
            ("Applicant's ability in computer programming", ('Computer programming',)),
            ("Applicant's ability in statistics", ('Statistics',)),
            ("Applicant's ability in data analysis", ('Data analysis skills',)),
            ("Applicant's ability in social science methodology", ('Social science methods',)),
            ("Applicant's communication ability", ('Communication ability',)),
            ("Applicant's experience working in teams", ('Experience working in teams',)),
            ("Applicant's interest and passion for social good", ('Interest and passion for social good',)),
            ('Good match for program?', (
                '''The fellowship is very competitive and we are looking for a '''
                '''mix of people: smart, quantitative, analytical individuals who '''
                '''can work well in a team and who care about using their skills '''
                '''to make a social impact. \n\n'''
                '''In your opinion, does this applicant match those qualities and '''
                '''will this applicant benefit from this program?''',
            )),
            ('Should we accept this applicant?', None),
            ('What makes applicant stand out', (
                '''What makes this candidate stand out for you?''',
            )),
            ('Recommendation letter', (
                '''Please upload a letter in Word document or PDF format '''
                '''below or paste the text in the box below''',
                '''Please attach your recommendation as an additional Word, '''
                '''PDF or text document.''',
            )),
            ('Additional comments', ('''Anything else you'd like to tell us?''',)),
    )),
}

# Internationalization
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/

STATIC_URL = '/static/'


# Logging

if not DEBUG:
    LOGGING = DEFAULT_LOGGING.copy()
    LOGGING['handlers']['console']['filters'] = ['require_debug_false']
    LOGGING['loggers']['django.server']['propagate'] = True
