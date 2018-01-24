import itertools

from django import template
from django.template.defaultfilters import stringfilter


register = template.Library()


@register.filter
@stringfilter
def repeat(value, count, join=''):
    return join.join(itertools.repeat(value, count))
