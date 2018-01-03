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

    def prepare(self, args):
        yield self.local['docker'][
            'build',
            '--build-arg', f'TARGET={args.target}',
            '-t', args.name,
            '-t', self.get_full_name(args.name),
            ROOT_PATH,
        ]

        if args.push:
            yield args.__children__.push.prepare(args)

        if args.deploy:
            yield args.__children__.deploy.prepare(args)

    class Push(Local):
        """push already-built image to registry"""

        def prepare(self, args):
            return self.local['docker'][
                'push',
                Build.get_full_name(args.name),
            ]

    class Deploy(Local):
        """deploy an image container"""

        def prepare(self, args):
            return self.local['eb']['deploy']


@Appy.register
class Etl(Local):
    """manage survey data"""

    @cachedclassproperty
    def icmd(cls):
        docker = cls.local['docker']
        return docker[
            'run',
            '--rm',
            '--net=host',
            '-v', f'{SRC_PATH}:/app',
            'appyreviews_web',
        ]

    class Apps(Local):
        """map wufoo data into appy"""

        def prepare(self, args):
            return Etl.icmd[
                'env',
                'DATABASE_URL=' + os.environ['DATABASE_URL'],
                './manage.py',
                'loadapps',
                '-s', '_2018',
                '-y', '2018',
            ]

    class Wufoo(Local):
        """load initial survey data"""

        EXAMPLE_DATABASE_URL = 'postgres://appy_reviews:PASSWORD@localhost:5433/appy_reviews'

        def __init__(self, parser):
            parser.add_argument(
                '--csv',
                action='store_true',
                default=False,
                dest='csv_cache',
                help="cache data in local CSV files",
            )
            parser.add_argument(
                '--database-url',
                help=f"Database URL (e.g.: {self.EXAMPLE_DATABASE_URL})",
            )

        def prepare(self, args):
            if args.database_url:
                database_url = args.database_url
            elif os.getenv('DATABASE_URL'):
                database_url = '$DATABASE_URL'
            else:
                args.__parser__.error(
                    'DATABASE_URL must be specified by argument or environment\n\n'
                    'For example:\n'
                    f'\tmanage etl bootstrap --database-url={self.EXAMPLE_DATABASE_URL}\n'
                    'or:\n'
                    f'\tDATABASE_URL={self.EXAMPLE_DATABASE_URL} WUFOO_API_KEY=xx-xx-xx manage etl bootstrap'
                )

            if not os.getenv('WUFOO_API_KEY'):
                args.__parser__.error(
                    'WUFOO_API_KEY must be specified by environment\n\n'
                    'For example:\n'
                    '\tWUFOO_API_KEY=xx-xx-xx DATABASE_URL=... manage etl bootstrap'
                )

            target = 'output' if args.csv_cache else '-'
            return Etl.icmd[
                'env',
                f'DATABASE_URL={database_url}',
                'WUFOO_API_KEY=$WUFOO_API_KEY',
                './manage.py',
                'loadwufoo',
                '-f', '"^2018 "',
                '-s', '2018-stream',
                target,
            ]
