"""Pipeline domain service entrypoints.

This module is intentionally kept lightweight in phase-1 migration:
- provide a stable service import path for pipeline operations
- avoid task layer importing view modules directly
"""

from typing import Any


def dag_to_pipeline(*args: Any, **kwargs: Any):
    """Convert DAG definition to workflow payload.

    Lazy import prevents heavy view import at module import time.
    """
    from myapp.views.view_pipeline import dag_to_pipeline as _dag_to_pipeline

    return _dag_to_pipeline(*args, **kwargs)


def run_pipeline(*args: Any, **kwargs: Any):
    """Trigger pipeline execution.

    Lazy import prevents heavy view import at module import time.
    """
    from myapp.views.view_pipeline import run_pipeline as _run_pipeline

    return _run_pipeline(*args, **kwargs)
