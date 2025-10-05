import unittest
import os
import sqlite3
from unittest.mock import patch, MagicMock
from multi_user_app import app, users, get_vanna_instance, init_training_db, load_training_data_from_db, MyVanna

class MultiUserAppTestCase(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_key'
        self.app = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

        # 清理用户数据目录
        self.user_data_dir = os.path.join(os.getcwd(), 'user_data')
        if os.path.exists(self.user_data_dir):
            for f in os.listdir(self.user_data_dir):
                os.remove(os.path.join(self.user_data_dir, f))
            os.rmdir(self.user_data_dir)
        os.makedirs(self.user_data_dir)

        # 模拟 ChromaDB 集合
        self.mock_chroma_collection = MagicMock()
        MyVanna.chroma_client = MagicMock()
        MyVanna.chroma_client.get_or_create_collection.return_value = self.mock_chroma_collection

    def tearDown(self):
        self.app_context.pop()
        # 清理用户数据目录
        if os.path.exists(self.user_data_dir):
            for f in os.listdir(self.user_data_dir):
                os.remove(os.path.join(self.user_data_dir, f))
            os.rmdir(self.user_data_dir)

    def test_login_logout(self):
        # Test successful login
        response = self.app.post('/login', data={'username': 'user1', 'password': 'pass1'})
        self.assertEqual(response.status_code, 302)  # Redirect to index
        with self.app as client:
            client.get('/')
            self.assertEqual(session['username'], 'user1')

        # Test logout
        response = self.app.get('/logout')
        self.assertEqual(response.status_code, 302)  # Redirect to login
        with self.app as client:
            client.get('/')
            self.assertNotIn('username', session)

        # Test failed login
        response = self.app.post('/login', data={'username': 'user1', 'password': 'wrong_pass'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid credentials', response.data)

    def test_user_specific_vanna_instance_and_db(self):
        # Login user1
        self.app.post('/login', data={'username': 'user1', 'password': 'pass1'})
        user1_vn = get_vanna_instance('user1')
        self.assertIsInstance(user1_vn, MyVanna)
        self.assertEqual(user1_vn.chroma_collection.name, 'vanna_training_data_user1')
        self.assertTrue(os.path.exists(os.path.join(self.user_data_dir, 'training_data_user1.sqlite')))

        # Login user2
        self.app.post('/login', data={'username': 'user2', 'password': 'pass2'})
        user2_vn = get_vanna_instance('user2')
        self.assertIsInstance(user2_vn, MyVanna)
        self.assertEqual(user2_vn.chroma_collection.name, 'vanna_training_data_user2')
        self.assertTrue(os.path.exists(os.path.join(self.user_data_dir, 'training_data_user2.sqlite')))

        # Ensure instances are different
        self.assertIsNot(user1_vn, user2_vn)
        self.assertIsNot(user1_vn.chroma_collection, user2_vn.chroma_collection)

    def test_training_data_isolation(self):
        # Login user1 and add data
        self.app.post('/login', data={'username': 'user1', 'password': 'pass1'})
        user1_vn = get_vanna_instance('user1')
        user1_vn.train(ddl="CREATE TABLE user1_table (id INT);")
        user1_vn.train(question="user1 question", sql="SELECT * FROM user1_table;")

        # Login user2 and add data
        self.app.post('/login', data={'username': 'user2', 'password': 'pass2'})
        user2_vn = get_vanna_instance('user2')
        user2_vn.train(ddl="CREATE TABLE user2_table (id INT);")
        user2_vn.train(question="user2 question", sql="SELECT * FROM user2_table;")

        # Verify user1's data
        self.app.post('/login', data={'username': 'user1', 'password': 'pass1'})
        user1_vn_reloaded = get_vanna_instance('user1')
        user1_training_data = user1_vn_reloaded.get_training_data()
        self.assertIn("CREATE TABLE user1_table (id INT);", user1_training_data['content'].tolist())
        self.assertNotIn("CREATE TABLE user2_table (id INT);", user1_training_data['content'].tolist())

        # Verify user2's data
        self.app.post('/login', data={'username': 'user2', 'password': 'pass2'})
        user2_vn_reloaded = get_vanna_instance('user2')
        user2_training_data = user2_vn_reloaded.get_training_data()
        self.assertIn("CREATE TABLE user2_table (id INT);", user2_training_data['content'].tolist())
        self.assertNotIn("CREATE TABLE user1_table (id INT);", user2_training_data['content'].tolist())

if __name__ == '__main__':
    unittest.main()