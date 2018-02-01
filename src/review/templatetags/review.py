import collections
import itertools

from django import template
from django.template.defaultfilters import stringfilter


register = template.Library()


@register.filter
@stringfilter
def repeat(value, count, join=''):
    return join.join(itertools.repeat(value, count))


@register.filter
def lookup(hash_, key):
    return hash_.get(key) if hash_ else None


@register.filter
def multilookup(hash_, key):
    if hash_:
        if isinstance(key, (str, bytes)) or not isinstance(key, collections.Sequence):
            index = -1
        else:
            (key, index) = key

        values = hash_.getlist(key)

        try:
            return values[index]
        except IndexError:
            pass


@register.filter
def makelist(value):
    if isinstance(value, (str, bytes)) or not isinstance(value, collections.Sequence):
        return (value,)
    return value


@register.simple_tag(takes_context=True)
def render(context, content, **kwargs):
    return template.Template(content).render(
        template.Context(kwargs) if kwargs else context
    )
