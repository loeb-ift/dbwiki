import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sqlite3
from app import app, init_training_db, load_training_data_from_db

class TestQAUpdate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        在所有測試執行前設置環境：
        1. 設置測試用的資料庫路徑。
        2. 初始化訓練資料庫。
        3. 從資料庫加載訓練資料。
        """
        cls.test_db_path = 'test_training_data.sqlite'
        os.environ['TRAINING_DATA_DB_PATH'] = cls.test_db_path
        init_training_db()
        load_training_data_from_db(MagicMock()) # vn 實例在這裡不需要實際功能

    @classmethod
    def tearDownClass(cls):
        """
        在所有測試執行後清理環境：
        1. 刪除測試用的資料庫檔案。
        2. 清理環境變量。
        """
        if os.path.exists(cls.test_db_path):
            os.remove(cls.test_db_path)
        del os.environ['TRAINING_DATA_DB_PATH']

    def setUp(self):
        """
        在每個測試執行前設置：
        1. 獲取 Flask 測試客戶端。
        2. 清空並重新填充測試資料庫，確保每個測試都在乾淨的狀態下運行。
        """
        self.app = app.test_client()
        self.app.testing = True

        # 清空並重新填充資料庫
        conn = sqlite3.connect(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM training_qa")
        cursor.execute("INSERT INTO training_qa (id, question, sql_query) VALUES (?, ?, ?)", (1, "舊問題", "SELECT * FROM old_table"))
        cursor.execute("INSERT INTO training_qa (id, question, sql_query) VALUES (?, ?, ?)", (2, "另一個問題", "SELECT * FROM another_table"))
        conn.commit()
        conn.close()

    def test_update_qa_question_success(self):
        """
        測試成功更新問答配對的問題。
        """
        response = self.app.post(
            '/api/update_qa_question',
            data=json.dumps({'id': 1, 'question': '新問題'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.data)['status'], 'success')
        self.assertEqual(json.loads(response.data)['message'], 'Question updated successfully.')

        # 驗證資料庫中的問題是否已更新
        conn = sqlite3.connect(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT question FROM training_qa WHERE id = ?", (1,))
        updated_question = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(updated_question, '新問題')

    def test_update_qa_question_not_found(self):
        """
        測試更新不存在的問答配對。
        """
        response = self.app.post(
            '/api/update_qa_question',
            data=json.dumps({'id': 999, 'question': '不存在的問題'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(response.data)['status'], 'error')
        self.assertIn('No QA pair found with id 999.', json.loads(response.data)['message'])

    def test_update_qa_question_missing_id(self):
        """
        測試缺少 ID 的情況。
        """
        response = self.app.post(
            '/api/update_qa_question',
            data=json.dumps({'question': '缺少ID的問題'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.data)['status'], 'error')
        self.assertEqual(json.loads(response.data)['message'], 'ID and question are required.')

    def test_update_qa_question_missing_question(self):
        """
        測試缺少問題內容的情況。
        """
        response = self.app.post(
            '/api/update_qa_question',
            data=json.dumps({'id': 1}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.data)['status'], 'error')
        self.assertEqual(json.loads(response.data)['message'], 'ID and question are required.')

    @patch('sqlite3.connect')
    def test_update_qa_question_database_error(self, mock_connect):
        """
        測試資料庫操作失敗的情況。
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = sqlite3.Error("模擬資料庫錯誤")

        response = self.app.post(
            '/api/update_qa_question',
            data=json.dumps({'id': 1, 'question': '新問題'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(json.loads(response.data)['status'], 'error')
        self.assertIn('Database error: 模擬資料庫錯誤', json.loads(response.data)['message'])

if __name__ == '__main__':
    unittest.main()