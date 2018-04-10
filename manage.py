import argparse
import contextlib
import enum
import os
import sys
from pathlib import Path

from argcmdr import Local, LocalRoot, localmethod
from plumbum import colors


ROOT_PATH = Path(__file__).parent.resolve()
SRC_PATH = ROOT_PATH / 'src'


class Appy(LocalRoot):
    """appy management"""


@Appy.register
class Build(Local):
    """build container image"""

    DEFAULT_NAMETAG = 'dsapp/appy-reviews/web:latest'

    REGISTRY = '093198349272.dkr.ecr.us-west-2.amazonaws.com'

    @classmethod
    def get_full_name(cls, name):
        return '/'.join((cls.REGISTRY, name))

    def __init__(self, parser):
        parser.add_argument(
            '-n', '--name',
            default=self.DEFAULT_NAMETAG,
            help=f'Image name/tag (default: {self.DEFAULT_NAMETAG})',
        )
        parser.add_argument(
            '--label',
            action='append',
            help='Additional name/tags to label image; the first of these, '
                 'if any, is treated as the "version"',
        )
        parser.add_argument(
            '--target',
            choices=('development', 'production'),
            default='production',
            help="Target environment (default: production)",
        )
        parser.add_argument(
            '-l', '--login',
            action='store_true',
            help="log in to AWS ECR",
        )
        parser.add_argument(
            '-p', '--push',
            action='store_true',
            help="push image once built",
        )
        parser.add_argument(
            '-d', '--deploy',
            action='store_true',
            help="deploy the container once the image is pushed",
        )

    def prepare(self, args, parser):
        if args.login and not args.push:
            parser.error("will not log in outside of push operation")

        command = self.local['docker'][
            'build',
            '--build-arg', f'TARGET={args.target}',
            '-t', args.name,
            '-t', self.get_full_name(args.name),
        ]

        if args.label:
            for label in args.label:
                command = command['-t', label]

        yield command[ROOT_PATH]

        if args.push:
            yield from self['push'].prepare(args)

        if args.deploy:
            yield self['deploy'].prepare(args)

    class Push(Local):
        """push already-built image to registry"""

        def __init__(self, parser):
            parser.add_argument(
                '-l', '--login',
                action='store_true',
                help="log in to AWS ECR",
            )

        def prepare(self, args):
            if args.login:
                login_command = self.local['aws'][
                    'ecr',
                    'get-login',
                    '--no-include-email',
                    '--region', 'us-west-2',
                ]
                if args.show_commands or not args.execute_commands:
                    print('>', login_command)
                if args.execute_commands:
                    full_command = login_command()
                    (executable, *arguments) = full_command.split()
                    assert executable == 'docker'
                    yield self.local[executable][arguments]

            yield self.local['docker'][
                'push',
                Build.get_full_name(args.name),
            ]

    class Deploy(Local):
        """deploy an image container"""

        def prepare(self, args):
            command = self.local['eb']['deploy']

            # specify environment
            if args.target == 'production':
                command = command['appy-reviews-pro']
            else:
                command = command['appy-reviews-dev']

            if args.label:
                return command['-l', args.label[0]]
            return command


class LocalContainer(Local):

    @classmethod
    def run(cls, *args, **kwargs):
        docker = cls.local['docker']
        return docker[
            'run',
            '--rm',
            '--net=host',
            '-v', f'{SRC_PATH}:/app',
        ].bound_command(
            *args
        ).bound_command(
            *(
                f'-e{key}' if value is None else f'-e{key}={value}'
                for (key, value) in kwargs.items()
            )
        )['appyreviews_web']


class DbLocal(LocalContainer):

    EXAMPLE_DATABASE_URL = 'postgres://appy_reviews:PASSWORD@localhost:5433/appy_reviews'

    @classmethod
    def get_database_url(cls, args):
        if args.database_url:
            return args.database_url

        if os.getenv('DATABASE_URL'):
            return None

        args.__parser__.error(
            'DATABASE_URL must be specified by argument or environment\n\n'
            'For example:\n'
            f'\tmanage db --database-url={cls.EXAMPLE_DATABASE_URL}\n'
            'or:\n'
            f'\tDATABASE_URL={cls.EXAMPLE_DATABASE_URL} manage db'
        )

    @classmethod
    def manage(cls, args, *args_, **kwargs):
        return cls.run(
            *args_,
            DATABASE_URL=cls.get_database_url(args),
            **kwargs
        )['./manage.py']

    def __init__(self, parser):
        parser.add_argument(
            '-v', '--verbosity',
            type=int,
            default=1,
        )
        parser.add_argument(
            '--db', '--database-url',
            dest='database_url',
            metavar='database-url',
            help=f"Database URL (e.g.: {self.EXAMPLE_DATABASE_URL})",
        )


@Appy.register
class Develop(DbLocal):
    """create the appy-reviews container in development mode and run it
    in the background

    """
    DEFAULT_NAMETAG = 'appyreviews_web_1'

    def __init__(self, parser):
        super().__init__(parser)

        parser.add_argument(
            '-n', '--name',
            default=self.DEFAULT_NAMETAG,
            help=f'Image name/tag (default: {self.DEFAULT_NAMETAG})',
        )
        parser.add_argument(
            '-b', '--build',
            action='store_true',
            help="(re-)build image before container creation",
        )

    def prepare(self, args):
        if args.build:
            yield self.local['docker'][
                'build',
                '--build-arg', 'TARGET=development',
                '-t', 'appyreviews_web',
                ROOT_PATH,
            ]

        yield self.run(
            '-d',
            '--name', args.name,
            DATABASE_URL=self.get_database_url(args),
            APPY_DEBUG=1,
            SMTP_USER=None,
            SMTP_PASSWORD=None,
        )

    class Control(Local):
        """control the appy-reviews supervisor process"""

        commands = ('start', 'stop', 'restart')

        def __init__(self, parser):
            parser.add_argument(
                'mcmd',
                metavar='command',
                choices=self.commands,
                help="{{{}}}".format(', '.join(self.commands)),
            )

        def prepare(self, args):
            return self.local['docker'][
                'exec',
                args.name,
                'supervisorctl',
                '-c',
                '/etc/supervisor/supervisord.conf',
                args.mcmd,
                'webapp',
            ]

    class DjManage(Local):
        """manage the appy-reviews django project"""

        def __init__(self, parser):
            parser.add_argument(
                'mcmd',
                metavar='command',
                help="django management command",
            )
            parser.add_argument(
                'remainder',
                metavar='command arguments',
                nargs=argparse.REMAINDER,
            )

        def prepare(self, args):
            return self.local['docker'][
                'exec',
                '-it',
                args.name,
                './manage.py',
                args.mcmd,
                args.remainder,
            ]


@Appy.register
class Db(DbLocal):
    """manage database via local container"""

    commands = (
        'showmigrations',
        'makemigrations',
        'migrate',
    )

    def __init__(self, parser):
        super().__init__(parser)

        parser.add_argument(
            'mcmd',
            metavar='command',
            choices=self.commands,
            help="{{{}}}".format(', '.join(self.commands)),
        )
        parser.add_argument(
            'remainder',
            metavar='command arguments',
            nargs=argparse.REMAINDER,
        )

    def prepare(self, args):
        return self.manage(args, '-it')[args.mcmd, args.remainder]


@Appy.register
class Etl(DbLocal):
    """manage survey data"""

    class Apps(Local):
        """map wufoo data into appy"""

        def __init__(self, parser):
            parser.add_argument(
                'subcommand',
                choices=('execute', 'inspect',),
                default='execute',
                nargs='?',
                help="either execute command, or inspect state of system only, "
                     "do not load applications (default: execute)",
            )

        def prepare(self, args):
            return Etl.manage(args)[
                'loadapps',
                '-s', '_2018',
                '2018',
                args.subcommand,
            ]

    class Wufoo(Local):
        """load initial survey data"""

        def __init__(self, parser):
            parser.add_argument(
                '--csv',
                action='store_true',
                default=False,
                dest='csv_cache',
                help="cache data in local CSV files",
            )

        def prepare(self, args, parser):
            if not os.getenv('WUFOO_API_KEY'):
                parser.error(
                    'WUFOO_API_KEY must be specified by environment\n\n'
                    'For example:\n'
                    '\tWUFOO_API_KEY=xx-xx-xx DATABASE_URL=... manage etl bootstrap'
                )

            # FIXME: This doesn't work, rather only when command is run
            # FIXME: by user in shell
            return Etl.manage(
                args,
                WUFOO_API_KEY=None,
            )[
                'loadwufoo',
                '-v', args.verbosity,
                '-f', '"^2018 "',
                ('output' if args.csv_cache else '-'),
            ]


@Appy.register
class Reviewer(DbLocal):
    """manage reviewers"""

    class Invite(Local):
        """invite a new or existing reviewer"""

        def __init__(self, parser):
            parser.add_argument(
                'remainder',
                metavar='command arguments',
                nargs='*',
                help="arguments to pass to sendconfirm (preceeded by --)",
            )

        def prepare(self, args):
            return Reviewer.manage(
                args,
                SMTP_USER=None,
                SMTP_PASSWORD=None,
            )[
                'sendinvite',
                args.remainder,
            ]


@Appy.register
class Static(LocalContainer):
    """generate static pages"""

    @localmethod
    def closed(self):
        """render closed.html and upload it to the S3 bucket as index.html"""
        return (
            # render to stdout
            self.run()[
                './manage.py',
                'makestatic',
                'closed',
                'program_year={settings.REVIEW_PROGRAM_YEAR}',
            ] |
            # pipe rendering to awscli
            # and upload to bucket
            self.local['aws'][
                's3',
                'cp',
                '-',
                's3://review.dssg.io/index.html',
                '--acl', 'public-read',
                '--content-type', 'text/html',
            ]
        )


@Appy.register
class DNS(Local):
    """manage site DNS"""

    class StrEnum(str, enum.Enum):

        def __str__(self):
            return self.value

    class Domain(StrEnum):

        zone = 'dssg.io.'
        fqdn = f'review.{zone}'

    class CName(StrEnum):

        live = 'pro-reviews-dssg.us-west-2.elasticbeanstalk.com'
        static = 'd2va83k0l3phq8.cloudfront.net'

    class profile_hint(contextlib.AbstractContextManager):
        """Print a helpful hint about using the correct AWS profile in
        the event of an execution error.

        Note that the exception is not suppressed.

        """
        def __exit__(self, _exc_type, exc_value, _exc_tb):
            if isinstance(exc_value, Local.local.ProcessExecutionError):
                print(
                    'Hint: specify your AWS profile for the DSSG account:\n'
                    '\n'
                    '\tAWS_PROFILE=dssg manage dns ...\n',
                    file=sys.stderr,
                )

    @classmethod
    def prepare_hosted_zone(cls):
        # AWS_PROFILE=dssg
        return cls.local['aws'][
            'route53',
            'list-hosted-zones',
            '--query', f"HostedZones[?Name == '{cls.Domain.zone}']",
        ] | cls.local['jq'][
            '.[0].Id',
        ]

    @localmethod
    def check(self):
        """look up the site's current DNS setting"""
        with self.profile_hint():
            (_retcode, output, _error) = yield (
                self.prepare_hosted_zone() |
                self.local['xargs'][
                    '-I', '{}',
                    'aws',
                    'route53',
                    'list-resource-record-sets',
                    '--hosted-zone-id', '{}',
                    '--query', f"ResourceRecordSets[?Name == '{self.Domain.fqdn}']",
                ] | self.local['jq'][
                    '-r',
                    '.[0].ResourceRecords[0].Value',
                ]
            )

        if output is None:
            # dry run
            return

        cname = output.strip()
        for value in self.CName:
            if value == cname:
                print(value.name.upper() | colors.info)
                break
        else:
            print('UNKNOWN' | colors.warn)

    @localmethod('target', choices=CName.__members__, help="the CNAME value to set")
    def set(self, args):
        """set the site's DNS to either the live server or the static
        content bucket

        """
        with self.profile_hint():
            yield self.prepare_hosted_zone() | self.local['xargs'][
                '-I', '{}',
                'aws',
                'route53',
                'change-resource-record-sets',
                '--hosted-zone-id', '{}',
                '--change-batch', '''{
                    "Changes": [{
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": "%s",
                            "Type": "CNAME",
                            "TTL": 300,
                            "ResourceRecords": [{"Value": "%s"}]
                        }
                    }]
                }''' % (self.Domain.fqdn, self.CName[args.target]),
            ]
