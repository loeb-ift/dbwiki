import unittest
import os
import json
import sqlite3
import shutil
from unittest.mock import patch, MagicMock

# Due to the structure of app.py, we need to import it first.
# This import method will change after refactoring.
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app_main import app, init_training_db, get_user_db_connection, users

class TestApiEndpoints(unittest.TestCase):

    def setUp(self):
        """Set up the test environment before each test."""
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret'
        self.app = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

        self.test_user = "test_user_api"
        self.test_password = "password"
        
        # Patch the USERS config for the duration of the test
        # Ensure app.config['USERS'] exists before patching
        if 'USERS' not in app.config:
            app.config['USERS'] = {}
            
        self.users_patcher = patch.dict(app.config['USERS'], {self.test_user: {'password': self.test_password, 'is_admin': True}})
        self.users_patcher.start()

        self.user_data_dir = os.path.join(os.getcwd(), 'user_data')
        self.test_db_path = os.path.join(self.user_data_dir, f'training_data_{self.test_user}.sqlite')
        
        # Clean up before each test
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        
        init_training_db(self.test_user)

        # Log in the test user
        with self.app.session_transaction() as sess:
            sess['username'] = self.test_user

    def tearDown(self):
        """Clean up the test environment after each test."""
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        
        self.users_patcher.stop()
        self.app_context.pop()

    def test_dataset_crud_and_activation_flow(self):
        """Test the full CRUD and activation flow for datasets."""
        
        # 1. GET initial datasets (should be empty)
        response = self.client.get('/api/datasets')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['datasets']), 0)

        # 2. POST to create a new dataset
        from io import BytesIO
        with patch('app.blueprints.datasets.pd.read_csv', return_value=MagicMock()):
            with patch('app.blueprints.datasets.pd.DataFrame.to_sql') as mock_to_sql:
                response = self.client.post(
                    '/api/datasets',
                    data={
                        'dataset_name': 'MyTestDataset',
                        'files': (BytesIO(b'col1,col2\n1,a'), 'test.csv')
                    },
                    content_type='multipart/form-data'
                )
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['dataset']['dataset_name'], 'MyTestDataset')
        dataset_id = data['dataset']['id']

        # 3. GET datasets again (should have one)
        response = self.client.get('/api/datasets')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data['datasets']), 1)
        self.assertEqual(data['datasets'][0]['name'], 'MyTestDataset')

        # 4. POST to activate the dataset
        with patch('sqlalchemy.inspect') as mock_inspect:
            mock_inspector = MagicMock()
            mock_inspector.get_table_names.return_value = ['test']
            mock_inspect.return_value = mock_inspector
            
            response = self.client.post('/api/datasets/activate', json={'dataset_id': dataset_id})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        with self.client.session_transaction() as sess:
            self.assertEqual(sess['active_dataset_id'], str(dataset_id))

        # 5. PUT to update the dataset name
        response = self.client.put('/api/datasets', json={'dataset_id': dataset_id, 'new_name': 'MyUpdatedDataset'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['dataset']['dataset_name'], 'MyUpdatedDataset')

        # 6. GET to verify the name change
        response = self.client.get('/api/datasets')
        data = json.loads(response.data)
        self.assertEqual(data['datasets'][0]['name'], 'MyUpdatedDataset')

        # 7. DELETE the dataset
        response = self.client.delete('/api/datasets', json={'dataset_id': dataset_id})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')

        # 8. GET datasets one last time (should be empty again)
        response = self.client.get('/api/datasets')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data['datasets']), 0)

    def test_prompt_management_api_flow(self):
        """Test the full CRUD flow for prompt management."""
        
        # 1. GET initial prompts (should have some defaults)
        response = self.client.get('/api/prompts')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        initial_prompt_count = len(data['prompts'])
        self.assertGreater(initial_prompt_count, 0)

        # 2. POST to create a new prompt
        new_prompt_data = {
            'prompt_name': 'my_custom_prompt',
            'prompt_content': 'This is a custom prompt.',
            'prompt_type': 'custom',
            'is_global': False
        }
        response = self.client.post('/api/save_prompt', json=new_prompt_data)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')

        # 3. GET prompts again to verify addition
        response = self.client.get('/api/prompts')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data['prompts']), initial_prompt_count + 1)
        
        # Find the newly created prompt
        new_prompt = next((p for p in data['prompts'] if p['prompt_name'] == 'my_custom_prompt'), None)
        self.assertIsNotNone(new_prompt)
        prompt_id = new_prompt['id']

        # 4. POST to update the prompt
        updated_prompt_data = {
            'id': prompt_id,
            'prompt_name': 'my_custom_prompt_updated',
            'prompt_content': 'This is an updated custom prompt.',
            'prompt_type': 'custom_updated',
            'is_global': False
        }
        response = self.client.post('/api/save_prompt', json=updated_prompt_data)
        self.assertEqual(response.status_code, 200)

        # 5. GET to verify the update
        response = self.client.get('/api/prompts')
        data = json.loads(response.data)
        updated_prompt = next((p for p in data['prompts'] if p['id'] == prompt_id), None)
        self.assertEqual(updated_prompt['prompt_name'], 'my_custom_prompt_updated')
        self.assertEqual(updated_prompt['prompt_content'], 'This is an updated custom prompt.')

        # 6. DELETE the prompt
        response = self.client.delete(f'/api/delete_prompt/{prompt_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')

        # 7. GET prompts one last time to verify deletion
        response = self.client.get('/api/prompts')
        data = json.loads(response.data)
        self.assertEqual(len(data['prompts']), initial_prompt_count)
        
        # 8. Test resetting a default prompt
        # First, modify a default prompt
        default_prompt_name = 'ask_analysis_prompt'
        response = self.client.post('/api/save_prompt', json={
            'prompt_name': default_prompt_name,
            'prompt_content': 'Modified content',
            'is_global': True
        })
        self.assertEqual(response.status_code, 200)
        
        # Now, reset it
        response = self.client.post(f'/api/reset_prompt_to_default/{default_prompt_name}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        
        # Verify it has been reset (by checking it doesn't contain the modified content)
        response = self.client.get('/api/prompts')
        data = json.loads(response.data)
        reset_prompt = next((p for p in data['prompts'] if p['prompt_name'] == default_prompt_name), None)
        self.assertNotIn('Modified content', reset_prompt['prompt_content'])


if __name__ == '__main__':
    unittest.main()