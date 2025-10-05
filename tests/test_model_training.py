import unittest
from unittest.mock import patch, MagicMock
from app import app, vn

class TestModelTraining(unittest.TestCase):
    """
    測試模型訓練功能。
    """

    def setUp(self):
        """
        設置測試環境。
        """
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.vn.train')
    def test_train_model_with_ddl(self, mock_train):
        """
        測試使用 DDL 訓練模型。
        """
        mock_train.return_value = None
        response = self.app.post('/api/train', data={'ddl': 'CREATE TABLE test (id INT)'})
        self.assertEqual(response.status_code, 200)
        mock_train.assert_called_once_with(ddl='CREATE TABLE test (id INT)')

    @patch('app.vn.train')
    def test_train_model_with_documentation(self, mock_train):
        """
        測試使用文件訓練模型。
        """
        mock_train.return_value = None
        response = self.app.post('/api/train', data={'doc': 'This is a test documentation.'})
        self.assertEqual(response.status_code, 200)
        mock_train.assert_called_once_with(documentation='This is a test documentation.')

    @patch('app.vn.train')
    def test_train_model_with_qa_pairs(self, mock_train):
        """
        測試使用問答配對訓練模型。
        """
        mock_train.return_value = None
        response = self.app.post('/api/train', json={'qa_pairs': [{'question': 'What is test?', 'sql': 'SELECT * FROM test'}]})
        self.assertEqual(response.status_code, 200)
        mock_train.assert_called()

    @patch('app.vn.train')
    def test_train_model_failure(self, mock_train):
        """
        測試模型訓練失敗的情況。
        """
        mock_train.side_effect = Exception("Training failed")
        response = self.app.post('/api/train', data={'ddl': 'CREATE TABLE test (id INT)'})
        self.assertEqual(response.status_code, 500)
        self.assertIn(b'Training failed', response.data)

    def test_train_model_invalid_input(self):
        """
        測試模型訓練接口接收到無效輸入。
        """
        response = self.app.post('/api/train', data={})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'No training data provided', response.data)

if __name__ == '__main__':
    unittest.main()