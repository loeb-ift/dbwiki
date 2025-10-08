import os
import sys
import json
from unittest.mock import MagicMock
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add 'src' to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from vanna.ollama import Ollama
from vanna.chromadb import ChromaDB_VectorStore
from queue import Queue

# Helper function to load prompt templates
def load_prompt_template(filename):
    with open(os.path.join('prompts', 'prompts', filename), 'r', encoding='utf-8') as f:
        return f.read()

class MockVanna(Ollama, ChromaDB_VectorStore):
    def __init__(self, user_id: str, config=None):
        self.log_queue = Queue()
        
        # Get Ollama model and host from environment variables
        model = os.getenv('OLLAMA_MODEL', 'mock-model')
        ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')

        # Mock Ollama client to prevent actual model pull
        self.ollama_client = MagicMock()
        self.ollama_client.pull.return_value = None # Ensure pull does nothing

        # Call Ollama's init with environment variables, but it should now use the mocked client
        Ollama.__init__(self, config={'model': model, 'ollama_host': ollama_host})
        ChromaDB_VectorStore.__init__(self, config={'collection_name': f"mock_vanna_training_data_{user_id}"})
        self.user_id = user_id
        self.engine = MagicMock() # Mock database engine
        self.run_sql = MagicMock(return_value=None) # Mock run_sql method
        self.run_sql_is_set = True

    def log(self, message: str, title: str = "Info"):
        self.log_queue.put({'type': 'thinking_step', 'step': title, 'details': message})

    def get_similar_question_sql(self, question: str, top_n: int = 5):
        self.log(f"檢索相似問題和 SQL 範例，問題: '{question}'", "相似問題檢索")
        return [
            {'question': '顯示所有訂單的總金額', 'sql': 'SELECT SUM(total_amount) FROM orders;'},
            {'question': '找出最近一個月的銷售額', 'sql': 'SELECT SUM(amount) FROM sales WHERE sale_date >= DATE(\'now\', \'-1 month\');'}
        ]

    def get_related_ddl(self, question: str, top_n: int = 5):
        self.log(f"檢索相關資料庫結構 (DDL)，問題: '{question}'", "DDL 檢索")
        return [
            'CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, total_amount REAL);',
            'CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, customer_name TEXT);'
        ]

    def get_related_documentation(self, question: str, top_n: int = 5):
        self.log(f"檢索相關文件，問題: '{question}'", "文件檢索")
        return [
            '業務規則：訂單總金額包含稅費。',
            '資料定義：customer_id 是客戶的唯一識別碼。'
        ]

    def submit_prompt(self, messages):
        # This is where the LLM would process the prompt
        # For testing, we'll just return a predefined analysis or a formatted prompt
        full_prompt = messages[0]['content'] # Assuming the prompt is the first message
        
        # Simulate LLM processing the analysis prompt
        if "SQL 查詢思考過程分析表" in full_prompt:
            # Extract relevant parts from the prompt to construct a mock analysis
            analysis_output = "## SQL 查詢思考過程分析表 (模擬結果)\n\n"
            analysis_output += "### 1. 原始問題\n"
            analysis_output += "用戶提出的問題已在提示中。\n\n"
            analysis_output += "### 2. 檢索到的相似問題與 SQL 範例\n"
            analysis_output += "系統檢索到以下相似問題及其對應的 SQL 範例，這些範例有助於理解問題的意圖和可能的查詢模式。\n"
            analysis_output += "| 相似問題 | 相關 SQL 範例 |\n"
            analysis_output += "|---|---|\n"
            
            # Extracting from the prompt is complex, so we'll use a placeholder for now
            # In a real scenario, the LLM would generate this based on the input
            analysis_output += "| 顯示所有訂單的總金額 | SELECT SUM(total_amount) FROM orders; |\n"
            analysis_output += "| 找出最近一個月的銷售額 | SELECT SUM(amount) FROM sales WHERE sale_date >= DATE('now', '-1 month'); |\n\n"

            analysis_output += "### 3. 檢索到的相關資料庫結構 (DDL)\n"
            analysis_output += "系統檢索到以下與問題相關的資料庫表結構定義 (DDL)。\n"
            analysis_output += "```sql\n"
            analysis_output += "CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, total_amount REAL);\n"
            analysis_output += "CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, customer_name TEXT);\n"
            analysis_output += "```\n\n"

            analysis_output += "### 4. 檢索到的相關業務文件\n"
            analysis_output += "系統檢索到以下與問題相關的業務文件或知識背景。\n"
            analysis_output += "業務規則：訂單總金額包含稅費。\n"
            analysis_output += "資料定義：customer_id 是客戶的唯一識別碼。\n\n"

            analysis_output += "### 5. 綜合分析與 SQL 構建思路\n"
            analysis_output += "LLM 根據上述資訊，識別出關鍵實體為 `orders` 和 `customers` 表。推斷出問題可能涉及訂單金額的匯總和時間篩選。利用 DDL 確定了 `order_id` 和 `customer_id` 的關聯。最終構建了 SQL 查詢。\n"
            analysis_output += "請務必以繁體中文生成所有分析結果和建議。\n"
            return analysis_output
        
        # Simulate SQL generation
        if "SELECT SUM(total_amount) FROM orders;" in full_prompt:
            return "SELECT SUM(total_amount) FROM orders;"
        
        return "模擬的 LLM 響應"

def run_test_ask_analysis(question: str, user_id: str = "test_user"):
    print(f"--- 測試開始: 分析問題 '{question}' ---")
    vn = MockVanna(user_id=user_id)

    # Simulate the generate_sql process and capture logs
    print("\n--- 模擬 generate_sql 過程 ---")
    # These calls will trigger the log messages in MockVanna
    similar_qas = vn.get_similar_question_sql(question)
    related_ddl = vn.get_related_ddl(question)
    related_docs = vn.get_related_documentation(question)

    # Collect logs from the queue
    logs = []
    while not vn.log_queue.empty():
        logs.append(vn.log_queue.get())
    
    # Format logs for the analysis prompt
    similar_qa_str = ""
    if similar_qas:
        for qa in similar_qas:
            similar_qa_str += f"| {qa['question']} | {qa['sql']} |\n"
    else:
        similar_qa_str = "無"

    related_ddl_str = ""
    if related_ddl:
        related_ddl_str = "\n".join(related_ddl)
    else:
        related_ddl_str = "無"

    related_docs_str = ""
    if related_docs:
        related_docs_str = "\n".join(related_docs)
    else:
        related_docs_str = "無"

    # Load the analysis prompt template
    ask_analysis_prompt_template = load_prompt_template('ask_analysis_prompt.txt')

    # Construct the full prompt for the analysis LLM
    analysis_prompt_content = f"""
原始問題:
{question}

檢索到的相似問題與 SQL 範例:
{similar_qa_str}

檢索到的相關資料庫結構 (DDL):
```sql
{related_ddl_str}
```

檢索到的相關業務文件:
{related_docs_str}
"""
    full_analysis_prompt = ask_analysis_prompt_template + analysis_prompt_content

    print("\n--- 提交分析提示給 LLM ---")
    analysis_table = vn.submit_prompt([{'role': 'user', 'content': full_analysis_prompt}])

    print("\n--- 生成的 SQL 查詢 (模擬) ---")
    generated_sql = vn.submit_prompt([{'role': 'user', 'content': f"根據問題 '{question}' 生成 SQL"}])
    print(generated_sql)

    print("\n--- SQL 查詢思考過程分析表 ---")
    print(analysis_table)

    print("\n--- 測試結束 ---")

if __name__ == '__main__':
    test_question = "找出所有客戶的訂單總金額"
    run_test_ask_analysis(test_question)