import abc
import collections


class SurveyPresentationFunction(abc.ABC):

    do_not_call_in_templates = True

    def __init__(self):
        self.__name__ = self.__class__.__name__

    def __iter__(self):
        yield self

    @abc.abstractmethod
    def __call__(self, entry):
        pass


class CoalesceKeys(SurveyPresentationFunction):

    def __init__(self, *keys, sep=', '):
        super().__init__()
        self.keys = keys
        self.sep = sep

    def itervalues(self, entry):
        for key in self.keys:
            if entry.get(key):
                yield key

    def itervaluesmulti(self, entry):
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
                yield key

    def __call__(self, entry):
        getter = self.itervaluesmulti if hasattr(entry, 'getlist') else self.itervalues
        return self.sep.join(getter(entry))

    def __repr__(self):
        return f'{self.__name__}({{keys}}, {self.sep!r})'.format(
            keys=', '.join(repr(key) for key in self.keys),
        )
