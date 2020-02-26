import collections

from django.apps import apps
from django.contrib.admin.utils import NestedObjects
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, transaction
from terminaltables import AsciiTable

from review import models


RELATED_OBJECTS_TO_MERGE = {
    models.InterviewAssignment,
    models.ReviewerConcession,
    models.Application,
}


def get_model_from_signature(signature):
    (app_name, model_name) = signature.split('.')
    return apps.get_model(app_name, model_name)


class Command(BaseCommand):

    help = ("Merge multiple accounts into one. "
            "E.g.: mergeaccounts reviewer --from nome@email.com --to name@email.com")

    def add_arguments(self, parser):
        parser.add_argument(
            'account_type',
            choices=('applicant', 'reviewer'),
            help="account type",
        )
        parser.add_argument(
            '--from',
            action='append',
            dest='from_emails',
            metavar='EMAIL',
            help="account(s) to merge from",
        )
        parser.add_argument(
            '--to',
            dest='to_email',
            metavar='EMAIL',
            help="account to merge into",
        )
        parser.add_argument(
            '-f', '--force',
            action='store_true',
            help="do not prompt for confirmation",
        )

    def handle(self, account_type, from_emails, to_email, force, verbosity, **options):
        if not from_emails:
            raise CommandError("at least one source account required: --from")

        if not to_email:
            raise CommandError("exactly one destination account required: --to")

        model = apps.get_model('review', account_type)

        # FIXME: as soon as applicant.email is case-insensitive, can/should use below:
        # from_instances = model.objects.filter(email__in=from_emails)
        pattern = '|'.join(from_emails)
        from_instances = model.objects.filter(email__iregex=rf'^{pattern}$')
        if len(from_instances) != len(from_emails):
            raise CommandError("account look-up error")

        try:
            # FIXME: ditto
            # to_instance = model.objects.get(email=to_email)
            to_instance = model.objects.get(email__iexact=to_email)
        except model.DoesNotExist:
            raise CommandError("account look-up error")

        to_merge = RELATED_OBJECTS_TO_MERGE.copy()

        if model is models.Reviewer:
            if to_instance.concession:
                if verbosity >= 1:
                    self.stdout.write(
                        f'[INFO] {models.ReviewerConcession._meta.verbose_name} '
                        f'– {to_instance.concession} – exists (will not overwrite)'
                    )
                    self.stdout.write('')

                to_merge.remove(models.ReviewerConcession)

        try:
            with transaction.atomic():
                self.merge_accounts(account_type,
                                    from_instances,
                                    to_instance,
                                    to_merge,
                                    force,
                                    verbosity)
        except KeyboardInterrupt:
            self.stdout.write('aborted')

    def merge_accounts(self, account_type, from_instances, to_instance, to_merge, force, verbosity):
        # TODO: is it about as common as anything that same-year applications
        # TODO must (also) be merged?
        #
        # TODO: currently this doesn't help with that; but, unclear that that's
        # TODO: precisely something we'd want to automate.

        (updated, ignored) = self.update_related(account_type,
                                                 from_instances,
                                                 to_instance,
                                                 to_merge)

        if verbosity >= 1:
            table = AsciiTable(
                (
                    [('related item', 'count')] +
                    [
                        (related_model._meta.verbose_name, count)
                        for (related_model, count) in updated.items()
                    ]
                ),
                'items reassigned',
            )
            self.stdout.write(table.table)
            self.stdout.write('')

        if verbosity >= 1 or not force:
            self.stdout.write("the following items will be DESTROYED:")
            self.stdout.write('')
            for related_instance in ignored:
                self.stdout.write(f"✗ {related_instance._meta.verbose_name}: {related_instance}")
            self.stdout.write('')

        # NOTE: Unnecessary to check in here so long as prompt before end
        # if not force:
        #     input("press <enter> to confirm ...")

        delete_count = 0
        deleted = collections.defaultdict(int)

        for from_instance in from_instances:
            (delete_count1, deleted1) = from_instance.delete()

            delete_count += delete_count1
            for (deleted_model, count) in deleted1.items():
                deleted[deleted_model] += count

        if verbosity >= 1:
            table = AsciiTable(
                (
                    [('item', 'count')] +
                    [
                        (
                            get_model_from_signature(deleted_model)._meta.verbose_name,
                            count,
                        )
                        for (deleted_model, count) in deleted.items()
                        if count > 0
                    ]
                ),
                f'{delete_count} items deleted',
            )
            self.stdout.write(table.table)
            self.stdout.write('')

        if not force:
            input("press <enter> to save changes ...")

    # NOTE: django.db.models.deletion.Collector is arguably more general-purpose,
    # NOTE: and straight-forward; however, it missed ReviewerConcession, (perhaps
    # NOTE: because related_name is +).
    #
    # NOTE: It's unclear if NestedObjects from contrib will always serve our
    # NOTE: purpose; so, this is left for future use.

    def _update_related_basic(self, account_type, from_instances, to_instance, to_merge):
        ignored = []
        updated = collections.defaultdict(int)

        collector = Collector(using=DEFAULT_DB_ALIAS)
        collector.collect(from_instances)
        for (related_model, related_instance) in collector.instances_with_model():
            if related_model in to_merge:
                setattr(related_instance, account_type, to_instance)
                related_instance.save(update_fields=(account_type,))
                updated[related_model] += 1
            else:
                ignored.append(related_instance)

        return updated, ignored

    def _update_related_nested(self, account_type, from_instances, to_instance, to_merge):
        ignored = []
        updated = collections.defaultdict(int)

        collector = NestedObjects(using=DEFAULT_DB_ALIAS)
        collector.collect(from_instances)

        # FIXME: could handle multiple sets but will be good to test format returned by nested()
        try:
            (from_instance, related_instances) = collector.nested()
        except ValueError:
            raise CommandError("related item look-up error")

        ignored.append(from_instance)
        for related_instance in related_instances:
            if isinstance(related_instance, list):
                # NOTE: This should be a collection of related-related-objects,
                # NOTE: and as such only a concern if their link is deleted
                #
                # FIXME: worth bothering?
                pass
            elif related_instance._meta.model in to_merge:
                setattr(related_instance, account_type, to_instance)
                related_instance.save(update_fields=(account_type,))
                updated[related_instance._meta.model] += 1
            else:
                ignored.append(related_instance)

        return updated, ignored

    update_related = _update_related_nested
