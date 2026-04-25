from myapp import app
from myapp_run_config import resolve_run_options


if __name__ == "__main__":
    debug, port = resolve_run_options()
    app.run(host="0.0.0.0", port=port, debug=debug)
