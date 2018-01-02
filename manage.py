import os
from pathlib import Path

from argcmdr import Command, RootCommand
from plumbum import local


ROOT_PATH = Path(__file__).parent.resolve()
SRC_PATH = ROOT_PATH / 'src'

DOCKER = local['docker']
ICMD = DOCKER[
    'run',
    '--rm',
    '--net=host',
    '-v', f'{SRC_PATH}:/app',
    'appyreviews_web',
]


class Appy(RootCommand):
    """appy management"""


@Appy.register
class Etl(Command):
    """manage survey data"""

    class Apps(Command):
        """map wufoo data into appy"""

        def __call__(self, args):
            ICMD(
                'env',
                'DATABASE_URL=' + os.environ['DATABASE_URL'],
                './manage.py',
                'loadapps',
                '-s', '_2018',
                '-y', '2018',
            )

    class Wufoo(Command):
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

        def __call__(self, args):
            if args.database_url:
                database_url = args.database_url
            elif os.getenv('DATABASE_URL'):
                database_url = '$DATABASE_URL'
            else:
                args.parser.error(
                    'DATABASE_URL must be specified by argument or environment\n\n'
                    'For example:\n'
                    f'\tmanage etl bootstrap --database-url={self.EXAMPLE_DATABASE_URL}\n'
                    'or:\n'
                    f'\tDATABASE_URL={self.EXAMPLE_DATABASE_URL} WUFOO_API_KEY=xx-xx-xx manage etl bootstrap'
                )

            if not os.getenv('WUFOO_API_KEY'):
                args.parser.error(
                    'WUFOO_API_KEY must be specified by environment\n\n'
                    'For example:\n'
                    '\tWUFOO_API_KEY=xx-xx-xx DATABASE_URL=... manage etl bootstrap'
                )

            target = 'output' if args.csv_cache else '-'
            ICMD(
                'env',
                f'DATABASE_URL={database_url}',
                'WUFOO_API_KEY=$WUFOO_API_KEY',
                './manage.py',
                'loadwufoo',
                '-f', '"^2018 "',
                target,
            )
