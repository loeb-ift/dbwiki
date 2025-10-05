import logging
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, session, redirect, url_for
from werkzeug.utils import secure_filename
import os
import sys
from functools import wraps
# 將 'src' 目錄添加到 Python 路徑中，以確保從本地源碼導入
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))
from dotenv import load_dotenv
import re
import json
import sqlite3
import uuid

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DatabaseError
from vanna.ollama import Ollama
from vanna.chromadb import ChromaDB_VectorStore
from vanna.types import TrainingPlan
import pandas as pd

# 加載環境變量
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', str(uuid.uuid4()))

# --- Login Decorator ---
def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'status': 'error', 'message': 'User not authenticated.'}), 401
        return f(*args, **kwargs)
    return decorated_function

def init_training_db(user_id: str):
    """Initializes the training database for a specific user and creates tables if they don't exist."""
    db_dir = os.path.join(os.getcwd(), 'user_data')
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, f'training_data_{user_id}.sqlite')
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_ddl (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ddl_statement TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_documentation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                documentation_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_qa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                sql_query TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_name TEXT NOT NULL,
                db_path TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS correction_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incorrect_name TEXT NOT NULL UNIQUE,
                correct_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
 
        conn.commit()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='training_qa';")
        if cursor.fetchone() is None:
            conn.close()
            app.logger.error(f"'training_qa' table was not created in database at '{db_path}'.")
            raise Exception(f"ERROR: 'training_qa' table was not created in database at '{db_path}'.")

        conn.close()
        app.logger.info(f"Training database for user '{user_id}' at '{db_path}' initialized successfully.")
    except sqlite3.Error as e:
        app.logger.error(f"Could not initialize training database for user '{user_id}' at '{db_path}': {e}")
        raise
    except Exception as e:
        app.logger.error(f"An unexpected error during training database initialization for user '{user_id}' at '{db_path}': {e}")
        raise

users = {
    "user1": "pass1",
    "user2": "pass2"
}

class MyVanna(Ollama, ChromaDB_VectorStore):
    def __init__(self, user_id: str, config=None):
        model = os.getenv('OLLAMA_MODEL')
        if model is None:
            raise ValueError("OLLAMA_MODEL environment variable not set. Please set it in your .env file.")

        ollama_host = os.getenv('OLLAMA_HOST', 'http://host.docker.internal:11434')
        app.logger.info(f"Connecting to Ollama at: {ollama_host}")

        ollama_config = {
            'model': model,
            'ollama_host': ollama_host,
        }
        Ollama.__init__(self, config=ollama_config)
        
        chroma_collection_name = f"vanna_training_data_{user_id}"
        ChromaDB_VectorStore.__init__(self, config={'collection_name': chroma_collection_name})

    def _get_initial_prompt(self):
        return (
            f"您是一位精通 {self.dialect} 的資深資料庫專家(DBA)。\n"
            "您的任務是根據使用者的問題，生成一段唯一的、可執行的 SQL 查詢。\n"
            "請遵循以下的思考指南來回應：\n"
            "===回應指南===\n"
            "1. 如果提供的上下文足以回答問題，請直接生成 SQL 查詢，不要包含任何額外的解釋或 Markdown 標記。\n"
            "2. 如果上下文幾乎足夠，但需要知道某個欄位的具體值（例如，需要一個城市名稱），請生成一個 `intermediate_sql` 查詢來獲取這些值。您的回覆中只能包含 `-- intermediate_sql` 和查詢本身。\n"
            "3. 如果上下文完全不足以回答問題，請用繁體中文解釋為什麼無法生成 SQL，並說明需要哪些額外資訊。\n"
        )

    def log(self, message: str, title: str = "Info"):
        app.logger.info(f"Vanna Internal Log - {title}: {message}")

def _noop_pull_model(self, client, model_name):
    app.logger.info(f"Patch activated: Skipping Ollama model pull for '{model_name}'")
    pass

Ollama._Ollama__pull_model_if_ne = _noop_pull_model

app.logger.debug(f"OLLAMA_MODEL before MyVanna init: {os.getenv('OLLAMA_MODEL')}")

user_vanna_instances = {}

def get_vanna_instance(user_id: str) -> MyVanna:
    if user_id not in user_vanna_instances:
        user_vanna_instances[user_id] = MyVanna(user_id=user_id)
        
        try:
            db_dir = os.path.join(os.getcwd(), 'user_data')
            db_path = os.path.join(db_dir, f'training_data_{user_id}.sqlite')
            
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT id, db_path, dataset_name FROM datasets ORDER BY created_at DESC LIMIT 1")
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    dataset_id, db_path, dataset_name = row
                    app.logger.info(f"Auto-connecting to user's most recent dataset: '{dataset_name}'")
                    
                    engine = create_engine(f"sqlite:///{db_path}")
                    user_vanna_instances[user_id].engine = engine
                    
                    def run_sql_sqlite(sql: str) -> pd.DataFrame:
                        with engine.connect() as connection:
                            result = connection.execute(text(sql))
                            rows = result.fetchall()
                            columns = result.keys()
                            return pd.DataFrame(rows, columns=columns)
                    
                    user_vanna_instances[user_id].run_sql = run_sql_sqlite
                    user_vanna_instances[user_id].run_sql_is_set = True
                    
                    if 'active_dataset_id' not in session:
                        session['active_dataset_id'] = dataset_id
                        session['active_db_path'] = db_path
        except Exception as e:
            app.logger.warning(f"Failed to auto-connect to user's recent dataset: {e}")
    
    vn = user_vanna_instances[user_id]

    session_active_id = session.get('active_dataset_id')
    instance_active_id = getattr(vn, 'active_dataset_id', None)

    if session_active_id and session_active_id != instance_active_id:
        app.logger.info(f"Session's active dataset ({session_active_id}) differs from instance's ({instance_active_id}). Re-connecting.")
        try:
            training_db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{user_id}.sqlite')
            conn = sqlite3.connect(training_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (session_active_id,))
            row = cursor.fetchone()
            conn.close()

            if row:
                db_path = row[0]
                engine = create_engine(f"sqlite:///{db_path}")
                vn.engine = engine
                
                def run_sql_sqlite(sql: str) -> pd.DataFrame:
                    with engine.connect() as connection:
                        result = connection.execute(text(sql))
                        rows = result.fetchall()
                        columns = result.keys()
                        return pd.DataFrame(rows, columns=columns)
                vn.run_sql = run_sql_sqlite
                vn.run_sql_is_set = True
                vn.active_dataset_id = session_active_id
                vn.active_db_path = db_path
                app.logger.info(f"Vanna instance for user '{user_id}' re-connected to dataset ID {session_active_id}.")
        except Exception as e:
            app.logger.error(f"Failed to re-sync vanna instance with active dataset: {e}")

    return vn

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['username'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username] == password:
            session['username'] = username
            init_training_db(username)
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/api/training_status', methods=['GET'])
@api_login_required
def get_training_status():
    user_id = session['username']
    db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{user_id}.sqlite')

    if not os.path.exists(db_path):
        return jsonify({'has_trained_data': False})

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT EXISTS(SELECT 1 FROM training_ddl)")
        has_ddl = cursor.fetchone()[0]
        
        cursor.execute("SELECT EXISTS(SELECT 1 FROM training_documentation)")
        has_doc = cursor.fetchone()[0]
        
        cursor.execute("SELECT EXISTS(SELECT 1 FROM training_qa)")
        has_qa = cursor.fetchone()[0]
        
        conn.close()
        
        has_trained_data = bool(has_ddl or has_doc or has_qa)
        
        return jsonify({'has_trained_data': has_trained_data})
    except Exception as e:
        app.logger.error(f"Error checking training status for user '{user_id}': {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/train', methods=['POST'])
@api_login_required
def train_model():
    user_id = session['username']
    vn = get_vanna_instance(user_id)

    def generate_progress():
        try:
            yield f"data: {json.dumps({'status': 'starting', 'message': '準備重新訓練...', 'percentage': 0})}\\n\\n"
            ddl = request.form.get('ddl')
            documentation = request.form.get('doc', '')
            qa_pairs_json = request.form.get('qa_pairs')

            if 'doc_file' in request.files:
                doc_file = request.files['doc_file']
                if doc_file.filename != '':
                    doc_content = doc_file.read().decode('utf-8')
                    documentation += f"\\n\\n{doc_content}"

            qa_pairs = []
            if qa_pairs_json:
                try:
                    qa_pairs = json.loads(qa_pairs_json)
                    if not isinstance(qa_pairs, list): qa_pairs = []
                except json.JSONDecodeError:
                    yield f"data: {json.dumps({'status': 'error', 'message': 'Invalid JSON format for qa_pairs.'})}\\n\\n"
                    return

            yield f"data: {json.dumps({'status': 'progress', 'message': '正在清除舊的訓練資料...', 'percentage': 10})}\\n\\n"
            
            vn.remove_training_data(id=None)
            
            db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{user_id}.sqlite')
            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM training_ddl")
                    cursor.execute("DELETE FROM training_documentation")
                    cursor.execute("DELETE FROM training_qa")
                    conn.commit()
                    conn.close()
                except sqlite3.Error as e:
                    app.logger.error(f"Could not clear training tables for user '{user_id}': {e}")
                    raise

            yield f"data: {json.dumps({'status': 'progress', 'message': '舊資料清除完畢，正在載入新資料...', 'percentage': 25})}\\n\\n"

            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    if ddl:
                        cursor.execute("INSERT INTO training_ddl (ddl_statement) VALUES (?)", (ddl,))
                    if documentation:
                        cursor.execute("INSERT INTO training_documentation (documentation_text) VALUES (?)", (documentation,))
                    if qa_pairs:
                        for pair in qa_pairs:
                            if pair.get('question') and pair.get('sql'):
                                cursor.execute("INSERT INTO training_qa (question, sql_query) VALUES (?, ?)", (pair['question'], pair['sql']))
                    conn.commit()
                    conn.close()
                except sqlite3.Error as e:
                    app.logger.warning(f"Could not save new training data for user '{user_id}': {e}")

            app.logger.info(f"--- ATOMIC RE-TRAINING INITIATED for user '{user_id}' ---")
            if ddl: app.logger.info(f"DDL submitted: {ddl[:200]}...")
            if documentation: app.logger.info(f"Documentation submitted: {documentation[:200]}...")
            if qa_pairs: app.logger.info(f"QA Pairs submitted: {len(qa_pairs)} pairs.")
            app.logger.info("-----------------------------------------")

            total_steps = bool(ddl) + bool(documentation) + bool(qa_pairs)
            if not total_steps:
                message = '未提供新的訓練資料。'
                yield f"data: {json.dumps({'status': 'completed', 'message': message, 'percentage': 100})}\\n\\n"
                return

            if ddl:
                vn.train(ddl=ddl)
                yield f"data: {json.dumps({'status': 'progress', 'percentage': 50, 'message': 'DDL 訓練完成'})}\\n\\n"
            if documentation:
                vn.train(documentation=documentation)
                yield f"data: {json.dumps({'status': 'progress', 'percentage': 75, 'message': '文件訓練完成'})}\\n\\n"
            if qa_pairs:
                vn.train(qa_list=qa_pairs)
                yield f"data: {json.dumps({'status': 'progress', 'percentage': 90, 'message': f'問答配對 ({len(qa_pairs)} 組) 訓練完成'})}\\n\\n"

            message = f"模型重新訓練成功！"
            yield f"data: {json.dumps({'status': 'completed', 'message': message, 'percentage': 100})}\\n\\n"

        except Exception as e:
            app.logger.error(f"An error occurred during atomic re-training: {e}", exc_info=True)
            error_message = json.dumps({'status': 'error', 'message': str(e)})
            yield f"data: {error_message}\\n\\n"

    return Response(stream_with_context(generate_progress()), mimetype='text/event-stream')


@app.route('/api/ask', methods=['POST'])
@api_login_required
def ask_question():
    user_id = session['username']
    vn = get_vanna_instance(user_id)

    data = request.json
    question = data.get('question')
    edited_sql = data.get('edited_sql')

    if not question:
        return jsonify({'status': 'error', 'message': 'Question is required.'}), 400

    def generate_response_stream():
        import io
        from logging import StreamHandler

        log_capture_string = io.StringIO()
        ch = StreamHandler(log_capture_string)
        ch.setLevel(logging.INFO)
        
        app.logger.addHandler(ch)
        app.logger.setLevel(logging.INFO)

        final_sql = None
        try:
            def yield_logs():
                log_contents = log_capture_string.getvalue()
                if log_contents:
                    log_capture_string.truncate(0)
                    log_capture_string.seek(0)
                    yield f"data: {json.dumps({'type': 'log_message', 'content': log_contents})}\\n\\n"

            if edited_sql:
                app.logger.info(f"Using user-edited SQL: {edited_sql}")
                final_sql = edited_sql
                yield f"data: {json.dumps({'type': 'thinking_step', 'content': '[使用者提供] 正在使用您編輯後的 SQL...\\n'})}\\n\\n"
                for log_line in yield_logs(): yield log_line
            else:
                app.logger.info(f"Received question: {question}")
                app.logger.info("Generating SQL with Vanna in streaming mode...")

                try:
                    question_sql_list = vn.get_similar_question_sql(question)
                    ddl_list = vn.get_related_ddl(question)
                    doc_list = vn.get_related_documentation(question)
                    
                    context_log = "--- 提供給模型的上下文 ---\n\n"
                    if ddl_list:
                        context_log += "**1. 相關的資料表結構 (DDL):**\n" + "\n".join(ddl_list) + "\n\n"
                    if doc_list:
                        context_log += "**2. 相關的業務知識文件:**\n" + "\n".join(doc_list) + "\n\n"
                    if question_sql_list:
                        context_log += "**3. 相關的問答範例:**\n"
                        for qa in question_sql_list:
                            context_log += f"- 問: {qa['question']}\n  答: {qa['sql']}\n"
                    context_log += "--- 上下文結束 ---\n\n--- 模型思考過程 ---\n"
                    
                    yield f"data: {json.dumps({'type': 'thinking_step', 'content': context_log})}\\n\\n"

                    prompt_message_log = vn.get_sql_prompt(
                        question=question, question_sql_list=question_sql_list,
                        ddl_list=ddl_list, doc_list=doc_list,
                    )
                    formatted_prompt = "\\n--- PROMPT SENT TO LLM ---\\n"
                    for msg in prompt_message_log:
                        formatted_prompt += f"ROLE: {msg.get('role')}\\nCONTENT: {msg.get('content')}\\n---\\n"
                    formatted_prompt += "--- END OF PROMPT ---"
                    app.logger.info(formatted_prompt)

                except Exception as log_e:
                    app.logger.error(f"Error assembling prompt for logging: {log_e}")

                sql_generator = vn.generate_sql(question=question, allow_llm_to_see_data=True)
                
                sql_buffer = []
                
                for chunk in sql_generator:
                    if isinstance(chunk, list):
                        chunk_str = "".join(str(item) for item in chunk)
                        yield f"data: {json.dumps({'type': 'thinking_step', 'content': chunk_str})}\\n\\n"
                        sql_buffer.append(chunk_str)
                    elif hasattr(chunk, 'sql') and chunk.sql:
                        final_sql = chunk.sql
                        break
                    elif isinstance(chunk, str):
                        yield f"data: {json.dumps({'type': 'thinking_step', 'content': chunk})}\\n\\n"
                        sql_buffer.append(chunk)
                    else:
                        chunk_str = str(chunk)
                        yield f"data: {json.dumps({'type': 'thinking_step', 'content': chunk_str})}\\n\\n"
                        sql_buffer.append(chunk_str)
                
                if final_sql is None:
                    full_response_str = "".join(sql_buffer).strip()
                    sql_block_match = re.search(r"```sql\n(.*?)\n```", full_response_str, re.DOTALL)
                    if sql_block_match:
                        final_sql = sql_block_match.group(1).strip()
                    else:
                        sql_match = re.search(r"(SELECT|WITH|INSERT|UPDATE|DELETE).*", full_response_str, re.DOTALL | re.IGNORECASE)
                        if sql_match:
                            final_sql = sql_match.group(0).strip()

            if final_sql:
                cleaned_sql = final_sql
                app.logger.info(f"Final Extracted SQL: {cleaned_sql}")
                
                for log_line in yield_logs(): yield log_line

                yield f"data: {json.dumps({'type': 'sql_result', 'sql': cleaned_sql})}\\n\\n"
                for log_line in yield_logs(): yield log_line
            else:
                full_response_str = "".join(sql_buffer).strip()
                app.logger.info(f"No SQL extracted. Passing full response as a thinking step. Full response: {full_response_str}")
                yield f"data: {json.dumps({'type': 'thinking_step', 'content': full_response_str})}\\n\\n"
                return

        except Exception as e:
            app.logger.error(f"An error occurred during SQL generation: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'SQL Generation Error: {e}'})}\\n\\n"
            return
        finally:
            for log_line in yield_logs():
                yield log_line
            app.logger.removeHandler(ch)

    return Response(stream_with_context(generate_response_stream()), mimetype='text/event-stream')

@app.route('/api/execute_sql', methods=['POST'])
@api_login_required
def execute_sql():
    user_id = session['username']
    vn = get_vanna_instance(user_id)
    
    data = request.json
    sql = data.get('sql')

    if not sql:
        return jsonify({'status': 'error', 'message': 'SQL is required.'}), 400

    try:
        if not hasattr(vn, 'run_sql_is_set') or not vn.run_sql_is_set:
            return jsonify({'status': 'error', 'message': 'Database connection not established.'}), 400

        app.logger.info(f"Executing user-provided SQL: {sql}")
        df = vn.run_sql(sql=sql)
        result_string = df.to_string()
        return jsonify({'status': 'success', 'data': result_string})

    except Exception as e:
        app.logger.error(f"Error executing SQL: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/datasets', methods=['GET'])
@api_login_required
def get_datasets():
    user_id = session['username']
    db_dir = os.path.join(os.getcwd(), 'user_data')
    db_path = os.path.join(db_dir, f'training_data_{user_id}.sqlite')

    if not os.path.exists(db_path):
        return jsonify({'status': 'success', 'datasets': []})

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS datasets (id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_name TEXT NOT NULL, db_path TEXT NOT NULL UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
        cursor.execute("SELECT id, dataset_name, created_at FROM datasets ORDER BY created_at DESC")
        rows = cursor.fetchall()
        datasets = [dict(row) for row in rows]
        conn.close()

        return jsonify({'status': 'success', 'datasets': datasets})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/datasets', methods=['POST'])
@api_login_required
def create_dataset():
    user_id = session['username']
    dataset_name = request.form.get('dataset_name')
    files = request.files.getlist('files')

    if not dataset_name or not files:
        return jsonify({'status': 'error', 'message': 'Dataset name and files are required.'}), 400

    for file in files:
        if not file.filename.lower().endswith('.csv'):
            return jsonify({'status': 'error', 'message': f"Invalid file type: {file.filename}. Please upload only .csv files."}), 400

    dataset_id = uuid.uuid4().hex[:12]
    db_dir = os.path.join('user_data', 'datasets')
    os.makedirs(db_dir, exist_ok=True)
    db_filename = f"{user_id}_{dataset_id}.sqlite"
    db_path = os.path.join(db_dir, db_filename)

    try:
        engine = create_engine(f'sqlite:///{db_path}')
        app.logger.info(f"--- DATASET CREATION for user '{user_id}' ---")
        app.logger.info(f"Dataset Name: {dataset_name}")
        app.logger.info(f"SQLite DB Path: {db_path}")
        for file in files:
            df = pd.read_csv(file.stream)
            table_name = os.path.splitext(secure_filename(file.filename))[0].replace('-', '_').replace(' ', '_')
            df.to_sql(table_name, engine, index=False, if_exists='replace')
            app.logger.info(f"CSV '{file.filename}' loaded into table '{table_name}'.")
        app.logger.info("-----------------------------------------")

        training_db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{user_id}.sqlite')
        conn = sqlite3.connect(training_db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO datasets (dataset_name, db_path) VALUES (?, ?)", (dataset_name, db_path))
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Dataset created successfully.',
            'dataset': {
                'id': new_id,
                'dataset_name': dataset_name,
                'db_path': db_path
            }
        }), 201

    except Exception as e:
        if os.path.exists(db_path):
            os.remove(db_path)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/datasets/activate', methods=['POST'])
@api_login_required
def activate_dataset():
    user_id = session['username']
    data = request.json
    dataset_id = data.get('dataset_id')

    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'dataset_id is required.'}), 400

    training_db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{user_id}.sqlite')
    try:
        conn = sqlite3.connect(training_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT db_path, dataset_name FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            db_path, dataset_name = row
            vn = get_vanna_instance(user_id)
            
            engine = create_engine(f"sqlite:///{db_path}")
            vn.engine = engine
            
            def run_sql_sqlite(sql: str) -> pd.DataFrame:
                with engine.connect() as connection:
                    result = connection.execute(text(sql))
                    rows = result.fetchall()
                    columns = result.keys()
                    return pd.DataFrame(rows, columns=columns)
            vn.run_sql = run_sql_sqlite
            vn.run_sql_is_set = True

            if hasattr(vn, 'engine'):
                app.logger.debug(f"In activate_dataset, vn.engine was SET. Engine name: {vn.engine.name}")
            else:
                app.logger.debug("In activate_dataset, vn.engine FAILED TO SET.")

            session['active_dataset_id'] = dataset_id
            session['active_db_path'] = db_path
            
            vn.active_dataset_id = dataset_id
            vn.active_db_path = db_path

            app.logger.info(f"--- DATASET ACTIVATED for user '{user_id}' ---")
            app.logger.info(f"Dataset Name: {dataset_name}")
            app.logger.info(f"Dataset ID: {dataset_id}")
            app.logger.info(f"DB Path: {db_path}")
            app.logger.info("-----------------------------------------")

            # Inspect the database to get schema
            inspector = inspect(engine)
            schema_info = {}
            ddl_statements = []
            for table_name in inspector.get_table_names():
                columns = inspector.get_columns(table_name)
                schema_info[table_name] = [f"{col['name']} ({str(col['type'])})" for col in columns]
                
                # Attempt to generate DDL for the table
                try:
                    with engine.connect() as connection:
                        # For SQLite, we can query the sqlite_master table
                        ddl_query = f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}';"
                        result = connection.execute(text(ddl_query))
                        ddl_statement = result.scalar()
                        if ddl_statement:
                            ddl_statements.append(ddl_statement + ";")
                except Exception as e:
                    app.logger.warning(f"Could not generate DDL for table {table_name}: {e}")

            return jsonify({
                'status': 'success',
                'message': f"Dataset '{dataset_name}' is now active.",
                'active_dataset_id': dataset_id,
                'schema': schema_info,
                'ddl': ddl_statements,
            })
        else:
            return jsonify({'status': 'error', 'message': 'Dataset not found or you do not have permission to access it.'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/datasets/<int:dataset_id>', methods=['DELETE'])
@api_login_required
def delete_dataset(dataset_id):
    user_id = session['username']
    training_db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{user_id}.sqlite')
    
    try:
        conn = sqlite3.connect(training_db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT db_path, dataset_name FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Dataset not found.'}), 404
        
        db_path, dataset_name = row
        
        if session.get('active_dataset_id') == dataset_id:
            session.pop('active_dataset_id', None)
            session.pop('active_db_path', None)
            
            vn = get_vanna_instance(user_id)
            vn.active_dataset_id = None
            vn.active_db_path = None
        
        cursor.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
        conn.commit()
        conn.close()
        
        if os.path.exists(db_path):
            os.remove(db_path)
        
        app.logger.info(f"--- DATASET DELETED for user '{user_id}' ---")
        app.logger.info(f"Dataset Name: {dataset_name}")
        app.logger.info(f"Dataset ID: {dataset_id}")
        app.logger.info(f"DB Path: {db_path}")
        app.logger.info("-----------------------------------------")
        
        return jsonify({
            'status': 'success',
            'message': f"Dataset '{dataset_name}' has been deleted successfully.",
            'dataset_id': dataset_id
        })
    except Exception as e:
        app.logger.error(f"Error deleting dataset: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/correction_rules', methods=['GET', 'POST'])
@api_login_required
def handle_correction_rules():
    user_id = session['username']
    db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{user_id}.sqlite')
    
    if not os.path.exists(db_path):
        init_training_db(user_id)

    if request.method == 'GET':
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, incorrect_name, correct_name FROM correction_rules ORDER BY created_at DESC")
            rules = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return jsonify({'status': 'success', 'rules': rules})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    if request.method == 'POST':
        data = request.json
        incorrect_name = data.get('incorrect_name')
        correct_name = data.get('correct_name')

        if not incorrect_name or not correct_name:
            return jsonify({'status': 'error', 'message': 'Both incorrect_name and correct_name are required.'}), 400

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO correction_rules (incorrect_name, correct_name) VALUES (?, ?)", (incorrect_name, correct_name))
            new_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return jsonify({'status': 'success', 'message': 'Rule added successfully.', 'rule': {'id': new_id, 'incorrect_name': incorrect_name, 'correct_name': correct_name}}), 201
        except sqlite3.IntegrityError:
            return jsonify({'status': 'error', 'message': f'Rule for "{incorrect_name}" already exists.'}), 409
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/correction_rules/<int:rule_id>', methods=['DELETE'])
@api_login_required
def delete_correction_rule(rule_id):
    user_id = session['username']
    db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{user_id}.sqlite')

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM correction_rules WHERE id = ?", (rule_id,))
        conn.commit()
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Rule not found.'}), 404
            
        conn.close()
        return jsonify({'status': 'success', 'message': 'Rule deleted successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/generate_qa_from_sql', methods=['POST'])
@api_login_required
def generate_qa_from_sql():
    user_id = session['username']
    vn = get_vanna_instance(user_id)

    if 'sql_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No sql_file part in the request.'}), 400
    
    file = request.files['sql_file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No selected file.'}), 400

    def generate_stream():
        try:
            sql_content = file.read().decode('utf-8')
            sql_queries = [q.strip() for q in sql_content.split(';') if q.strip()]
            total_queries = len(sql_queries)
            
            app.logger.info(f"--- GENERATING QA FROM {total_queries} SQL QUERIES for user '{user_id}' ---")

            for i, sql in enumerate(sql_queries):
                try:
                    question = vn.generate_question(sql)
                    qa_pair = {'question': question, 'sql': sql}
                    
                    yield f"data: {json.dumps({'status': 'progress', 'qa_pair': qa_pair, 'count': i + 1, 'total': total_queries})}\\n\\n"
                except Exception as e:
                    app.logger.error(f"Error generating question for SQL: {sql}. Error: {e}")
                    yield f"data: {json.dumps({'status': 'error_partial', 'sql': sql, 'message': str(e)})}\\n\\n"

            yield f"data: {json.dumps({'status': 'completed', 'message': f'Successfully generated QA pairs for {total_queries} queries.'})}\\n\\n"
            app.logger.info("-----------------------------------------")

        except Exception as e:
            app.logger.error(f"Error in generate_qa_from_sql stream: {e}")
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\\n\\n"

    return Response(stream_with_context(generate_stream()), mimetype='text/event-stream')


@app.route('/api/schema', methods=['GET'])
@api_login_required
def get_schema():
    user_id = session['username']
    active_dataset_id = session.get('active_dataset_id')

    if not active_dataset_id:
        return jsonify({'schema': {}, 'ddl': []})

    training_db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{user_id}.sqlite')
    conn = sqlite3.connect(training_db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (active_dataset_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'status': 'error', 'message': 'Active dataset not found in registry.'}), 404
    
    db_path = row[0]
    engine = create_engine(f"sqlite:///{db_path}")

    inspector = inspect(engine)
    schema_info = {}
    ddl_statements = []
    table_names = inspector.get_table_names()

    for table_name in table_names:
        columns = inspector.get_columns(table_name)
        schema_info[table_name] = [f"{col['name']} ({str(col['type'])})" for col in columns]
        
        try:
            with engine.connect() as connection:
                ddl_query = f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}';"
                result = connection.execute(text(ddl_query))
                ddl_statement = result.scalar()
                if ddl_statement:
                    ddl_statements.append(ddl_statement + ";")
        except Exception as e:
            app.logger.warning(f"Could not generate DDL for table {table_name} in get_schema: {e}")

    return jsonify({
        'schema': schema_info,
        'ddl': ddl_statements
    })
        
@app.route('/api/training_data/<int:training_id>', methods=['GET'])
@api_login_required
def get_training_data_by_id(training_id):
    user_id = session['username']
    db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{user_id}.sqlite')
    
    if not os.path.exists(db_path):
        return jsonify({'status': 'success', 'qa_pairs': [], 'documentation': []})
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, question, sql_query as sql FROM training_qa ORDER BY created_at DESC")
    qa_pairs = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT documentation_text FROM training_documentation ORDER BY created_at DESC")
    documentation = [row['documentation_text'] for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'status': 'success',
        'qa_pairs': qa_pairs,
        'documentation': documentation
    })
        
if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', debug=debug_mode, port=5001)