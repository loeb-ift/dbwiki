import unittest
import os
import sys
import json
from unittest.mock import patch, MagicMock
from flask import session
from io import BytesIO

# Add 'src' to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Import the Flask app and other necessary functions
from multi_user_app import app, get_user_db_connection, init_training_db, users, MyVanna, configure_vanna_for_request

class AskWebFeatureTest(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['DEBUG'] = False
        self.app = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

        # Mock Vanna instance for testing
        self.mock_vanna_instance = MagicMock(spec=MyVanna)
        self.mock_vanna_instance.log_queue = MagicMock(spec=Queue)
        self.mock_vanna_instance.log_queue.get.side_effect = [
            {'type': 'thinking_step', 'step': '相似問題檢索', 'details': [{'question': '相似問題1', 'sql': 'SELECT 1;'}]},
            {'type': 'thinking_step', 'step': 'DDL 檢索', 'details': ['CREATE TABLE test (id INT);']},
            {'type': 'thinking_step', 'step': '文件檢索', 'details': ['這是相關文件。']},
            {'type': 'analysis_result', 'analysis': '這是模擬的分析表內容。'},
            {'type': 'sql_result', 'sql': 'SELECT * FROM test;'},
            {'type': 'data_result', 'data': 'id\n1'},
            None # End of stream
        ]
        self.mock_vanna_instance.generate_sql.return_value = 'SELECT * FROM test;'
        self.mock_vanna_instance.submit_prompt.return_value = '這是模擬的分析表內容。'
        self.mock_vanna_instance.run_sql.return_value = MagicMock(to_string=lambda: 'id\n1')

        # Patch get_vanna_instance to return our mock
        self.get_vanna_patch = patch('multi_user_app.get_vanna_instance', return_value=self.mock_vanna_instance)
        self.mock_get_vanna = self.get_vanna_patch.start()

        # Patch configure_vanna_for_request to return our mock
        self.configure_vanna_patch = patch('multi_user_app.configure_vanna_for_request', return_value=self.mock_vanna_instance)
        self.mock_configure_vanna = self.configure_vanna_patch.start()

        # Create a dummy user_data directory and database for testing
        self.test_user_id = "testuser"
        self.test_db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{self.test_user_id}.sqlite')
        os.makedirs(os.path.dirname(self.test_db_path), exist_ok=True)
        init_training_db(self.test_user_id)

        # Login the test user
        with self.app as client:
            client.post('/login', data={'username': self.test_user_id, 'password': users[self.test_user_id]})
            with client.session_transaction() as sess:
                sess['username'] = self.test_user_id
                # Simulate activating a dataset
                # First, add a dummy dataset to the user's training DB
                with get_user_db_connection(self.test_user_id) as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO datasets (dataset_name, db_path) VALUES (?, ?)", ("test_dataset", "dummy_db.sqlite"))
                    self.test_dataset_id = cursor.lastrowid
                    conn.commit()
                sess['active_dataset_id'] = self.test_dataset_id

    def tearDown(self):
        self.get_vanna_patch.stop()
        self.configure_vanna_patch.stop()
        self.app_context.pop()
        # Clean up dummy database
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        user_data_dir = os.path.join(os.getcwd(), 'user_data')
        if os.path.exists(user_data_dir) and not os.listdir(user_data_dir):
            os.rmdir(user_data_dir)

    def test_ask_question_with_analysis(self):
        question = "顯示所有客戶的訂單總金額"
        response = self.app.post('/api/ask', json={'question': question})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/event-stream')

        # Parse the event stream response
        data_chunks = response.data.decode('utf-8').strip().split('\n\n')
        
        # Expected types in order
        expected_types = ['thinking_step', 'thinking_step', 'thinking_step', 'analysis_result', 'sql_result', 'data_result']
        
        parsed_data = []
        for chunk in data_chunks:
            if chunk.startswith('data: '):
                try:
                    parsed_data.append(json.loads(chunk[len('data: '):]))
                except json.JSONDecodeError:
                    self.fail(f"Failed to decode JSON from chunk: {chunk}")

        self.assertEqual(len(parsed_data), len(expected_types))

        for i, expected_type in enumerate(expected_types):
            self.assertEqual(parsed_data[i]['type'], expected_type)

        # Verify specific content
        self.assertIn('相似問題檢索', parsed_data[0]['step'])
        self.assertIn('DDL 檢索', parsed_data[1]['step'])
        self.assertIn('文件檢索', parsed_data[2]['step'])
        self.assertIn('這是模擬的分析表內容。', parsed_data[3]['analysis'])
        self.assertIn('SELECT * FROM test;', parsed_data[4]['sql'])
        self.assertIn('id\n1', parsed_data[5]['data'])

if __name__ == '__main__':
    unittest.main()