import os
import sys
import sqlite3
import tempfile
from werkzeug.datastructures import FileStorage
from io import BytesIO
import pandas as pd
from app.core.db_utils import get_user_db_connection
from app.core.helpers import get_dataset_tables
from app.blueprints.datasets import handle_dataset_files

# Configure pandas to display Chinese characters properly
import pandas as pd
pd.set_option('display.unicode.east_asian_width', True)

# Add the project root to Python path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Simulate Flask request and session objects
class MockRequest:
    def __init__(self, method='POST', files=None, args=None, form=None, json=None):
        self.method = method
        self.files = files or {}
        self.args = args or {}
        self.form = form or {}
        self.json = json
    
    def get_json(self):
        return self.json
    
    def getlist(self, key):
        return self.files.getlist(key)

class MockSession:
    def __init__(self):
        self.data = {}
    
    def __getitem__(self, key):
        return self.data[key]
    
    def __setitem__(self, key, value):
        self.data[key] = value

# Test function to simulate dataset file upload
def test_dataset_file_upload(user_id="user1"):
    print(f"\n===== Testing dataset file upload for user '{user_id}' =====")
    
    try:
        # Step 1: Create a test dataset if it doesn't exist
        print("Step 1: Creating a test dataset...")
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Check if test dataset exists, create if not
            cursor.execute("SELECT id FROM datasets WHERE dataset_name = ?", ("Test Dataset",))
            result = cursor.fetchone()
            
            if result:
                dataset_id = result[0]
                print(f"Found existing test dataset with ID: {dataset_id}")
            else:
                # Create a new test dataset
                test_db_path = os.path.join('user_data', 'datasets', f'test_dataset_{user_id}.sqlite')
                os.makedirs(os.path.dirname(test_db_path), exist_ok=True)
                
                cursor.execute("INSERT INTO datasets (dataset_name, db_path) VALUES (?, ?)", 
                              ("Test Dataset", test_db_path))
                dataset_id = cursor.lastrowid
                conn.commit()
                print(f"Created new test dataset with ID: {dataset_id}")
        
        # Step 2: Create a mock CSV file for upload
        print("Step 2: Creating mock CSV file for upload...")
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['测试1', '测试2', '测试3'],
            'value': [100, 200, 300]
        })
        
        # Convert DataFrame to CSV in memory
        csv_buffer = BytesIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8')
        csv_buffer.seek(0)
        
        # Create a mock FileStorage object
        mock_file = FileStorage(
            stream=csv_buffer,
            filename='test_data.csv',
            name='files',
            content_type='text/csv'
        )
        
        # Step 3: Simulate the file upload request
        print("Step 3: Simulating file upload request...")
        mock_request = MockRequest(
            method='POST',
            files={'files': [mock_file]},
            args={'dataset_id': str(dataset_id)}
        )
        
        mock_session = MockSession()
        mock_session['username'] = user_id
        
        # Step 4: Test individual components of the upload process
        print("Step 4: Testing upload process components...")
        
        # Test get_user_db_connection
        print("- Testing get_user_db_connection...")
        try:
            with get_user_db_connection(user_id) as conn:
                print("  ✓ Successfully connected to user database")
        except Exception as e:
            print(f"  ✗ Error connecting to user database: {type(e).__name__}: {e}")
            return False
        
        # Test dataset exists
        print("- Checking if dataset exists...")
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
            row = cursor.fetchone()
            if not row:
                print(f"  ✗ Dataset with ID {dataset_id} not found")
                return False
            db_path = row[0]
            print(f"  ✓ Found dataset at: {db_path}")
        
        # Test creating engine and uploading CSV
        print("- Testing CSV upload to dataset...")
        try:
            from sqlalchemy import create_engine
            engine = create_engine(f'sqlite:///{db_path}')
            table_name = 'test_table'
            df.to_sql(table_name, engine, index=False, if_exists='replace')
            print(f"  ✓ Successfully uploaded CSV to table '{table_name}'")
        except Exception as e:
            print(f"  ✗ Error uploading CSV: {type(e).__name__}: {e}")
            return False
        
        # Test get_dataset_tables
        print("- Testing get_dataset_tables...")
        try:
            tables_info, error = get_dataset_tables(user_id, dataset_id)
            if error:
                print(f"  ✗ Error getting dataset tables: {error}")
                return False
            print(f"  ✓ Found {len(tables_info['table_names'])} tables")
            print(f"  ✓ Tables: {tables_info['table_names']}")
        except Exception as e:
            print(f"  ✗ Error in get_dataset_tables: {type(e).__name__}: {e}")
            return False
        
        print("\nAll tests passed successfully! The file upload functionality appears to be working correctly.")
        print("\nPotential issues to check:")
        print("1. Check if the user 'user1' has the correct permissions for file operations")
        print("2. Verify the actual request being sent by the client")
        print("3. Check server logs for more detailed error information")
        print("4. Ensure the user_data/datasets directory has proper write permissions")
        
        return True
        
    except Exception as e:
        print(f"\nTest failed with unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print(f"Current working directory: {os.getcwd()}")
    print(f"Python version: {sys.version}")
    
    # Run the test for user 'user1'
    success = test_dataset_file_upload("user1")
    
    if success:
        print("\n===== Test completed successfully =====")
    else:
        print("\n===== Test completed with failures =====")