import logging
import threading
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, session, redirect, url_for
from werkzeug.utils import secure_filename
import os
import sys
from functools import wraps
import sqlite3
import uuid
import json
import re
import time
import tempfile
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DatabaseError, OperationalError
from queue import Queue
from threading import Thread
import traceback

# Helper function to load prompt templates
def load_prompt_template(filename):
    # 尝试从用户的提示词表中加载
    try:
        # 从session中获取当前用户ID
        from flask import session
        if 'username' in session:
            user_id = session['username']
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                # 提取文件名（不含扩展名）作为prompt_name
                prompt_name = os.path.splitext(filename)[0]
                # 优先查找用户自定义的非全局提示词
                cursor.execute(
                    "SELECT prompt_content FROM training_prompts WHERE prompt_name = ? AND is_global = 0", 
                    (prompt_name,)
                )
                result = cursor.fetchone()
                if result:
                    app.logger.info(f"Loaded custom prompt template '{filename}' from user database for user '{user_id}'")
                    return result[0]
                # 如果没有用户自定义的，则查找全局提示词（无论是用户自己设置的全局还是默认全局）
                cursor.execute(
                    "SELECT prompt_content FROM training_prompts WHERE prompt_name = ? AND is_global = 1", 
                    (prompt_name,)
                )
                result = cursor.fetchone()
                if result:
                    app.logger.info(f"Loaded global prompt template '{filename}' from user database for user '{user_id}'")
                    return result[0]
    except Exception as e:
        app.logger.warning(f"Failed to load prompt template from database: {e}")
        # 即使数据库加载失败，也继续尝试从文件加载
    
    # 从文件加载作为后备方案
    path = os.path.join('prompts', filename)
    
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            app.logger.info(f"Loaded prompt template '{filename}' from file system")
            return f.read()
    else:
        raise FileNotFoundError(f"Prompt template file not found in 'prompts/': {filename}")

# Add 'src' to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from vanna.ollama import Ollama
from vanna.openai import OpenAI_Chat
from vanna.anthropic import Anthropic_Chat
from vanna.google import GoogleGeminiChat
from vanna.chromadb import ChromaDB_VectorStore
from vanna.types import TrainingPlan

# --- App Setup ---
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', str(uuid.uuid4()))

# --- User Management ---
try:
    users_json = os.getenv('APP_USERS', '{"user1": "pass1", "user2": "pass2"}')
    users = json.loads(users_json)
except json.JSONDecodeError:
    app.logger.error("APP_USERS 環境變數格式錯誤，請使用正確的 JSON 格式。")
    users = {}

# 辅助函数：获取数据集中的表列表
def get_dataset_tables(user_id, dataset_id):
    """获取指定数据集中的所有表列表"""
    # 检查数据集是否存在并获取数据库路径
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
        if not row:
            return None, "Dataset not found"
        db_path = row[0]
    
    try:
        # 获取数据库中的表列表
        engine = create_engine(f'sqlite:///{db_path}')
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        
        # 获取每个表的DDL语句
        ddl_statements = []
        with engine.connect() as connection:
            for name in table_names:
                ddl = connection.execute(text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{name}';")).scalar()
                if ddl: ddl_statements.append(ddl + ";")
        
        return {
            'table_names': table_names,
            'ddl_statements': ddl_statements
        }, None
    except Exception as e:
        return None, str(e)

# Helper function to write logs to file
def write_ask_log(user_id: str, log_type: str, content: str):
    log_dir = os.path.join(os.getcwd(), 'ask_log')
    os.makedirs(log_dir, exist_ok=True)
    timestamp = int(time.time())
    file_path = os.path.join(log_dir, f"{user_id}_{log_type}_{timestamp}.log")
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"{content}\n")
    app.logger.info(f"Ask log written to: {file_path}")

def _get_all_ask_logs(user_id: str) -> dict:
    log_dir = os.path.join(os.getcwd(), 'ask_log')
    if not os.path.exists(log_dir):
        return {}

    all_logs = {}
    for filename in os.listdir(log_dir):
        if filename.startswith(f"{user_id}_") and filename.endswith(".log"):
            log_type_parts = filename.split('_')
            # Reconstruct log type, excluding user_id and timestamp
            # e.g., user1_get_similar_question_sql_results_1759994574.log -> get_similar_question_sql_results
            # Ensure to handle cases where log_type might contain multiple underscores
            log_type = "_".join(log_type_parts[1:-1])
            
            file_path = os.path.join(log_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    all_logs.setdefault(log_type, []).append(content)
            except Exception as e:
                app.logger.error(f"Error reading log file {filename}: {e}")
    
    # Join all contents for each log type
    return {log_type: "\n".join(contents) for log_type, contents in all_logs.items()}

def _delete_all_ask_logs(user_id: str):
    log_dir = os.path.join(os.getcwd(), 'ask_log')
    if not os.path.exists(log_dir):
        return

    for filename in os.listdir(log_dir):
        if filename.startswith(f"{user_id}_") and filename.endswith(".log"):
            file_path = os.path.join(log_dir, filename)
            try:
                os.remove(file_path)
                app.logger.info(f"Removed log file: {filename}")
            except Exception as e:
                app.logger.error(f"Error removing log file {filename}: {e}")

# --- Helper Functions ---
def get_user_db_path(user_id: str) -> str:
    db_dir = os.path.join(os.getcwd(), 'user_data')
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, f'training_data_{user_id}.sqlite')

def get_user_db_connection(user_id: str) -> sqlite3.Connection:
    db_path = get_user_db_path(user_id)
    return sqlite3.connect(db_path)

# --- Decorators ---
def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'status': 'error', 'message': 'User not authenticated.'}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- Database Initialization ---
def init_training_db(user_id: str):
    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            tables = {
                "training_ddl": "(id INTEGER PRIMARY KEY AUTOINCREMENT, ddl_statement TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
                "training_documentation": "(id INTEGER PRIMARY KEY AUTOINCREMENT, documentation_text TEXT NOT NULL, table_name TEXT, dataset_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(dataset_id, table_name))",
                "training_qa": "(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, sql_query TEXT NOT NULL, table_name TEXT, dataset_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
                "datasets": "(id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_name TEXT NOT NULL, db_path TEXT NOT NULL UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
                "correction_rules": "(id INTEGER PRIMARY KEY AUTOINCREMENT, incorrect_name TEXT NOT NULL UNIQUE, correct_name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
                "training_prompts": "(id INTEGER PRIMARY KEY AUTOINCREMENT, prompt_name TEXT NOT NULL, prompt_content TEXT NOT NULL, prompt_type TEXT, is_global INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(prompt_name, prompt_type))"
            }
            for table_name, schema in tables.items():
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} {schema};")
            
            def add_column_if_not_exists(table, column, col_type):
                cursor.execute(f"PRAGMA table_info({table})")
                if column not in [info[1] for info in cursor.fetchall()]:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            
            add_column_if_not_exists('training_documentation', 'dataset_id', 'TEXT')
            add_column_if_not_exists('training_qa', 'dataset_id', 'TEXT')
            
            # 初始化一些基础提示词类型
            try:
                base_prompt_types = [
                    ('ask_analysis_prompt', '用於分析用戶問題和生成SQL的提示詞'),
                    ('qa_generation_system_prompt', '用於從SQL生成問答配對的提示詞'),
                    ('documentation_prompt', '用於生成數據庫文檔的提示詞')
                ]
                
                # 检查是否已有基础提示词，如果没有则插入
                for prompt_name, prompt_desc in base_prompt_types:
                    cursor.execute("SELECT COUNT(*) FROM training_prompts WHERE prompt_name = ?", (prompt_name,))
                    if cursor.fetchone()[0] == 0:
                        # 尝试从全局提示词文件加载内容
                        try:
                            prompt_content = load_prompt_template(f"{prompt_name}.txt")
                            cursor.execute(
                                "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, is_global) VALUES (?, ?, ?, ?)",
                                (prompt_name, prompt_content, prompt_desc, 1)
                            )
                        except Exception as e:
                            app.logger.warning(f"Failed to load default prompt {prompt_name}: {e}")
            except Exception as e:
                app.logger.warning(f"Failed to initialize base prompt types: {e}")
            
            conn.commit()
    except sqlite3.Error as e:
        app.logger.error(f"Could not initialize/update training database for user '{user_id}': {e}")
        raise

# --- Vanna AI Integration ---
class MyVanna(ChromaDB_VectorStore):
    def __init__(self, user_id: str, config=None):
        app.logger.info(f"Initializing MyVanna instance for user: {user_id}")
        self.log_queue = Queue()
        self.user_id = user_id
        self.config = config or {}
        self.llm_choice = None
        self.llm_instance = None

        # Determine which LLM to use based on environment variables
        self.llm_choice = self._get_llm_choice()
        
        # Store LLM configuration without instantiating abstract classes
        self.llm_config = {
            'ollama_model': os.getenv('OLLAMA_MODEL'),
            'ollama_host': os.getenv('OLLAMA_HOST', 'http://host.docker.internal:11434'),
            'openai_api_key': os.getenv('OPENAI_API_KEY'),
            'openai_model': os.getenv('OPENAI_MODEL', 'gpt-4-turbo'),
            'anthropic_api_key': os.getenv('ANTHROPIC_API_KEY'),
            'anthropic_model': os.getenv('ANTHROPIC_MODEL', 'claude-3-opus-20240229'),
            'google_api_key': os.getenv('GOOGLE_API_KEY'),
            'google_model': os.getenv('GOOGLE_MODEL', 'gemini-1.5-pro-latest'),
        }
        
        # Log LLM choice
        if self.llm_choice == 'openai':
            app.logger.info(f"Using OpenAI for user: {user_id} with model: {self.llm_config['openai_model']}")
        elif self.llm_choice == 'ollama':
            app.logger.info(f"Using Ollama for user: {user_id} with model: {self.llm_config['ollama_model']}, host: {self.llm_config['ollama_host']}")
        elif self.llm_choice == 'anthropic':
            app.logger.info(f"Using Anthropic for user: {user_id} with model: {self.llm_config['anthropic_model']}")
        elif self.llm_choice == 'google':
            app.logger.info(f"Using Google Gemini for user: {user_id} with model: {self.llm_config['google_model']}")
        else:
            app.logger.warning(f"Unknown LLM choice: {self.llm_choice}")

        collection_name = f"vanna_training_data_{user_id}"
        self.config['collection_name'] = collection_name
        
        # Initialize parent class
        app.logger.info(f"Initializing ChromaDB_VectorStore for user: {user_id} with collection: {collection_name}")
        ChromaDB_VectorStore.__init__(self, config=self.config)

        # Store original methods to call them and log their results
        self._original_get_similar_question_sql = super().get_similar_question_sql
        self._original_get_related_ddl = super().get_related_ddl
        self._original_get_related_documentation = super().get_related_documentation

    # Implement abstract methods required by VannaBase
    def system_message(self, message: str) -> any:
        # Simple message wrapper implementation
        return {'role': 'system', 'content': message}

    def user_message(self, message: str) -> any:
        # Simple message wrapper implementation
        return {'role': 'user', 'content': message}

    def assistant_message(self, message: str) -> any:
        # Simple message wrapper implementation
        return {'role': 'assistant', 'content': message}

    def submit_prompt(self, prompt, **kwargs) -> str:
        # Import LLM classes here to avoid circular imports
        if self.llm_choice == 'openai':
            from vanna.openai import OpenAI_Chat
            # 设置配置
            self.config['api_key'] = self.llm_config['openai_api_key']
            self.config['model'] = self.llm_config['openai_model']
            try:
                openai_chat = OpenAI_Chat(config=self.config)
                return openai_chat.submit_prompt(prompt, **kwargs)
            except Exception as e:
                app.logger.error(f"Error with OpenAI_Chat: {e}")
                raise
        elif self.llm_choice == 'ollama':
            # Ollama类是抽象类，需要实现多个向量相关的抽象方法
            # ChromaDB_VectorStore类已经实现了这些向量相关的方法
            # 所以我们创建一个临时类，同时继承这两个类
            from vanna.ollama.ollama import Ollama
            from vanna.chromadb.chromadb_vector import ChromaDB_VectorStore
            
            # 设置Ollama配置
            self.config['model'] = self.llm_config['ollama_model']
            self.config['ollama_host'] = self.llm_config['ollama_host']
            
            try:
                # 创建一个临时类，同时继承Ollama和ChromaDB_VectorStore
                # 这样就能同时获得Ollama的LLM功能和ChromaDB_VectorStore的向量存储功能
                class OllamaWithVectorStore(Ollama, ChromaDB_VectorStore):
                    def __init__(self, config):
                        # 初始化两个父类
                        ChromaDB_VectorStore.__init__(self, config=config)
                        
                        # 导入ollama库
                        try:
                            ollama = __import__("ollama")
                        except ImportError:
                            raise ImportError("需要安装ollama库: pip install ollama")
                        
                        # 确保config包含必要的参数
                        if not config:
                            raise ValueError("config must contain at least Ollama model")
                        if 'model' not in config:
                            raise ValueError("config must contain at least Ollama model")
                        
                        # 初始化Ollama所需的属性
                        self.host = config.get("ollama_host", "http://localhost:11434")
                        self.model = config["model"]
                        if ":" not in self.model:
                            self.model += ":latest"
                        
                        self.ollama_timeout = config.get("ollama_timeout", 240.0)
                        self.keep_alive = config.get('keep_alive', None)
                        self.ollama_options = config.get('options', {})
                        self.num_ctx = self.ollama_options.get('num_ctx', 2048)
                        
                        # 初始化ollama_client
                        from httpx import Timeout
                        self.ollama_client = ollama.Client(self.host, timeout=Timeout(self.ollama_timeout))
                        
                        # 拉取模型（如果需要）
                        self._pull_model_if_ne(self.ollama_client, self.model)
                    
                    @staticmethod
                    def _pull_model_if_ne(ollama_client, model):
                        model_response = ollama_client.list()
                        model_lists = [model_element['model'] for model_element in
                                    model_response.get('models', [])]
                        if model not in model_lists:
                            ollama_client.pull(model)
                
                # 实例化这个临时类
                ollama_instance = OllamaWithVectorStore(config=self.config)
                return ollama_instance.submit_prompt(prompt, **kwargs)
            except Exception as e:
                app.logger.error(f"Error with Ollama: {e}")
                raise
        elif self.llm_choice == 'anthropic':
            from vanna.anthropic import Anthropic_Chat
            self.config['api_key'] = self.llm_config['anthropic_api_key']
            self.config['model'] = self.llm_config['anthropic_model']
            try:
                anthropic_chat = Anthropic_Chat(config=self.config)
                return anthropic_chat.submit_prompt(prompt, **kwargs)
            except Exception as e:
                app.logger.error(f"Error with Anthropic_Chat: {e}")
                raise
        elif self.llm_choice == 'google':
            from vanna.google import GoogleGeminiChat
            self.config['api_key'] = self.llm_config['google_api_key']
            self.config['model'] = self.llm_config['google_model']
            try:
                google_chat = GoogleGeminiChat(config=self.config)
                return google_chat.submit_prompt(prompt, **kwargs)
            except Exception as e:
                app.logger.error(f"Error with GoogleGeminiChat: {e}")
                raise
        else:
            # Default implementation or raise exception
            raise ValueError(f"Unsupported LLM choice: {self.llm_choice}")

    # Store original method for generate_sql
    def _get_original_generate_sql(self):
        if not hasattr(self, '_original_generate_sql'):
            self._original_generate_sql = super().generate_sql
        return self._original_generate_sql

    def get_similar_question_sql(self, question: str, **kwargs):
        top_n = kwargs.pop('top_n', 5)
        log_message_calling = f"Calling get_similar_question_sql with question: '{question}', top_n: {top_n}"
        app.logger.info(log_message_calling)
        write_ask_log(self.user_id, "get_similar_question_sql_calling", log_message_calling)
        self.log_queue.put({'type': 'thinking_step', 'step': '開始相似問題檢索', 'details': {'question': question, 'top_n': top_n}})
        results = self._original_get_similar_question_sql(question, top_n=top_n, **kwargs)
        log_message_results = f"get_similar_question_sql raw results: {results}"
        app.logger.info(log_message_results)
        write_ask_log(self.user_id, "get_similar_question_sql_results", log_message_results)
        self.log_queue.put({'type': 'thinking_step', 'step': '相似問題檢索完成', 'details': results})
        return results

    def get_related_ddl(self, question: str, **kwargs):
        top_n = kwargs.pop('top_n', 5)
        log_message_calling = f"Calling get_related_ddl with question: '{question}', top_n: {top_n}"
        app.logger.info(log_message_calling)
        write_ask_log(self.user_id, "get_related_ddl_calling", log_message_calling)
        self.log_queue.put({'type': 'thinking_step', 'step': '開始 DDL 檢索', 'details': {'question': question, 'top_n': top_n}})
        results = self._original_get_related_ddl(question, top_n=top_n, **kwargs)
        log_message_results = f"get_related_ddl raw results: {results}"
        app.logger.info(log_message_results)
        write_ask_log(self.user_id, "get_related_ddl_results", log_message_results)
        self.log_queue.put({'type': 'thinking_step', 'step': 'DDL 檢索完成', 'details': results})
        return results

    def get_related_documentation(self, question: str, **kwargs):
        top_n = kwargs.pop('top_n', 5)
        log_message_calling = f"Calling get_related_documentation with question: '{question}', top_n: {top_n}"
        app.logger.info(log_message_calling)
        write_ask_log(self.user_id, "get_related_documentation_calling", log_message_calling)
        self.log_queue.put({'type': 'thinking_step', 'step': '開始文件檢索', 'details': {'question': question, 'top_n': top_n}})
        results = self._original_get_related_documentation(question, top_n=top_n, **kwargs)
        log_message_results = f"get_related_documentation raw results: {results}"
        app.logger.info(log_message_results)
        write_ask_log(self.user_id, "get_related_documentation_results", log_message_results)
        self.log_queue.put({'type': 'thinking_step', 'step': '文件檢索完成', 'details': results})
        return results

    def generate_sql(self, question: str, **kwargs):
        self.log_queue.put({'type': 'thinking_step', 'step': 'LLM 開始生成 SQL', 'details': {'question': question}})
        sql_response = self._original_generate_sql(question, **kwargs)
        self.log_queue.put({'type': 'thinking_step', 'step': 'LLM 完成生成 SQL', 'details': {'sql_response': sql_response}})
        return sql_response

    def _get_llm_choice(self):
        # Determine which LLM to use based on environment variables
        if os.getenv('OLLAMA_MODEL'):
            return 'ollama'
        elif os.getenv('OPENAI_API_KEY'):
            return 'openai'
        elif os.getenv('ANTHROPIC_API_KEY'):
            return 'anthropic'
        elif os.getenv('GOOGLE_API_KEY'):
            return 'google'
        else:
            return 'openai'  # Default to OpenAI if no other LLM is configured

    def log(self, message: str, title: str = "資訊"):
        self.log_queue.put({'type': 'thinking_step', 'step': title, 'details': {'message': message}})

_vanna_instances = {}
def get_vanna_instance(user_id: str) -> MyVanna:
    if user_id not in _vanna_instances:
        app.logger.info(f"Creating new MyVanna instance for user: {user_id}")
        _vanna_instances[user_id] = MyVanna(user_id=user_id)
    else:
        app.logger.info(f"Reusing existing MyVanna instance for user: {user_id}")
    return _vanna_instances[user_id]

def _noop_pull_model(self, client, model_name):
    app.logger.info(f"Patch: Skipping Ollama model pull for '{model_name}'")
Ollama._Ollama__pull_model_if_ne = _noop_pull_model

def configure_vanna_for_request(vn, user_id, dataset_id): # Add dataset_id as a parameter
    if not dataset_id:
        raise Exception("No active dataset selected.")
    
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
    if not row:
        raise Exception("Active dataset not found.")
    
    engine = create_engine(f"sqlite:///{row[0]}")
    vn.engine = engine
    vn.run_sql = lambda sql: pd.read_sql_query(sql, engine)
    vn.run_sql_is_set = True
    return vn

# --- Flask Routes ---
@app.route('/')
def index():
    if 'username' not in session: return redirect(url_for('login'))
    return render_template('index.html', username=session['username'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form.get('password')
        if users.get(username) == password:
            session['username'] = username
            init_training_db(username)
            return redirect(url_for('index'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('active_dataset_id', None)
    return redirect(url_for('login'))

@app.route('/api/datasets', methods=['GET', 'POST', 'PUT', 'DELETE'])
@api_login_required
def handle_datasets():
    user_id = session['username']
    if request.method == 'GET':
        with get_user_db_connection(user_id) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, dataset_name AS name, created_at FROM datasets ORDER BY created_at DESC")
            return jsonify({'status': 'success', 'datasets': [dict(row) for row in cursor.fetchall()]})
    
    elif request.method == 'POST':
        dataset_name = request.form.get('dataset_name')
        files = request.files.getlist('files')
        if not dataset_name or not files:
            return jsonify({'status': 'error', 'message': 'Dataset name and files are required.'}), 400
        
        db_path = os.path.join('user_data', 'datasets', f'{uuid.uuid4().hex}.sqlite')
        try:
            engine = create_engine(f'sqlite:///{db_path}')
            for file in files:
                df = pd.read_csv(file.stream)
                table_name = os.path.splitext(secure_filename(file.filename))[0].replace('-', '_').replace(' ', '_')
                df.to_sql(table_name, engine, index=False, if_exists='replace')
            
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO datasets (dataset_name, db_path) VALUES (?, ?)", (dataset_name, db_path))
                new_id = cursor.lastrowid
                conn.commit()
            return jsonify({'status': 'success', 'dataset': {'id': new_id, 'dataset_name': dataset_name}}), 201
        except Exception as e:
            if os.path.exists(db_path): os.remove(db_path)
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    elif request.method == 'PUT':
        data = request.json
        dataset_id = data.get('dataset_id')
        new_name = data.get('new_name')
        
        if not dataset_id or not new_name:
            return jsonify({'status': 'error', 'message': 'Dataset ID and new name are required.'}), 400
        
        try:
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                # 检查数据集是否存在
                cursor.execute("SELECT id FROM datasets WHERE id = ?", (dataset_id,))
                if not cursor.fetchone():
                    return jsonify({'status': 'error', 'message': 'Dataset not found.'}), 404
                
                # 更新数据集名称
                cursor.execute("UPDATE datasets SET dataset_name = ? WHERE id = ?", (new_name, dataset_id))
                conn.commit()
            
            return jsonify({'status': 'success', 'dataset': {'id': dataset_id, 'dataset_name': new_name}})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    elif request.method == 'DELETE':
        data = request.json
        dataset_id = data.get('dataset_id')
        
        if not dataset_id:
            return jsonify({'status': 'error', 'message': 'Dataset ID is required.'}), 400
        
        try:
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                # 检查数据集是否存在并获取数据库路径
                cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'status': 'error', 'message': 'Dataset not found.'}), 404
                
                db_path = row[0]
                
                # 删除数据集记录
                cursor.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
                conn.commit()
            
            # 删除实际的数据库文件
            if os.path.exists(db_path):
                os.remove(db_path)
            
            return jsonify({'status': 'success', 'dataset_id': dataset_id})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/datasets/activate', methods=['POST'])
@api_login_required
def activate_dataset():
    user_id = session['username']
    dataset_id = request.get_json().get('dataset_id')
    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'dataset_id is required.'}), 400
    
    try:
        session['active_dataset_id'] = dataset_id
        vn = get_vanna_instance(user_id)
        vn = configure_vanna_for_request(vn, user_id, dataset_id) # Pass dataset_id
        
        inspector = inspect(vn.engine)
        table_names = inspector.get_table_names()
        ddl_statements = []
        with vn.engine.connect() as connection:
            for name in table_names:
                ddl = connection.execute(text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{name}';")).scalar()
                if ddl: ddl_statements.append(ddl + ";")

        training_data = vn.get_training_data()
        is_trained = not training_data.empty if training_data is not None else False

        return jsonify({
            'status': 'success', 
            'message': f"Dataset activated.", 
            'table_names': table_names, 
            'ddl': ddl_statements,
            'is_trained': is_trained
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/datasets/<dataset_id>/tables', methods=['GET'])
@api_login_required
def get_tables_in_dataset(dataset_id):
    """获取指定数据集中的表列表"""
    user_id = session['username']
    
    tables_info, error = get_dataset_tables(user_id, dataset_id)
    if error:
        return jsonify({'status': 'error', 'message': error}), 404 if error == "Dataset not found" else 500
    
    return jsonify({
        'status': 'success',
        'dataset_id': dataset_id,
        'table_names': tables_info['table_names'],
        'ddl_statements': tables_info['ddl_statements']
    })

@app.route('/api/datasets/files', methods=['POST', 'DELETE'])
@api_login_required
def handle_dataset_files():
    user_id = session['username']
    dataset_id = request.args.get('dataset_id')
    
    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'dataset_id is required.'}), 400
    
    # 检查数据集是否存在
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'status': 'error', 'message': 'Dataset not found.'}), 404
        
        db_path = row[0]
    
    if request.method == 'POST':
        # 向数据集添加新的CSV文件
        files = request.files.getlist('files')
        if not files:
            return jsonify({'status': 'error', 'message': 'No files uploaded.'}), 400
        
        try:
            engine = create_engine(f'sqlite:///{db_path}')
            added_tables = []
            
            for file in files:
                if not file.name.endswith('.csv'):
                    continue
                
                df = pd.read_csv(file.stream)
                table_name = os.path.splitext(secure_filename(file.filename))[0].replace('-', '_').replace(' ', '_')
                df.to_sql(table_name, engine, index=False, if_exists='replace')
                added_tables.append(table_name)
            
            # 获取更新后的表列表
            tables_info, _ = get_dataset_tables(user_id, dataset_id)
            all_tables = tables_info['table_names']
            
            return jsonify({
                'status': 'success', 
                'message': f'Added {len(added_tables)} table(s) to dataset.',
                'added_tables': added_tables,
                'all_tables': all_tables
            })
        except Exception as e:
            app.logger.error(f'Error adding files to dataset: {e}')
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    elif request.method == 'DELETE':
        # 从数据集删除表
        data = request.json
        table_name = data.get('table_name')
        
        if not table_name:
            return jsonify({'status': 'error', 'message': 'table_name is required.'}), 400
        
        try:
            engine = create_engine(f'sqlite:///{db_path}')
            with engine.connect() as connection:
                # 检查表是否存在
                inspector = inspect(engine)
                if table_name not in inspector.get_table_names():
                    return jsonify({'status': 'error', 'message': f'Table {table_name} not found.'}), 404
                
                # 删除表
                connection.execute(text(f'DROP TABLE IF EXISTS {table_name}'))
                connection.commit()
            
            # 获取更新后的表列表
            tables_info, _ = get_dataset_tables(user_id, dataset_id)
            all_tables = tables_info['table_names']
            
            return jsonify({
                'status': 'success', 
                'message': f'Table {table_name} deleted successfully.',
                'all_tables': all_tables
            })
        except Exception as e:
            app.logger.error(f'Error deleting table from dataset: {e}')
            return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/training_data', methods=['GET'])
@api_login_required
def get_training_data():
    user_id = session['username']
    table_name = request.args.get('table_name', 'global')
    page = int(request.args.get('page', 1))
    page_size = 10  # Fixed page size
    offset = (page - 1) * page_size
    dataset_id = session.get('active_dataset_id')

    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400

    with get_user_db_connection(user_id) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get documentation
        cursor.execute("SELECT documentation_text FROM training_documentation WHERE table_name = ? AND dataset_id = ?", (table_name, dataset_id))
        doc_row = cursor.fetchone()
        documentation = doc_row['documentation_text'] if doc_row else ""
        
        # Get total count for pagination
        cursor.execute("SELECT COUNT(*) FROM training_qa WHERE table_name = ? AND dataset_id = ?", (table_name, dataset_id))
        total_count = cursor.fetchone()[0]
        total_pages = (total_count + page_size - 1) // page_size

        # Get paginated QA pairs
        cursor.execute("""
            SELECT id, question, sql_query as sql
            FROM training_qa
            WHERE table_name = ? AND dataset_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (table_name, dataset_id, page_size, offset))
        qa_pairs = [dict(row) for row in cursor.fetchall()]
        
        # Get dataset analysis
        cursor.execute("SELECT documentation_text FROM training_documentation WHERE table_name = ? AND dataset_id = ?", ('__dataset_analysis__', dataset_id))
        analysis_row = cursor.fetchone()
        dataset_analysis = analysis_row['documentation_text'] if analysis_row else ""

    response_data = {
        'documentation': documentation,
        'qa_pairs': qa_pairs,
        'dataset_analysis': dataset_analysis,
        'pagination': {
            'current_page': page,
            'total_pages': total_pages,
            'total_count': total_count
        }
    }

    # Save to temporary file and print info
    try:
        temp_dir = os.path.join(os.getcwd(), 'temp_vanna_data')
        os.makedirs(temp_dir, exist_ok=True)
        temp_file_path = os.path.join(temp_dir, f"training_data_{user_id}_{dataset_id}_{int(time.time())}.json")
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            json.dump(response_data, f, ensure_ascii=False, indent=2)
        app.logger.info(f"Training data saved to temporary file: {temp_file_path}")
        app.logger.info(f"Temporary file content:\n{json.dumps(response_data, ensure_ascii=False, indent=2)}")
    except Exception as e:
        app.logger.error(f"Error saving training data to temporary file: {e}")

    return jsonify(response_data)

@app.route('/api/save_documentation', methods=['POST'])
@api_login_required
def save_documentation():
    user_id = session['username']
    data = request.get_json()
    doc_content = data.get('documentation', '')
    table_name = data.get('table_name', 'global')
    dataset_id = session.get('active_dataset_id')

    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400

    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            if doc_content.strip():
                cursor.execute(
                    "REPLACE INTO training_documentation (dataset_id, table_name, documentation_text) VALUES (?, ?, ?)",
                    (dataset_id, table_name, doc_content)
                )
                message = f"Documentation for table '{table_name}' saved."
            else:
                cursor.execute("DELETE FROM training_documentation WHERE dataset_id = ? AND table_name = ?", (dataset_id, table_name))
                message = f"Documentation for table '{table_name}' cleared."
            conn.commit()
        return jsonify({'status': 'success', 'message': message})
    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/add_qa_question', methods=['POST'])
@api_login_required
def add_qa_question():
    user_id = session['username']
    data = request.get_json()
    question = data.get('question')
    sql_query = data.get('sql')
    table_name = data.get('table_name', 'global')
    dataset_id = session.get('active_dataset_id')

    if not all([question, sql_query, dataset_id]):
        return jsonify({'status': 'error', 'message': 'Question, SQL, and active dataset are required.'}), 400

    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO training_qa (question, sql_query, table_name, dataset_id) VALUES (?, ?, ?, ?)",
                (question, sql_query, table_name, dataset_id)
            )
            new_id = cursor.lastrowid
            conn.commit()
        return jsonify({'status': 'success', 'message': 'QA pair added successfully.', 'id': new_id})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'info', 'message': 'QA pair may already exist.'}), 200
    except sqlite3.Error as e:
        app.logger.error(f"Database error for user '{user_id}' in add_qa_question: {e}")
        return jsonify({'status': 'error', 'message': f"Database error: {e}"}), 500

@app.route('/api/train', methods=['POST'])
@api_login_required
def train_model():
    user_id = session['username']
    dataset_id = session.get('active_dataset_id')
    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400
    vn = get_vanna_instance(user_id)
    vn = configure_vanna_for_request(vn, user_id, dataset_id)

    def generate_progress():
        try:
            ddl = request.form.get('ddl')
            documentation = request.form.get('doc', '')
            qa_pairs_json = request.form.get('qa_pairs')
            qa_pairs = json.loads(qa_pairs_json) if qa_pairs_json else []

            yield f"data: {json.dumps({'percentage': 0, 'message': '開始訓練...', 'log': 'Training process initiated.'})}\n\n"
            app.logger.info("Training process initiated.")
            
            total_steps = (1 if ddl else 0) + (1 if documentation else 0) + (1 if qa_pairs else 0)
            completed_steps = 0

            if ddl:
                app.logger.info("Starting DDL training.")
                vn.train(ddl=ddl)
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*100, 'message': 'DDL 訓練完成。', 'log': 'DDL training completed.'})}\n\n"
                app.logger.info("DDL training completed.")
            
            if documentation:
                app.logger.info("Starting documentation training.")
                vn.train(documentation=documentation)
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*100, 'message': '文件訓練完成。', 'log': 'Documentation training completed.'})}\n\n"
                app.logger.info("Documentation training completed.")

            if qa_pairs:
                app.logger.info(f"Starting QA pair training for {len(qa_pairs)} pairs.")
                for pair in qa_pairs:
                    if pair.get('question') and pair.get('sql'):
                        vn.train(question=pair['question'], sql=pair['sql'])
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*100, 'message': f'問答配對 ({len(qa_pairs)} 組) 訓練完成。', 'log': f'QA pair training for {len(qa_pairs)} pairs completed.'})}\n\n"
                app.logger.info(f"QA pair training for {len(qa_pairs)} pairs completed.")

            yield f"data: {json.dumps({'percentage': 100, 'message': '所有訓練步驟已完成。', 'log': 'All training steps completed.'})}\n\n"
            app.logger.info("All training steps completed.")

        except Exception as e:
            app.logger.error(f"Training failed for user '{user_id}': {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(stream_with_context(generate_progress()), mimetype='text/event-stream')

@app.route('/api/ask', methods=['POST'])
@api_login_required
def ask_question():
    user_id = session['username']
    data = request.json
    question = data.get('question')
    if not question:
        return jsonify({'status': 'error', 'message': 'Question is required.'}), 400

    vn_instance = get_vanna_instance(user_id)
    dataset_id = session.get('active_dataset_id')

    def run_vanna_in_thread(vn_instance: MyVanna, question: str, dataset_id: str, user_id: str):
        """
        在新執行緒中執行 Vanna 相關操作，並將日誌傳送到主應用程式的隊列。
        """
        try:
            # 確保使用傳入的 vn_instance
            vn = configure_vanna_for_request(vn_instance, user_id, dataset_id)
        
            # Try to load training data from the temporary file
            try:
                temp_dir = os.path.join(os.getcwd(), 'temp_vanna_data')
                if os.path.exists(temp_dir):
                    # Find the latest temporary file for the current user and dataset
                    latest_file = None
                    latest_timestamp = 0
                    for filename in os.listdir(temp_dir):
                        if filename.startswith(f"training_data_{user_id}_{dataset_id}_") and filename.endswith(".json"):
                            try:
                                # Extract timestamp from filename
                                timestamp_str = filename.split('_')[-1].split('.')[0]
                                timestamp = int(timestamp_str)
                                if timestamp > latest_timestamp:
                                    latest_timestamp = timestamp
                                    latest_file = os.path.join(temp_dir, filename)
                            except ValueError:
                                continue # Skip files with invalid timestamp format

                    if latest_file and os.path.exists(latest_file):
                        with open(latest_file, 'r', encoding='utf-8') as f:
                            temp_training_data = json.load(f)
                        
                        vn.log(f"從暫存文件加載訓練數據: {latest_file}", "資訊")
                        app.logger.info(f"Loading training data from temporary file: {latest_file}")
                        app.logger.info(f"Temporary training data content: {json.dumps(temp_training_data, ensure_ascii=False, indent=2)}")

                        # Load documentation
                        if temp_training_data.get('documentation'):
                            # 確保 documentation 是字串，以避免型別錯誤
                            documentation_data = temp_training_data['documentation']
                            if isinstance(documentation_data, list):
                                for doc_item in documentation_data:
                                    if isinstance(doc_item, str):
                                        vn.train(documentation=doc_item)
                                    else:
                                        vn.log(f"跳過無效的文檔項目: {doc_item}", "警告")
                            elif isinstance(documentation_data, str):
                                vn.train(documentation=documentation_data)
                            else:
                                vn.log(f"跳過無效的文檔數據類型: {type(documentation_data)}", "警告")
                            vn.log("已從暫存文件加載文檔", "資訊")
                            app.logger.info("Loaded documentation from temp file.")
                            app.logger.info(f"Vanna training data count after documentation: {len(vn.get_training_data())}")

                        # Load QA pairs
                        if temp_training_data.get('qa_pairs'):
                            for qa_pair in temp_training_data['qa_pairs']:
                                if isinstance(qa_pair, dict) and qa_pair.get('question') and qa_pair.get('sql'):
                                    # 確保 question 和 sql 都是字串
                                    question_str = str(qa_pair['question'])
                                    sql_str = str(qa_pair['sql'])
                                    vn.train(question=question_str, sql=sql_str)
                                else:
                                    vn.log(f"跳過無效的問答配對項目: {qa_pair}", "警告")
                            vn.log(f"已從暫存文件加載 {len(temp_training_data.get('qa_pairs', []))} 個問答配對", "資訊")
                            app.logger.info(f"Loaded {len(temp_training_data.get('qa_pairs', []))} QA pairs from temp file.")
                            app.logger.info(f"Vanna training data count after QA pairs: {len(vn.get_training_data())}")
                        
                        # Load dataset analysis (as documentation)
                        if temp_training_data.get('dataset_analysis'):
                            # 確保 dataset_analysis 是字串，以避免型別錯誤
                            dataset_analysis_data = temp_training_data['dataset_analysis']
                            if isinstance(dataset_analysis_data, list):
                                for analysis_item in dataset_analysis_data:
                                    if isinstance(analysis_item, str):
                                        vn.train(documentation=analysis_item)
                                    else:
                                        vn.log(f"跳過無效的數據集分析項目: {analysis_item}", "警告")
                            elif isinstance(dataset_analysis_data, str):
                                vn.train(documentation=dataset_analysis_data)
                            else:
                                vn.log(f"跳過無效的數據集分析數據類型: {type(dataset_analysis_data)}", "警告")
                            vn.log("已從暫存文件加載數據集分析", "資訊")
                            app.logger.info("Loaded dataset analysis from temp file.")
                            app.logger.info(f"Vanna training data count after dataset analysis: {len(vn.get_training_data())}")
                    else:
                        app.logger.info("No temporary training data file found for current user/dataset.")
                else:
                    app.logger.info("Temporary Vanna data directory does not exist.")
            except Exception as e:
                app.logger.error(f"Error loading training data from temporary file in ask function: {e}")
                vn.log(f"從暫存文件加載訓練數據時出錯: {e}", "錯誤")

            # 現在所有操作都將使用同一個 vn 實例及其 log_queue
            sql = vn.generate_sql(question=question)

            # 檢查並修正不完整的 WITH 語句
            if re.match(r'^\s*WITH\s+.*?\)\s*$', sql, re.DOTALL | re.IGNORECASE):
                # 嘗試從 WITH 語句中提取 CTE 名稱
                cte_match = re.match(r'^\s*WITH\s+(\w+)\s+AS\s+\(', sql, re.DOTALL | re.IGNORECASE)
                if cte_match:
                    cte_name = cte_match.group(1)
                    corrected_sql = f"{sql}\nSELECT * FROM {cte_name};"
                    app.logger.warning(f"Detected incomplete WITH statement. Corrected SQL: {corrected_sql}")
                    vn.log(f"檢測到不完整的 WITH 語句，已嘗試修正為: {corrected_sql}", "警告")
                    sql = corrected_sql
                else:
                    app.logger.warning(f"Detected incomplete WITH statement but could not extract CTE name. Original SQL: {sql}")
                    vn.log(f"檢測到不完整的 WITH 語句，但無法提取 CTE 名稱。原始 SQL: {sql}", "警告")

            try:
                df = vn.run_sql(sql=sql)
            except OperationalError as e:
                if "no such table" in str(e):
                    app.logger.warning(f"SQL execution skipped, table not found: {e}")
                    vn.log(f"SQL 執行被跳過，因為找不到資料表。", "警告")
                else:
                    app.logger.error(f"SQL execution failed: {e}", exc_info=True)
                    vn.log(f"SQL 執行失敗: {e}", "錯誤")
                df = pd.DataFrame() # 建立一個空的 DataFrame，讓後續流程可以繼續
        
            # correct_sql = None # Commented out as correct_sql is not implemented
            if df.empty:
                app.logger.warning("SQL 查詢結果為空，嘗試修正 SQL...")
                vn.log("SQL 查詢結果為空，嘗試修正 SQL...", "警告")
                # correct_sql = vn.correct_sql(question=question, sql=sql, error=None) # Commented out as correct_sql is not implemented
                # if correct_sql:
                #     sql = correct_sql
                #     df = vn.run_sql(sql=sql)
                #     vn.log("已生成修正後的 SQL 並執行", "資訊")
        
            app.logger.info(f"Generated SQL: {sql}")
            app.logger.info(f"SQL Result: {df.head()}")

            # --- 動態生成提示詞並發送給 Ollama 進行分析 ---
            analysis_result = None
            try:
                # 讀取 ask_analysis_prompt.txt 模板
                ask_analysis_prompt_template = load_prompt_template('ask_analysis_prompt.txt')

                # 讀取所有日誌內容
                all_logs_content = _get_all_ask_logs(user_id)

                # 格式化相似問題和 SQL 範例
                formatted_similar_qa = all_logs_content.get("get_similar_question_sql_results", "無")
                
                # 填充模板
                dynamic_prompt_content = ask_analysis_prompt_template.replace(
                    "[用戶提出的原始自然語言問題]", question
                ).replace(
                    "[列出檢索到的相似問題和 SQL 範例]", formatted_similar_qa
                ).replace(
                    "[列出檢索到的相關 DDL 語句]", all_logs_content.get("get_related_ddl_results", "無")
                ).replace(
                    "[列出檢索到的相關業務文件內容]", all_logs_content.get("get_related_documentation_results", "無")
                )

                # 保存動態提示詞到歷史紀錄
                try:
                    prompt_history_dir = os.path.join(os.getcwd(), 'prompt_history')
                    os.makedirs(prompt_history_dir, exist_ok=True)
                    timestamp = int(time.time())
                    prompt_filename = f"{user_id}_dynamic_prompt_{timestamp}.txt"
                    prompt_filepath = os.path.join(prompt_history_dir, prompt_filename)
                    with open(prompt_filepath, 'w', encoding='utf-8') as f:
                        f.write(dynamic_prompt_content)
                    app.logger.info(f"Dynamic prompt saved to history: {prompt_filepath}")
                except Exception as e:
                    app.logger.error(f"Error saving dynamic prompt to history: {e}")

                # 將動態提示詞發送給 Ollama 進行分析 (支援分塊)
                try:
                    vn.log("正在將思考過程發送給 Ollama 進行分析...", "資訊")
                    app.logger.info(f"Sending dynamic prompt to Ollama for analysis for user '{user_id}'. Total prompt length: {len(dynamic_prompt_content)}")

                    CHUNK_SIZE = 8000  # 設定每個分塊的大小
                    if len(dynamic_prompt_content) > CHUNK_SIZE:
                        # 如果提示詞過長，則進行分塊處理
                        chunks = [dynamic_prompt_content[i:i + CHUNK_SIZE] for i in range(0, len(dynamic_prompt_content), CHUNK_SIZE)]
                        analysis_parts = []
                        vn.log(f"提示詞過長，將分 {len(chunks)} 個區塊進行分析。", "資訊")
                        
                        for i, chunk in enumerate(chunks):
                            vn.log(f"正在分析第 {i+1}/{len(chunks)} 個區塊...", "資訊")
                            app.logger.info(f"Analyzing chunk {i+1}/{len(chunks)} for user '{user_id}'. Chunk size: {len(chunk)}")
                            # 為每個分塊添加上下文提示，以確保分析的連貫性
                            chunk_prompt = f"這是大型分析任務的一部分 (區塊 {i+1}/{len(chunks)})。請專注於分析以下內容，並保持與之前區塊的連貫性：\n\n{chunk}"
                            part_result = vn.submit_prompt([{'role': 'user', 'content': chunk_prompt}])
                            analysis_parts.append(part_result)
                        
                        analysis_result = "\n\n---\n\n".join(analysis_parts)
                        vn.log("所有區塊分析完成，已合併結果。", "資訊")
                    else:
                        # 如果提示詞長度在限制內，則直接發送
                        analysis_result = vn.submit_prompt([{'role': 'user', 'content': dynamic_prompt_content}])

                    vn.log("Ollama 分析完成。", "資訊")
                    app.logger.info(f"Ollama analysis result for user '{user_id}'. Result length: {len(analysis_result) if analysis_result else 0}")

                except Exception as e:
                    error_message = f"Ollama 分析失敗: {e}"
                    app.logger.error(error_message, exc_info=True)
                    vn.log(error_message, "錯誤")
                    analysis_result = error_message

                # 清理所有日誌文件
                _delete_all_ask_logs(user_id)

            except Exception as e:
                app.logger.error(f"Error generating, sending to Ollama, or saving dynamic prompt: {e}", exc_info=True)
                vn.log(f"生成、發送給 Ollama 或保存動態提示詞時出錯: {e}", "錯誤")
            # --- 動態生成提示詞並發送給 Ollama 進行分析結束 ---
        
            # 從 vn 實例的 log_queue 中提取所有日誌
            logs = []
            while not vn.log_queue.empty():
                logs.append(vn.log_queue.get())
        
            # 從日誌中提取所需的詳細資訊
            similar_qa_details = [log['details'] for log in logs if log['step'] == '相似問題檢索完成']
            ddl_details = [log['details'] for log in logs if log['step'] == 'DDL 檢索完成']
            doc_details = [log['details'] for log in logs if log['step'] == '文件檢索完成']
        
            # 將結果放入主應用程式的隊列
            app.logger.info(f"Final similar_qa_details: {similar_qa_details}")
            app.logger.info(f"Final ddl_details: {ddl_details}")
            app.logger.info(f"Final doc_details: {doc_details}")
        
            vn_instance.log_queue.put({
                'type': 'result',
                'sql': sql,
                'df_json': df.to_json(orient='records'),
                'similar_qa_details': similar_qa_details,
                'ddl_details': ddl_details,
                'doc_details': doc_details,
                'analysis_result': analysis_result # Add the analysis result here
            })
        except Exception as e:
            app.logger.exception("Error in Vanna thread")
            vn_instance.log_queue.put({'type': 'error', 'message': str(e), 'traceback': traceback.format_exc()})
        finally:
            # 確保無論成功或失敗，都會發送一個結束信號
            vn_instance.log_queue.put(None)

    def stream_logs():
        app.logger.info("開始串流日誌...")
        # 在這裡啟動 Vanna 執行緒，確保其在日誌串流開始後運行
        vanna_thread = threading.Thread(target=run_vanna_in_thread, args=(vn_instance, question, dataset_id, user_id))
        vanna_thread.start()

        while True:
            item = vn_instance.log_queue.get()
            if item is None:
                app.logger.info("串流結束。")
                break
            # 將 Vanna 的日誌或結果發送到前端
            if item['type'] == 'log':
                yield f"data: {json.dumps({'type': 'log', 'step': item['step'], 'message': item['message'], 'level': item['level']})}\n\n"
            elif item['type'] == 'result':
                # 當 Vanna 執行完成並將結果放入隊列時，發送結果
                yield f"data: {json.dumps({'type': 'result', 'sql': item['sql'], 'df_json': item['df_json'], 'similar_qa_details': item['similar_qa_details'], 'ddl_details': item['ddl_details'], 'doc_details': item['doc_details'], 'analysis_result': item.get('analysis_result')})}\n\n"
            elif item['type'] == 'error':
                yield f"data: {json.dumps({'type': 'error', 'message': item['message'], 'traceback': item['traceback']})}\n\n"
            
        vanna_thread.join() # 等待 Vanna 執行緒完成

    return Response(stream_with_context(stream_logs()), mimetype='text/event-stream')

@app.route('/api/generate_qa_from_sql', methods=['POST'])
@api_login_required
def generate_qa_from_sql():
    user_id = session['username']
    if 'sql_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No sql_file part in the request'}), 400

    file = request.files['sql_file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No selected file'}), 400

    if not file or not file.filename.lower().endswith('.sql'):
        return jsonify({'status': 'error', 'message': 'Invalid file type. Please upload a .sql file.'}), 400

    sql_content = file.read().decode('utf-8')

    def stream_qa_generation(sql_content):
        user_id = session['username']
        dataset_id = session.get('active_dataset_id')
        if not dataset_id:
            yield f"data: {json.dumps({'status': 'error', 'message': 'No active dataset selected.'})}\n\n"
            return

        try:
            vn = get_vanna_instance(user_id)
            vn = configure_vanna_for_request(vn, user_id)
            queries = [q.strip() for q in sql_content.split(';') if q.strip()]
            total_queries = len(queries)
            yield f"data: {json.dumps({'status': 'starting', 'total': total_queries, 'message': '開始生成問答配對...'})}\n\n"
            qa_system_prompt = load_prompt_template('qa_generation_system_prompt.txt')
            
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                for i, sql_query in enumerate(queries):
                    try:
                        question = vn.submit_prompt([
                            {'role': 'system', 'content': qa_system_prompt},
                            {'role': 'user', 'content': sql_query}
                        ])
                        
                        cursor.execute(
                            "INSERT INTO training_qa (question, sql_query, table_name, dataset_id) VALUES (?, ?, ?, ?)",
                            (question, sql_query, 'global', dataset_id)
                        )
                        conn.commit()
                        
                        percentage = int(((i + 1) / total_queries) * 100)
                        yield f"data: {json.dumps({'status': 'progress', 'percentage': percentage, 'message': f'已生成 {i + 1}/{total_queries} 個問答配對', 'qa_pair': {'question': question, 'sql': sql_query}})}\n\n"
                    except Exception as e:
                        app.logger.error(f"Error generating QA for query '{sql_query}': {e}", exc_info=True)
                        yield f"data: {json.dumps({'status': 'warning', 'message': f'生成問題時發生錯誤: {str(e)} (SQL: {sql_query[:50]}...)'})}\n\n"
                
            yield f"data: {json.dumps({'status': 'completed', 'percentage': 100, 'message': '問答配對已全部生成並儲存！'})}\n\n"
        except Exception as e:
            app.logger.error(f"An error occurred in stream_qa_generation: {e}", exc_info=True)
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return Response(stream_with_context(stream_qa_generation(sql_content)), mimetype='text/event-stream')

@app.route('/api/generate_documentation', methods=['POST'])
@api_login_required
def generate_documentation():
    user_id = session['username']
    data = request.get_json()
    ddl = data.get('ddl')
    if not ddl:
        return jsonify({'status': 'error', 'message': 'DDL is required.'}), 400

    try:
        vn = get_vanna_instance(user_id)
        vn = configure_vanna_for_request(vn, user_id)
        documentation_prompt_content = load_prompt_template('documentation_prompt.txt')
        prompt = documentation_prompt_content.format(ddl=ddl)
        documentation_text = vn.submit_prompt([{'role': 'user', 'content': prompt}])

        if documentation_text:
            dataset_id = session.get('active_dataset_id')
            if dataset_id:
                with get_user_db_connection(user_id) as conn:
                    cursor = conn.cursor()
                    analysis_table_name = '__dataset_analysis__'
                    cursor.execute(
                        "REPLACE INTO training_documentation (dataset_id, table_name, documentation_text) VALUES (?, ?, ?)",
                        (dataset_id, analysis_table_name, documentation_text)
                    )
                    conn.commit()
        return jsonify({
            'status': 'success',
            'documentation': documentation_text or "無法生成文件。"
        })
    except Exception as e:
        app.logger.error(f"Error generating documentation for user '{user_id}': {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/analyze_schema', methods=['POST'])
@api_login_required
def analyze_schema():
    user_id = session['username']
    dataset_id = session.get('active_dataset_id')

    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400

    try:
        vn = get_vanna_instance(user_id)
        vn = configure_vanna_for_request(vn, user_id, dataset_id)

        # 1. 獲取 DDL
        inspector = inspect(vn.engine)
        table_names = inspector.get_table_names()
        ddl_statements = []
        with vn.engine.connect() as connection:
            for name in table_names:
                ddl = connection.execute(text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{name}';")).scalar()
                if ddl: ddl_statements.append(ddl + ";")
        full_ddl = "\n".join(ddl_statements)

        # 2. 獲取知識背景文件
        with get_user_db_connection(user_id) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT documentation_text FROM training_documentation WHERE dataset_id = ? AND table_name != '__dataset_analysis__'", (dataset_id,))
            documentation_rows = cursor.fetchall()
            knowledge_docs = "\n".join([row['documentation_text'] for row in documentation_rows])

            # 3. 獲取 SQL 問答配對
            cursor.execute("SELECT question, sql_query FROM training_qa WHERE dataset_id = ?", (dataset_id,))
            qa_pairs_rows = cursor.fetchall()
            qa_pairs_str = "\n".join([f"問: {row['question']}\n答: {row['sql_query']}" for row in qa_pairs_rows])

        # 4. 組裝提示
        documentation_prompt_content = load_prompt_template('documentation_prompt.txt')
        
        # 根據 prompt 模板的預期格式組裝
        prompt_content = f"""
DDL 語句:
{full_ddl}

業務術語:
{knowledge_docs if knowledge_docs else "無"}

SQL 查詢集合:
{qa_pairs_str if qa_pairs_str else "無"}

請務必以繁體中文生成所有分析結果和建議。
"""
        prompt = documentation_prompt_content + prompt_content

        # 5. 呼叫 LLM
        analysis_documentation = vn.submit_prompt([{'role': 'user', 'content': prompt}])

        # 6. 儲存分析結果
        if analysis_documentation:
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                analysis_table_name = '__dataset_analysis__'
                cursor.execute(
                    "REPLACE INTO training_documentation (dataset_id, table_name, documentation_text) VALUES (?, ?, ?)",
                    (dataset_id, analysis_table_name, analysis_documentation)
                )
                conn.commit()

        # 7. 返回結果
        app.logger.info(f"Schema analysis for user '{user_id}' completed. Analysis length: {len(analysis_documentation) if analysis_documentation else 0}")
        return jsonify({
            'status': 'success',
            'analysis': analysis_documentation or "無法生成資料庫分析文件。"
        })
    except Exception as e:
        app.logger.error(f"Schema analysis failed for user '{user_id}': {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/generate_documentation_from_analysis', methods=['POST'])
@api_login_required
def generate_documentation_from_analysis():
    user_id = session['username']
    dataset_id = session.get('active_dataset_id')

    if not dataset_id:
        app.logger.warning(f"User '{user_id}' attempted to generate documentation from analysis without an active dataset.")
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400

    try:
        with get_user_db_connection(user_id) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT documentation_text FROM training_documentation WHERE dataset_id = ? AND table_name = '__dataset_analysis__'", (dataset_id,))
            analysis_row = cursor.fetchone()
            analysis_documentation = analysis_row['documentation_text'] if analysis_row else ""

        if not analysis_documentation:
            app.logger.info(f"No analysis documentation found for dataset '{dataset_id}' for user '{user_id}'.")
            return jsonify({'status': 'error', 'message': 'No analysis documentation found for the active dataset.'}), 400

        app.logger.info(f"Successfully retrieved analysis documentation for dataset '{dataset_id}' for user '{user_id}'. Length: {len(analysis_documentation)}")
        return jsonify({
            'status': 'success',
            'documentation': analysis_documentation
        })
    except Exception as e:
        app.logger.error(f"Error retrieving analysis documentation for user '{user_id}': {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/delete_all_qa', methods=['POST'])
@api_login_required
def delete_all_qa():
    user_id = session['username']
    dataset_id = session.get('active_dataset_id')

    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'No active dataset selected.'}), 400

    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM training_qa WHERE dataset_id = ?", (dataset_id,))
            conn.commit()
        return jsonify({'status': 'success', 'message': '所有問答配對已刪除。'})
    except sqlite3.Error as e:
        app.logger.error(f"Database error for user '{user_id}' in delete_all_qa: {e}")
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500


# --- Prompt Management API Routes ---
# 支持两种路由路径，为了兼容前端代码
@app.route('/api/prompts', methods=['GET'])
@app.route('/api/get_prompts', methods=['GET'])
@api_login_required
def get_prompts():
    user_id = session['username']
    try:
        with get_user_db_connection(user_id) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, prompt_name, prompt_content, prompt_type, is_global, created_at FROM training_prompts ORDER BY created_at DESC")
            prompts = [dict(row) for row in cursor.fetchall()]
            return jsonify({'status': 'success', 'prompts': prompts})
    except sqlite3.Error as e:
        app.logger.error(f"Database error for user '{user_id}' in get_prompts: {e}")
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500

@app.route('/api/save_prompt', methods=['POST'])
@api_login_required
def save_prompt():
    user_id = session['username']
    data = request.get_json()
    
    prompt_name = data.get('prompt_name')
    prompt_content = data.get('prompt_content')
    prompt_type = data.get('prompt_type')
    is_global = 1 if data.get('is_global', False) else 0
    prompt_id = data.get('id')
    
    if not prompt_name or not prompt_content:
        return jsonify({'status': 'error', 'message': '提示詞名稱和內容是必需的。'}), 400
    
    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            if prompt_id:
                # 更新现有提示词
                cursor.execute(
                    "UPDATE training_prompts SET prompt_name = ?, prompt_content = ?, prompt_type = ?, is_global = ? WHERE id = ?",
                    (prompt_name, prompt_content, prompt_type, is_global, prompt_id)
                )
                message = '提示詞已更新。'
            else:
                # 插入新提示词
                cursor.execute(
                    "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, is_global) VALUES (?, ?, ?, ?)",
                    (prompt_name, prompt_content, prompt_type, is_global)
                )
                message = '提示詞已添加。'
            
            conn.commit()
            return jsonify({'status': 'success', 'message': message})
    except sqlite3.IntegrityError:
        app.logger.warning(f"Integrity error for user '{user_id}' in save_prompt: Duplicate prompt name")
        return jsonify({'status': 'error', 'message': '提示詞名稱已存在，請使用不同的名稱。'}), 400
    except sqlite3.Error as e:
        app.logger.error(f"Database error for user '{user_id}' in save_prompt: {e}")
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500

@app.route('/api/delete_prompt/<int:prompt_id>', methods=['DELETE'])
@api_login_required
def delete_prompt(prompt_id):
    user_id = session['username']
    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM training_prompts WHERE id = ?", (prompt_id,))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({'status': 'error', 'message': '提示詞不存在。'}), 404
            return jsonify({'status': 'success', 'message': '提示詞已刪除。'})
    except sqlite3.Error as e:
        app.logger.error(f"Database error for user '{user_id}' in delete_prompt: {e}")
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500

@app.route('/api/reset_prompt_to_default/<string:prompt_name>', methods=['POST'])
@api_login_required
def reset_prompt_to_default(prompt_name):
    user_id = session['username']
    try:
        # 尝试从全局提示词文件加载默认内容
        prompt_content = load_prompt_template(f"{prompt_name}.txt")
        
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            # 检查是否已存在该名称的提示词
            cursor.execute("SELECT id FROM training_prompts WHERE prompt_name = ?", (prompt_name,))
            result = cursor.fetchone()
            
            if result:
                # 更新现有提示词为默认内容
                cursor.execute(
                    "UPDATE training_prompts SET prompt_content = ?, is_global = 1 WHERE id = ?",
                    (prompt_content, result[0])
                )
            else:
                # 插入新的默认提示词
                prompt_type_map = {
                    'ask_analysis_prompt': '用於分析用戶問題和生成SQL的提示詞',
                    'qa_generation_system_prompt': '用於從SQL生成問答配對的提示詞',
                    'documentation_prompt': '用於生成數據庫文檔的提示詞'
                }
                prompt_type = prompt_type_map.get(prompt_name, '默認提示詞')
                cursor.execute(
                    "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, is_global) VALUES (?, ?, ?, ?)",
                    (prompt_name, prompt_content, prompt_type, 1)
                )
            
            conn.commit()
            return jsonify({'status': 'success', 'message': '提示詞已重置為默認值。'})
    except FileNotFoundError:
        app.logger.warning(f"Default prompt file not found for '{prompt_name}'")
        return jsonify({'status': 'error', 'message': '找不到默認提示詞文件。'}), 404
    except sqlite3.Error as e:
        app.logger.error(f"Database error for user '{user_id}' in reset_prompt_to_default: {e}")
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500


if __name__ == '__main__':

    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.getenv('FLASK_RUN_PORT', '5001'))
    app.run(host='0.0.0.0', debug=debug_mode, port=port)