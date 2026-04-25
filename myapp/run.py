import os

from myapp import app


def _to_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def resolve_run_options() -> tuple[bool, int]:
    debug = _to_bool(os.getenv("FLASK_DEBUG", ""))
    port = int(os.getenv("PORT", "80"))
    return debug, port


if __name__ == "__main__":
    debug, port = resolve_run_options()
    app.run(host="0.0.0.0", port=port, debug=debug)
