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


@register.simple_tag(takes_context=True)
def render(context, content, **kwargs):
    return template.Template(content).render(
        template.Context(kwargs) if kwargs else context
    )
