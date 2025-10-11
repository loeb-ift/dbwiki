import os
from app import app

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    # Use port 5004 since 5003 is in use
    port = 5004
    app.run(host='0.0.0.0', debug=debug_mode, port=port)