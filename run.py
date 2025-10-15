import os
from app import app

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    port = 8085
    app.run(host='0.0.0.0', debug=debug_mode, port=port)