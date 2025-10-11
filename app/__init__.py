from flask import Flask
import os
import json
from dotenv import load_dotenv

def create_app():
    """Create and configure an instance of the Flask application."""
    # Get the project root directory
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Create Flask app with explicit template and static folder paths
    app = Flask(__name__, 
                template_folder=os.path.join(project_root, 'templates'),
                static_folder=os.path.join(project_root, 'static'))
    load_dotenv()
    
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_strong_fixed_secret_key_for_session')
    
    try:
        # Get users from environment variable
        users_json = os.getenv('APP_USERS', '{}')
        users_dict = json.loads(users_json)
        
        # Initialize users config
        app.config['USERS'] = {}
        
        # Check if users_dict is in the simple format {username: password}
        if users_dict and all(isinstance(password, str) for password in users_dict.values()):
            # Use simple format - direct password comparison
            app.config['USERS'] = users_dict
        else:
            # If it's in the complex format {username: {password: '...', is_admin: ...}}
            app.config['USERS'] = users_dict
            
    except json.JSONDecodeError:
        app.logger.error("Invalid format for APP_USERS environment variable. Please use valid JSON.")
        app.config['USERS'] = {}
        
    # If no users configured, add default test user
    if not app.config['USERS']:
        app.config['USERS'] = {'testuser': 'password'}
        app.logger.info("No users configured. Added default test user: testuser/password")

    # Register blueprints
    from .blueprints.auth import auth_bp
    from .blueprints.datasets import datasets_bp
    from .blueprints.training import training_bp
    from .blueprints.ask import ask_bp
    from .blueprints.prompts import prompts_bp
    from .blueprints.test import test_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(datasets_bp)
    app.register_blueprint(training_bp)
    app.register_blueprint(ask_bp)
    app.register_blueprint(prompts_bp)
    app.register_blueprint(test_bp)

    # Register the main index route
    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    return app

# Create an instance of the app
app = create_app()