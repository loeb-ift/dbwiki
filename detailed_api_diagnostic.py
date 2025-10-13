import os
import sys
import logging
import traceback
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename
from io import BytesIO
import pandas as pd

# Add project root to Python path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Configure detailed logging for the entire application
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("detailed_api_diagnostic.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Try to import the Flask app and enhance its error handling
try:
    from app import app as flask_app
    from app.blueprints.datasets import handle_datasets
    from app.core.db_utils import get_user_db_connection, _run_migration_for_existing_db
    logger.info("Successfully imported application modules")
    
    # Enhance Flask's default logging
    flask_app.logger.setLevel(logging.DEBUG)
    
    # Add a custom error handler to catch all exceptions
    @flask_app.errorhandler(Exception)
    def handle_exception(e):
        """Return JSON instead of HTML for HTTP errors."""
        logger.error(f"Unhandled exception: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Pass through HTTP errors
        if isinstance(e, HTTPException):
            response = e.get_response()
            response.data = str(e)
            response.content_type = "text/plain"
            return response
        
        # Handle non-HTTP exceptions
        return {"error": str(e), "traceback": traceback.format_exc()}, 500
    
    # Add before_request handler to log all requests
    @flask_app.before_request
    def log_request_info():
        logger.debug(f"Request: {flask_app.request.method} {flask_app.request.url}")
        logger.debug(f"Request headers: {flask_app.request.headers}")
        logger.debug(f"Request data: {flask_app.request.data}")
        if flask_app.request.form:
            logger.debug(f"Request form: {dict(flask_app.request.form)}")
        if flask_app.request.files:
            logger.debug(f"Request files: {[f.filename for f in flask_app.request.files.getlist('files')]}")
        
    # Add after_request handler to log all responses
    @flask_app.after_request
    def log_response_info(response):
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Response headers: {response.headers}")
        return response
    
    # Create a test client with enhanced logging
    client = flask_app.test_client()
    
    # Function to create a mock CSV file
    def create_mock_csv():
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Test1', 'Test2', 'Test3'],
            'value': [100, 200, 300]
        })
        
        csv_buffer = BytesIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8')
        csv_buffer.seek(0)
        
        return csv_buffer
    
    # Test function
    def test_dataset_upload():
        logger.info("Starting dataset upload test...")
        
        # Simulate login for user1
        with client.session_transaction() as sess:
            sess['username'] = 'user1'
            sess['user_id'] = 'user1'
            logger.info("Simulated login for user 'user1'")
        
        # Create mock CSV file
        csv_buffer = create_mock_csv()
        
        # Prepare multipart form data with file
        dataset_name = "api_test_dataset"
        
        logger.info(f"Attempting to upload dataset '{dataset_name}' with file 'test_data.csv'")
        
        try:
            # Reset buffer position
            csv_buffer.seek(0)
            
            # Create a multipart form data dictionary
            # This is the correct format for file uploads with Flask test client
            response = client.post(
                '/api/datasets',
                content_type='multipart/form-data',
                data={
                    'dataset_name': dataset_name,
                },
                files={
                    'files': ('test_data.csv', csv_buffer.read(), 'text/csv')
                },
                follow_redirects=True
            )
            
            logger.info(f"API response status: {response.status_code}")
            logger.info(f"API response data: {response.data.decode('utf-8')}")
            
            if response.status_code == 201:
                logger.info("Dataset creation succeeded!")
            elif response.status_code == 500:
                logger.error(f"500 error detected! Response data: {response.data.decode('utf-8')}")
            else:
                logger.warning(f"Received unexpected status code: {response.status_code}")
        except Exception as e:
            logger.error(f"API call failed with exception: {e}")
            logger.error(traceback.format_exc())
        
        logger.info("Dataset upload test completed")
    
    if __name__ == "__main__":
        logger.info("Starting detailed API diagnostic test")
        test_dataset_upload()
        logger.info("Diagnostic test completed. Check detailed_api_diagnostic.log for details.")
        
except ImportError as e:
    logger.error(f"Failed to import application modules: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)
except Exception as e:
    logger.error(f"Script execution failed with unexpected error: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)