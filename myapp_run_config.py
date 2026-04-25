"""Runtime option parsing utilities for application startup."""

from __future__ import annotations

import os
from typing import Mapping, Tuple


TRUE_VALUES = {"1", "true", "yes", "on"}


def to_bool(value: str) -> bool:
    return value.strip().lower() in TRUE_VALUES


def resolve_run_options(env: Mapping[str, str] | None = None) -> Tuple[bool, int]:
    source = env if env is not None else os.environ
    debug = to_bool(source.get("FLASK_DEBUG", ""))
    port = int(source.get("PORT", "80"))
    return debug, port
