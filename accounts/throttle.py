"""Small fixed-window rate limiter on Django's cache."""
import time
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse


def _k(scope, ident):
    return f"throttle:{scope}:{ident}"


def failures(scope, ident):
    return cache.get(_k(scope, ident), 0)


def add_failure(scope, ident, window):
    key = _k(scope, ident)
    if cache.add(key, 1, window):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        return 1


def reset(scope, ident):
    cache.delete(_k(scope, ident))


def is_blocked(scope, ident, limit):
    return failures(scope, ident) >= limit


def limit_requests(scope, limit, window):
    """Decorator: at most `limit` requests per `window` seconds per client IP."""
    def deco(view):
        @wraps(view)
        def wrapper(request, *a, **kw):
            ident = request.META.get("REMOTE_ADDR", "?")
            if add_failure(scope, ident, window) > limit:
                return HttpResponse("Too many requests. Please wait and try again.", status=429)
            return view(request, *a, **kw)
        return wrapper
    return deco
