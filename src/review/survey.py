"""Presentation helpers for survey form data.

(For use in the fieldspec at REVIEW_APPLICATION_FIELDS.)

"""
import abc
import collections


class SurveyPresentationFunction(abc.ABC):
    """Presentation helper for survey form data."""

    # Django template will by default automatically attempt to call
    # *any* callable upon inspection/evaluation, and silently replace
    # with empty string upon error
    do_not_call_in_templates = True

    def __init__(self):
        # template may inspect callable object looking for __name__
        self.__name__ = self.__class__.__name__

    # backwards support for fieldspec without these helpers
    def __iter__(self):
        yield self

    # helper is (otherwise!) "just" a callable
    @abc.abstractmethod
    def __call__(self, entry):
        pass


class Coalesce(SurveyPresentationFunction):

    item_index = 1

    @classmethod
    def get_value(cls, item):
        return item[cls.item_index]

    def __init__(self, *keys, sep=', '):
        super().__init__()
        self.keys = keys
        self.sep = sep

    def iteritems(self, entry):
        for key in self.keys:
            value = entry.get(key)
            if value:
                yield (key, value)

    def iteritems_multi(self, entry):
        for key in self.keys:
            if isinstance(key, (str, bytes)) or not isinstance(key, collections.Sequence):
                index = -1
            else:
                (key, index) = key

            values = entry.getlist(key)

            try:
                value = values[index]
            except IndexError:
                value = None

            if value:
                yield (key, value)

    def __call__(self, entry):
        getter = self.iteritems_multi if hasattr(entry, 'getlist') else self.iteritems
        return self.sep.join(self.get_value(item) for item in getter(entry))

    def __repr__(self):
        return f'{self.__name__}({{keys}}, {self.sep!r})'.format(
            keys=', '.join(repr(key) for key in self.keys),
        )


class CoalesceKeys(Coalesce):

    item_index = 0
