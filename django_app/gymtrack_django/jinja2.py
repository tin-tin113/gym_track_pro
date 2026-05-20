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
