import unittest
import os
import shutil
import time
from unittest.mock import MagicMock, patch
from multi_user_app import app, write_ask_log, _get_latest_log_content, load_prompt_template

class TestDynamicPromptGeneration(unittest.TestCase):
    USER_ID = "test_user"
    DATASET_ID = "test_dataset"
    ASK_LOG_DIR = os.path.join(os.getcwd(), 'ask_log')
    PROMPTS_DIR = os.path.join(os.getcwd(), 'prompts')
    ASK_ANALYSIS_PROMPT_PATH = os.path.join(PROMPTS_DIR, 'prompts', 'ask_analysis_prompt.txt')

    @classmethod
    def setUpClass(cls):
        # Ensure ask_log and prompts directories exist for setup
        os.makedirs(cls.ASK_LOG_DIR, exist_ok=True)
        os.makedirs(os.path.join(cls.PROMPTS_DIR, 'prompts'), exist_ok=True)

        # Create a dummy ask_analysis_prompt.txt
        with open(cls.ASK_ANALYSIS_PROMPT_PATH, 'w', encoding='utf-8') as f:
            f.write("""
## SQL 查詢思考過程分析表

### 1. 原始問題
[用戶提出的原始自然語言問題]

### 2. 檢索到的相似問題與 SQL 範例
| 相似問題 | 相關 SQL 範例 |
|---|---|
[列出檢索到的相似問題和 SQL 範例]

### 3. 檢索到的相關資料庫結構 (DDL)
```sql
[列出檢索到的相關 DDL 語句]
```

### 4. 檢索到的相關業務文件
[列出檢索到的相關業務文件內容]
""")

    @classmethod
    def tearDownClass(cls):
        # Clean up created directories and files
        if os.path.exists(cls.ASK_LOG_DIR):
            shutil.rmtree(cls.ASK_LOG_DIR)
        if os.path.exists(cls.PROMPTS_DIR):
            shutil.rmtree(cls.PROMPTS_DIR)

    def setUp(self):
        # Clear ask_log and prompts directories before each test
        if os.path.exists(self.ASK_LOG_DIR):
            shutil.rmtree(self.ASK_LOG_DIR)
        os.makedirs(self.ASK_LOG_DIR, exist_ok=True)

        # Recreate ask_analysis_prompt.txt if it was deleted by tearDownClass
        os.makedirs(os.path.join(self.PROMPTS_DIR, 'prompts'), exist_ok=True)
        with open(self.ASK_ANALYSIS_PROMPT_PATH, 'w', encoding='utf-8') as f:
            f.write("""
## SQL 查詢思考過程分析表

### 1. 原始問題
[用戶提出的原始自然語言問題]

### 2. 檢索到的相似問題與 SQL 範例
| 相似問題 | 相關 SQL 範例 |
|---|---|
[列出檢索到的相似問題和 SQL 範例]

### 3. 檢索到的相關資料庫結構 (DDL)
```sql
[列出檢索到的相關 DDL 語句]
```

### 4. 檢索到的相關業務文件
[列出檢索到的相關業務文件內容]
""")

        self.app = app.test_client()
        self.app.testing = True

        # Mock session for login_required decorator
        with self.app as client:
            with client.session_transaction() as sess:
                sess['username'] = self.USER_ID
                sess['active_dataset_id'] = self.DATASET_ID

    def _create_dummy_log_file(self, log_type: str, content: str, timestamp: int = None):
        if timestamp is None:
            timestamp = int(time.time())
        file_path = os.path.join(self.ASK_LOG_DIR, f"{self.USER_ID}_{log_type}_{timestamp}.log")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return file_path

    def test_get_latest_log_content(self):
        # Test with no logs
        self.assertEqual(_get_latest_log_content(self.USER_ID, "test_log_type"), "")

        # Test with one log
        log_content1 = "Log content 1"
        self._create_dummy_log_file("test_log_type", log_content1, timestamp=100)
        self.assertEqual(_get_latest_log_content(self.USER_ID, "test_log_type").strip(), log_content1)

        # Test with multiple logs, ensure latest is picked
        log_content2 = "Log content 2"
        self._create_dummy_log_file("test_log_type", log_content2, timestamp=200)
        self.assertEqual(_get_latest_log_content(self.USER_ID, "test_log_type").strip(), log_content2)

        # Test with different user_id
        self._create_dummy_log_file("test_log_type", "another user log", user_id="another_user", timestamp=300)
        self.assertEqual(_get_latest_log_content(self.USER_ID, "test_log_type").strip(), log_content2)

    @patch('multi_user_app.MyVanna')
    @patch('multi_user_app.configure_vanna_for_request')
    @patch('multi_user_app.write_ask_log')
    def test_dynamic_prompt_generation_and_log_cleanup(self, mock_write_ask_log, mock_configure_vanna_for_request, MockMyVanna):
        # Mock Vanna instance and its methods
        mock_vn_instance = MockMyVanna.return_value
        mock_vn_instance.generate_sql.return_value = "SELECT 1;"
        mock_vn_instance.run_sql.return_value = MagicMock(empty=False, to_json=lambda orient: "[]")
        mock_vn_instance.log_queue = MagicMock()
        mock_vn_instance.log_queue.empty.side_effect = [False, True] # First call returns False, then True
        mock_vn_instance.log_queue.get.return_value = {'type': 'thinking_step', 'step': 'LLM 完成生成 SQL', 'details': {'sql_response': 'SELECT 1;'}}

        mock_configure_vanna_for_request.return_value = mock_vn_instance

        # Create dummy log files that should be cleaned up
        sql_log_content = "similar_question_sql_results content"
        ddl_log_content = "get_related_ddl_results content"
        doc_log_content = "get_related_documentation_results content"

        self._create_dummy_log_file("get_similar_question_sql_results", sql_log_content, timestamp=100)
        self._create_dummy_log_file("get_related_ddl_results", ddl_log_content, timestamp=101)
        self._create_dummy_log_file("get_related_documentation_results", doc_log_content, timestamp=102)

        # Simulate an ask request
        question = "What is the total sales?"
        response = self.app.post('/api/ask', json={'question': question})
        self.assertEqual(response.status_code, 200)

        # Read the generated dynamic prompt file
        dynamic_prompt_files = [f for f in os.listdir(self.PROMPTS_DIR) if f.startswith(f"{self.USER_ID}_dynamic_prompt_") and f.endswith(".txt")]
        self.assertEqual(len(dynamic_prompt_files), 1)
        
        dynamic_prompt_path = os.path.join(self.PROMPTS_DIR, dynamic_prompt_files)
        with open(dynamic_prompt_path, 'r', encoding='utf-8') as f:
            generated_prompt_content = f.read()

        # Assert content of the dynamic prompt
        self.assertIn(question, generated_prompt_content)
        self.assertIn(sql_log_content, generated_prompt_content)
        self.assertIn(ddl_log_content, generated_prompt_content)
        self.assertIn(doc_log_content, generated_prompt_content)

        # Assert old log files are cleaned up
        remaining_log_files = os.listdir(self.ASK_LOG_DIR)
        self.assertFalse(any(f.startswith(f"{self.USER_ID}_get_similar_question_sql_results_") for f in remaining_log_files))
        self.assertFalse(any(f.startswith(f"{self.USER_ID}_get_related_ddl_results_") for f in remaining_log_files))
        self.assertFalse(any(f.startswith(f"{self.USER_ID}_get_related_documentation_results_") for f in remaining_log_files))

if __name__ == '__main__':
    unittest.main()