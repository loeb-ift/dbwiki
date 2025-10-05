import unittest
from unittest.mock import patch, MagicMock
from app import app, vn

class TestQAGeneration(unittest.TestCase):
    """
    測試問答生成功能。
    """

    def setUp(self):
        """
        設置測試環境。
        """
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.vn.generate_questions')
    @patch('app.vn.train')
    def test_generate_questions_and_train(self, mock_train, mock_generate_questions):
        """
        測試生成問題並訓練模型。
        """
        mock_generate_questions.return_value = [{'question': 'How many users?', 'sql': 'SELECT count(*) FROM users'}]
        mock_train.return_value = None

        response = self.app.post('/api/generate_questions')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'questions generated and model retrained', response.data)
        mock_generate_questions.assert_called_once()
        mock_train.assert_called_once_with(question='How many users?', sql='SELECT count(*) FROM users')

    @patch('app.vn.generate_questions')
    def test_generate_questions_no_new_questions(self, mock_generate_questions):
        """
        測試沒有新問題生成的情況。
        """
        mock_generate_questions.return_value = []

        response = self.app.post('/api/generate_questions')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No new questions were generated', response.data)
        mock_generate_questions.assert_called_once()

    @patch('app.vn.generate_questions')
    def test_generate_questions_failure(self, mock_generate_questions):
        """
        測試生成問題失敗的情況。
        """
        mock_generate_questions.side_effect = Exception("Question generation failed")

        response = self.app.post('/api/generate_questions')
        self.assertEqual(response.status_code, 500)
        self.assertIn(b'Question generation failed', response.data)

if __name__ == '__main__':
    unittest.main()