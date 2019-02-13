import csv
import enum
import functools
import itertools
import os
import pathlib
import re
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from plumbum import local
from pyfoo import PyfooAPI


class Credentials(str, enum.Enum):
    """str-Enum of Wufoo API credentials"""

    account_name = 'datascience'
    api_key = os.getenv('WUFOO_API_KEY', '')

    def __str__(self):
        return self.value


# regular expressions to identify forms to load
# and to capture their canonical names (case-insensitive)
FORMS = (
    # recommendation form
    r'^(\d+) dssg fellow (recommendation) form$',

    # application form(s)
    r'^(\d+) dssg fellowship (application)'
    r'(?:(?:[- ]+part)? (\d))?$',

    # reviewer form
    r'^(\d+) dssg application (reviewer) registration$',
)

ENTRY_PAGE_SIZE = 100  # (Also the API default)
# NOTE: Also, the Wufoo API backend appears to ignore this
# parameter ANYWAY....


class Command(BaseCommand):

    help = "Load DSSG program application data from Wufoo"

    def add_arguments(self, parser):
        parser.add_argument(
            'target',
            default='.',
            metavar='path',
            nargs='?',
            help="Path to a directory into which to write CSV file output (optional). "
                 "When path is -, will instead use standard input/output to write to "
                 "the database.",
        )
        parser.add_argument(
            '-f', '--filter',
            action='append',
            default=[],
            dest='filters',
            metavar='filter',
            help="Regular expression(s) with which to filter forms by name.",
        )
        parser.add_argument(
            '-n', '--no-database',
            action='store_false',
            default=True,
            dest='write_to_db',
            help="Do not write data to database",
        )
        parser.add_argument(
            '-s', '--suffix',
            help="Suffix to apply to written database tables (defaults to inferred year).",
        )
        parser.add_argument(
            '--no-suffix',
            action='store_false',
            default=True,
            dest='apply_suffix',
            help="Apply no database table suffix.",
        )
        parser.add_argument(
            '--entity-id', '--id',
            default='EntryId',
            dest='entity_id_field',
            help="Database column to set as primary key (default: EntryId)",
        )
        parser.add_argument(
            '--no-entity-id',
            action='store_false',
            default=True,
            dest='apply_pk',
            help="Set no primary key",
        )
        parser.add_argument(
            '--append',
            action='store_true',
            help="Append rows to any existing database tables (rather than overwrite).",
        )
        parser.add_argument(
            '--recreate',
            action='store_true',
            help="Recreate table schema rather than merely truncating and repopulating.",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.verbosity = None

    def handle(self, target='.', filters=(), write_to_db=True,
               apply_suffix=True, suffix=None, append=False,
               entity_id_field='EntryId', apply_pk=True,
               recreate=False,
               verbosity=1, **_options):
        self.verbosity = verbosity

        if target == '-' and not write_to_db:
            raise CommandError("Can only write to standard I/O without database – nothing to do")

        csvsql = local['csvsql']
        client = PyfooAPI(*Credentials)

        for (year, name, form) in stream_forms(client, filters):
            entries = stream_entries(form)
            fields = list(stream_fields(form))

            # Peak ahead for entry column names
            try:
                head = next(entries)
            except StopIteration:
                head = None
            else:
                entries = itertools.chain((head,), entries)

            # Write to disk
            if target == '-':
                data_paths = (None, None)
                streams = (
                    functools.partial(self.write_entries_csv, head, entries),
                    functools.partial(self.write_fields_csv, head, fields),
                )
            else:
                data_paths = self.write_disk(target, name, head, entries, fields)
                streams = (None, None)

            # Write to database
            if not write_to_db or not head:
                continue

            table_names = [f'survey_{name}',
                           f'survey_{name}_fields']
            if apply_suffix:
                table_suffix = suffix or year
                table_names = [table_name + f'_{table_suffix}'
                               for table_name in table_names]

            table_col_defns = [
                # entries table columns
                ', '.join(
                    (
                        f'"{field_name}" ' +
                        ('citext' if re.search(r'^Field\d+$', field_name) else 'varchar')
                    )
                    for field_name in head
                ),

                # fields table columns
                '"field_id" varchar, "field_title" varchar',
            ]

            for (table_name, table_col_defn, data_path, stream, table_apply_pk) in zip(
                    table_names, table_col_defns, data_paths, streams, (apply_pk, False)):
                table_name_tmp = f'{table_name}_tmp'

                with connection.cursor() as cursor:
                    cursor.execute(f"select to_regclass('{table_name}')")
                    (result,) = cursor.fetchone()
                    table_exists = bool(result)

                direct_write = append or not table_exists

                load_command = csvsql[
                    '--db', settings.DATABASE_URL,
                    '--insert',
                    '--no-create',
                    '--no-constraints',
                    '--no-inference',  # inference incorrectly truncates and
                                       # casts document URIs to date
                ]

                if direct_write:
                    load_command = load_command[
                        '--table', table_name,
                        '--db-schema', settings.DATABASE_SCHEMA,
                    ]

                    if recreate and table_exists:
                        # tear down old table
                        self.execute_sql(f'drop table "{table_name}"')
                        table_exists = False
                else:
                    load_command = load_command[
                        '--table', table_name_tmp,
                    ]

                    self.execute_sql(f'create table {table_name_tmp} '
                                     f'({table_col_defn})',
                                     "creating temporary table", table_name_tmp)

                if not table_exists:
                    self.execute_sql(f'create table {settings.DATABASE_SCHEMA}.{table_name} '
                                     f'({table_col_defn})')

                    if table_apply_pk:
                        self.execute_sql(f'alter table "{table_name}" '
                                         f'add primary key ("{entity_id_field}")')

                if data_path:
                    load_command(data_path)
                else:
                    self.report("streaming to database table:", (table_name if direct_write
                                                                 else table_name_tmp))
                    load_process = load_command.popen(
                        '-',
                        stdin=subprocess.PIPE,
                        encoding='utf-8',
                    )
                    with load_process.stdin as pipe:
                        stream(pipe)
                    try:
                        load_process.wait(180)
                    except subprocess.TimeoutExpired:
                        load_process.kill()
                        raise

                if not direct_write:
                    try:
                        self.execute_sql('begin')

                        if table_exists:
                            if recreate:
                                # tear down old table
                                self.execute_sql(f'drop table "{table_name}"')

                                # set up new table
                                self.execute_sql(
                                    f'create table {settings.DATABASE_SCHEMA}.{table_name} '
                                    f'({table_col_defn})'
                                )

                                if table_apply_pk:
                                    self.execute_sql(f'alter table "{table_name}" '
                                                     f'add primary key ("{entity_id_field}")')
                            else:
                                self.execute_sql(f'truncate table only {table_name}')

                        self.execute_sql(f'insert into {table_name} '
                                         f'select * from {table_name_tmp}')

                        self.execute_sql(f'drop table {table_name_tmp}')
                    except BaseException:
                        try:
                            self.execute_sql('rollback')
                        except BaseException:
                            pass

                        raise
                    else:
                        self.execute_sql('commit')

    def execute_sql(self, sql, *comments):
        if comments:
            self.report(*comments, minlevel=3)

        self.report(sql, minlevel=3)

        with connection.cursor() as cursor:
            cursor.execute(sql)

    def report(self, *contents, minlevel=2):
        if self.verbosity >= minlevel:
            self.stdout.write(' '.join(str(item) for item in contents))

    def write_entries_csv(self, head, entries, outfile):
        writer = csv.DictWriter(outfile, tuple(head))
        writer.writeheader()
        for (count, entry) in enumerate(entries, 1):
            writer.writerow({
                key: (value.strip() if isinstance(value, str) else value)
                for (key, value) in entry.items()
            })

        self.report("\twriting entries:", count)

    def write_fields_csv(self, head, fields, outfile):
        writer = csv.writer(outfile, lineterminator=os.linesep)
        writer.writerow(['field_id', 'field_title'])
        for (count, (field_id, field_title)) in enumerate(fields, 1):
            if field_id and field_id in head:
                writer.writerow([field_id, field_title.strip()])

        self.report("\twriting fields:", count)

    def write_disk(self, target, name, head, entries, fields):
        """Write CSV to disk."""
        data_file_name = name + '.csv'
        data_path = pathlib.Path(target) / data_file_name
        with data_path.open('w') as outfile:
            if head is not None:
                self.write_entries_csv(head, entries, outfile)

        field_file_name = name + '_fields.csv'
        field_path = pathlib.Path(target) / field_file_name
        with field_path.open('w') as outfile:
            if head is not None:
                self.write_fields_csv(head, fields, outfile)

        return (data_path, field_path)


def stream_fields(form):
    for field in form.fields:

        if field.SubFields:
            for subfield in field.SubFields:
                yield (subfield.ID, subfield.Label)

            continue

        yield (field.ID, field.Title)


def stream_entries(form, page_size=ENTRY_PAGE_SIZE):
    """Generate form entries from given Form.

    Wraps `get_entries` to handle pagination.

    """
    for page_start in itertools.count(step=page_size):
        entries = form.get_entries(page_start, page_size)
        yield from entries

        if len(entries) < page_size:
            break


def stream_forms(client, filters=(), name_expressions=FORMS):
    """Generate forms whose names match regular expression(s)."""
    for form in client.forms:
        for name_expression in name_expressions:
            match = re.search(name_expression, form.Name, re.I)

            if match:
                # Form is a candidate
                if all(re.search(filter_, form.Name, re.I) for filter_ in filters):
                    # This is our form!
                    (year, *names) = match.groups()
                    name = '_'.join(names).lower()
                    assert name, (
                        "Failed to capture form name from identifying regular "
                        f"expression {name_expression!r}"
                    )
                    yield (year, name, form)

                # No need to continue with this form
                break
