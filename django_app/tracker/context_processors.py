from __future__ import annotations

from types import SimpleNamespace

from django.middleware.csrf import get_token


def template_compat(request):
    # Provide a few legacy template aliases.
    # - request.args -> querystring
    # - request.form -> post body (or empty-ish on GET)
    try:
        setattr(request, 'args', request.GET)
        setattr(request, 'form', request.POST if request.method == 'POST' else request.GET)
    except Exception:
        # Extremely defensive: never break rendering if request is immutable.
        pass

    return {
        "current_user": getattr(request, "user", None),
        "csrf_token": get_token(request),
        "SimpleNamespace": SimpleNamespace,
    }
