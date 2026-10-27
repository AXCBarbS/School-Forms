from django import template

register = template.Library()


@register.filter
def field(form, name):
    return form[name]


@register.filter
def pick(mapping, key):
    return mapping.get(key, ("", "", ""))


@register.filter
def idx(seq, i):
    try:
        return seq[i]
    except (IndexError, TypeError):
        return ""


@register.filter
def dictget(mapping, key):
    return mapping[key]
