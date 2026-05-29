from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib import messages
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from jinja2 import Environment, pass_context


def environment(**options: Any) -> Environment:
    env = Environment(**options)

    def _strftime(value, fmt: str = "%Y-%m-%d") -> str:
        if value is None:
            return ""
        try:
            return value.strftime(fmt)
        except Exception:
            return str(value)

    @pass_context
    def get_flashed_messages(context, with_categories: bool = False):
        request = context.get("request")
        if request is None:
            return []

        stored = []
        for msg in messages.get_messages(request):
            category = (msg.tags.split()[0] if msg.tags else "info")
            stored.append((category, str(msg)))

        if with_categories:
            return stored
        return [m for _, m in stored]

    def url_for(endpoint: str, **values: Any) -> str:
        if endpoint == "static":
            filename = values.get("filename")
            return static(filename) if filename else static("")

        from django.urls import get_resolver
        from urllib.parse import urlencode

        resolver = get_resolver()
        path_params = set()
        try:
            entry = resolver.reverse_dict.get(endpoint)
            if entry and isinstance(entry, tuple) and entry[0]:
                for possibility in entry[0]:
                    if len(possibility) > 1:
                        path_params.update(possibility[1])
        except Exception:
            pass

        path_kwargs = {}
        query_params = {}
        for k, v in values.items():
            if k in path_params:
                path_kwargs[k] = v
            else:
                query_params[k] = v

        try:
            url = reverse(endpoint, kwargs=path_kwargs)
            if query_params:
                url += "?" + urlencode(query_params)
            return url
        except NoReverseMatch:
            try:
                return reverse(endpoint, kwargs=values)
            except NoReverseMatch:
                return "#"

    env.globals.update(
        url_for=url_for,
        get_flashed_messages=get_flashed_messages,
        now=timezone.now,
        timedelta=timedelta,
    )

    env.filters.update(
        strftime=_strftime,
    )

    return env
