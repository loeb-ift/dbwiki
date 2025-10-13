import os
import sys
import json
import logging
import sqlite3
import uuid
import pandas as pd
from sqlalchemy import create_engine

# Add project root to Python path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Configure logging to capture detailed error information
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("dataset_upload_diagnostic.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import the necessary modules from the application
try:
    from app.core.db_utils import get_user_db_connection, _run_migration_for_existing_db
    from app.core.db_utils import get_user_db_path
    logger.info("Successfully imported application modules")
except ImportError as e:
    logger.error(f"Failed to import application modules: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

def check_file_permissions():
    """Check file permissions for user_data directories"""
    directories_to_check = [
        'user_data',
        'user_data/datasets',
        'user_data/chroma_db'
    ]
    
    logger.info("Checking file permissions...")
    for dir_path in directories_to_check:
        abs_path = os.path.join(os.getcwd(), dir_path)
        if os.path.exists(abs_path):
            stat_info = os.stat(abs_path)
            permissions = oct(stat_info.st_mode)[-3:]
            logger.info(f"Directory '{dir_path}' exists with permissions: {permissions}")
        else:
            logger.warning(f"Directory '{dir_path}' does not exist")


def check_user_database(user_id='user1'):
    """Check the user's database directly"""
    logger.info(f"Checking database for user '{user_id}'...")
    
    # Get the database path
    db_path = get_user_db_path(user_id)
    logger.info(f"User database path: {db_path}")
    
    # Check if the database file exists
    if os.path.exists(db_path):
        stat_info = os.stat(db_path)
        permissions = oct(stat_info.st_mode)[-3:]
        logger.info(f"Database file exists with permissions: {permissions}")
        
        # Try to connect directly and examine structure
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if datasets table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='datasets'")
            if cursor.fetchone():
                logger.info("Datasets table exists in user database")
                
                # Get count of existing datasets
                cursor.execute("SELECT COUNT(*) FROM datasets")
                count = cursor.fetchone()[0]
                logger.info(f"User has {count} existing datasets")
            else:
                logger.warning("Datasets table does not exist in user database")
            
            # Check database structure
            cursor.execute("PRAGMA table_info(datasets)")
            columns = cursor.fetchall()
            logger.info(f"Datasets table columns: {[col[1] for col in columns]}")
            
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error examining database structure: {e}")
            import traceback
            traceback.print_exc()
    else:
        logger.error(f"Database file does not exist: {db_path}")


def test_migration_directly(user_id='user1'):
    """Test the migration function directly"""
    logger.info(f"Testing migration function directly for user '{user_id}'...")
    try:
        with get_user_db_connection(user_id) as conn:
            logger.info("Successfully connected to user database")
            
            # Try to run the migration check directly
            try:
                logger.info("Running migration check directly...")
                _run_migration_for_existing_db(conn, user_id)
                logger.info("Migration check completed successfully")
            except Exception as e:
                logger.error(f"Migration check failed: {e}")
                import traceback
                traceback.print_exc()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        import traceback
        traceback.print_exc()


def test_dataset_creation_steps(user_id='user1'):
    """Simulate the steps in dataset creation to find where the error occurs"""
    logger.info(f"Simulating dataset creation steps for user '{user_id}'...")
    
    # Step 1: Generate a new DB path
    try:
        dataset_name = "test_diagnostic_dataset"
        db_path = os.path.join('user_data', 'datasets', f'{uuid.uuid4().hex}.sqlite')
        logger.info(f"Generated database path: {db_path}")
        
        # Step 2: Create directories if needed
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        logger.info(f"Created directories for database path")
        
        # Step 3: Try to create a SQLite database
        try:
            engine = create_engine(f'sqlite:///{db_path}')
            logger.info(f"Successfully created SQLAlchemy engine for: {db_path}")
            
            # Step 4: Create a sample table
            try:
                df = pd.DataFrame({
                    'id': [1, 2, 3],
                    'name': ['Test1', 'Test2', 'Test3'],
                    'value': [100, 200, 300]
                })
                df.to_sql('test_table', engine, index=False, if_exists='replace')
                logger.info("Successfully created test table in new database")
            except Exception as e:
                logger.error(f"Failed to create test table: {e}")
                import traceback
                traceback.print_exc()
        except Exception as e:
            logger.error(f"Failed to create database engine: {e}")
            import traceback
            traceback.print_exc()
        
        # Step 5: Try to register the dataset in user's database
        try:
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO datasets (dataset_name, db_path) VALUES (?, ?)", 
                              (dataset_name, db_path))
                new_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Successfully registered dataset with ID: {new_id}")
        except Exception as e:
            logger.error(f"Failed to register dataset in user database: {e}")
            import traceback
            traceback.print_exc()
            # Clean up the database file if registration failed
            if os.path.exists(db_path):
                os.remove(db_path)
                logger.info(f"Cleaned up database file: {db_path}")
    except Exception as e:
        logger.error(f"Dataset creation simulation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    logger.info("Starting database and dataset upload diagnostic test")
    
    # Check file permissions
    check_file_permissions()
    
    # Check user1's database
    check_user_database('user1')
    
    # Test migration directly
    test_migration_directly('user1')
    
    # Test dataset creation steps
    test_dataset_creation_steps('user1')
    
    logger.info("Diagnostic test completed. Check dataset_upload_diagnostic.log for details.")