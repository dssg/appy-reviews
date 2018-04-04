import argparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.template import loader, TemplateDoesNotExist


def keypair(arg):
    return arg.split('=', 1)


class Command(BaseCommand):

    help = "Render the specified template"

    def add_arguments(self, parser):
        parser.add_argument(
            'template_name',
            metavar='template',
            help="Template name (such as closed, closed.html or review/closed.html)",
        )
        parser.add_argument(
            'context',
            metavar='context key-value pairs',
            nargs=argparse.REMAINDER,
            type=keypair,
            help="Rendering context in the form: var_a=Joe var_b=\"some text\". "
                 "Use {} to interpolate settings: program_year={settings.REVIEW_PROGRAM_YEAR}",
        )

    def handle(self, template_name, context, verbosity, **options):
        tried = []
        while True:
            try:
                template = loader.get_template(template_name)
            except TemplateDoesNotExist:
                tried.append(template_name)
                if not template_name.endswith('.html'):
                    template_name += '.html'
                elif '/' not in template_name:
                    template_name = 'review/' + template_name
                else:
                    raise CommandError("no such template " + ' or '.join(tried))
            else:
                break

        if verbosity >= 2:
            self.stderr.write(template_name)

        self.stdout.write(
            template.render({
                name: value.format(settings=settings)
                for (name, value) in context
            })
        )
