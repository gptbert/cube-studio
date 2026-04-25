import os

from myapp import app


if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG', '').lower() in {'1', 'true', 'yes', 'on'}
    port = int(os.getenv('PORT', '80'))
    app.run(host='0.0.0.0', port=port, debug=debug)
