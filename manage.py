import argparse
import os
from pathlib import Path

from argcmdr import Local, LocalRoot
from descriptors import cachedclassproperty


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
            '--target',
            choices=('development', 'production'),
            default='production',
            help="Target environment (default: production)",
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
        parser.add_argument(
            '-l', '--login',
            action='store_true',
            help="log in to AWS ECR",
        )

    def prepare(self, args):
        if args.login and not args.push:
            args.__parser__.error("will not log in outside of push operation")

        yield self.local['docker'][
            'build',
            '--build-arg', f'TARGET={args.target}',
            '-t', args.name,
            '-t', self.get_full_name(args.name),
            ROOT_PATH,
        ]

        if args.push:
            yield from args.__children__.push.prepare(args)

        if args.deploy:
            yield args.__children__.deploy.prepare(args)

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
                if args.show_commands:
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
            return self.local['eb']['deploy']


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
    def manage(cls, args, **kwargs):
        return cls.run(
            DATABASE_URL=cls.get_database_url(args),
            **kwargs
        )['./manage.py']

    def __init__(self, parser):
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
        return self.manage(args)[args.mcmd, args.remainder]


@Appy.register
class Etl(DbLocal):
    """manage survey data"""

    class Apps(Local):
        """map wufoo data into appy"""

        def prepare(self, args):
            return Etl.manage(args)[
                'loadapps',
                '-s', '_2018',
                '-y', '2018',
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

        def prepare(self, args):
            if not os.getenv('WUFOO_API_KEY'):
                args.__parser__.error(
                    'WUFOO_API_KEY must be specified by environment\n\n'
                    'For example:\n'
                    '\tWUFOO_API_KEY=xx-xx-xx DATABASE_URL=... manage etl bootstrap'
                )

            return Etl.manage(
                args,
                WUFOO_API_KEY=None,
            )[
                'loadwufoo',
                '-f', '"^2018 "',
                '-s', '2018-stream',
                ('output' if args.csv_cache else '-'),
            ]
