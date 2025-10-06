import logging
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
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DatabaseError

# Add 'src' to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from vanna.ollama import Ollama
from vanna.chromadb import ChromaDB_VectorStore

# --- App Setup ---
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', str(uuid.uuid4()))

# --- User Management ---
users = {"user1": "pass1", "user2": "pass2"}

# --- Helper Functions ---
def get_user_db_path(user_id: str) -> str:
    db_dir = os.path.join(os.getcwd(), 'user_data')
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, f'training_data_{user_id}.sqlite')

def get_user_db_connection(user_id: str) -> sqlite3.Connection:
    db_path = get_user_db_path(user_id)
    return sqlite3.connect(db_path)

def _save_single_entry_data(user_id: str, table: str, column: str, content: str):
    db_path = get_user_db_path(user_id)
    if not os.path.exists(db_path):
        raise FileNotFoundError("User database not found.")
    
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {table}")
        if content and content.strip():
            cursor.execute(f"INSERT INTO {table} ({column}) VALUES (?)", (content,))
        conn.commit()

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
                "training_documentation": "(id INTEGER PRIMARY KEY AUTOINCREMENT, documentation_text TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
                "training_qa": "(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, sql_query TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
                "datasets": "(id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_name TEXT NOT NULL, db_path TEXT NOT NULL UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
                "correction_rules": "(id INTEGER PRIMARY KEY AUTOINCREMENT, incorrect_name TEXT NOT NULL UNIQUE, correct_name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            }
            for table_name, schema in tables.items():
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} {schema};")
            conn.commit()
        app.logger.info(f"Training database for user '{user_id}' initialized successfully.")
    except sqlite3.Error as e:
        app.logger.error(f"Could not initialize training database for user '{user_id}': {e}")
        raise

# --- Vanna AI Integration ---
class MyVanna(Ollama, ChromaDB_VectorStore):
    def __init__(self, user_id: str, config=None):
        model = os.getenv('OLLAMA_MODEL')
        if not model:
            raise ValueError("OLLAMA_MODEL environment variable not set.")
        ollama_host = os.getenv('OLLAMA_HOST', 'http://host.docker.internal:11434')
        Ollama.__init__(self, config={'model': model, 'ollama_host': ollama_host})
        ChromaDB_VectorStore.__init__(self, config={'collection_name': f"vanna_training_data_{user_id}"})

    def log(self, message: str, title: str = "Info"):
        app.logger.info(f"Vanna Log - {title}: {message}")

def _noop_pull_model(self, client, model_name):
    app.logger.info(f"Patch: Skipping Ollama model pull for '{model_name}'")
Ollama._Ollama__pull_model_if_ne = _noop_pull_model

user_vanna_instances = {}

def get_vanna_instance(user_id: str) -> MyVanna:
    if user_id not in user_vanna_instances:
        user_vanna_instances[user_id] = MyVanna(user_id=user_id)
    return user_vanna_instances[user_id]

# --- Flask Routes ---
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
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
    return redirect(url_for('login'))

@app.route('/api/training_status', methods=['GET'])
@api_login_required
def get_training_status():
    user_id = session['username']
    db_path = get_user_db_path(user_id)
    if not os.path.exists(db_path):
        return jsonify({'has_trained_data': False})
    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT (SELECT COUNT(*) FROM training_ddl) > 0 OR (SELECT COUNT(*) FROM training_documentation) > 0 OR (SELECT COUNT(*) FROM training_qa) > 0")
            has_data = cursor.fetchone()[0]
        return jsonify({'has_trained_data': bool(has_data)})
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
            yield f"data: {json.dumps({'status': 'starting', 'message': '準備開始訓練...', 'percentage': 0}, ensure_ascii=False)}\n\n"
            time.sleep(0.2)

            db_path = get_user_db_path(user_id)
            ddl, documentation, qa_pairs = "", "", []
            if os.path.exists(db_path):
                with get_user_db_connection(user_id) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT ddl_statement FROM training_ddl")
                    ddl = "\n\n".join([row[0] for row in cursor.fetchall()])
                    cursor.execute("SELECT documentation_text FROM training_documentation")
                    documentation = "\n\n".join([row[0] for row in cursor.fetchall()])
                    cursor.execute("SELECT question, sql_query FROM training_qa")
                    qa_pairs = [{'question': row[0], 'sql': row[1]} for row in cursor.fetchall()]
                yield f"data: {json.dumps({'status': 'progress', 'message': '已成功從資料庫讀取訓練資料...', 'percentage': 10}, ensure_ascii=False)}\n\n"
                time.sleep(0.2)
            
            yield f"data: {json.dumps({'status': 'progress', 'message': '1. 正在清除舊的模型向量...', 'percentage': 20}, ensure_ascii=False)}\n\n"
            time.sleep(0.2)
            vn.remove_training_data(id=None)
            yield f"data: {json.dumps({'status': 'progress', 'message': '   - 向量資料已清除。', 'percentage': 30}, ensure_ascii=False)}\n\n"
            time.sleep(0.2)
            
            yield f"data: {json.dumps({'status': 'progress', 'message': '2. 開始逐一重新訓練...', 'percentage': 30}, ensure_ascii=False)}\n\n"
            time.sleep(0.2)
            
            total_steps = bool(ddl) + bool(documentation) + bool(qa_pairs)
            if not total_steps:
                yield f"data: {json.dumps({'status': 'completed', 'message': '資料庫中沒有可用的訓練資料。', 'percentage': 100}, ensure_ascii=False)}\n\n"
                return

            completed_steps = 0
            def report_progress(message):
                nonlocal completed_steps
                completed_steps += 1
                percentage = 30 + int((completed_steps / total_steps) * 60)
                return f"data: {json.dumps({'status': 'progress', 'percentage': percentage, 'message': message}, ensure_ascii=False)}\n\n"

            if ddl:
                vn.train(ddl=ddl)
                yield report_progress('   - DDL 訓練完成')
                time.sleep(0.2)
            
            if documentation:
                vn.train(documentation=documentation)
                yield report_progress('   - 文件訓練完成')
                time.sleep(0.2)

            if qa_pairs:
                for pair in qa_pairs:
                    vn.train(question=pair['question'], sql=pair['sql'])
                yield report_progress(f'   - 問答配對 ({len(qa_pairs)} 組) 訓練完成')
                time.sleep(0.2)

            yield f"data: {json.dumps({'status': 'completed', 'message': '3. 模型重新訓練成功！', 'percentage': 100}, ensure_ascii=False)}\n\n"
        except Exception as e:
            app.logger.error(f"Training error: {e}", exc_info=True)
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
    return Response(stream_with_context(generate_progress()), mimetype='text/event-stream')

@app.route('/api/ask', methods=['POST'])
@api_login_required
def ask_question():
    user_id = session['username']
    vn = get_vanna_instance(user_id)

    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'Request must be JSON.'}), 400
    except Exception:
        return jsonify({'status': 'error', 'message': 'Invalid JSON in request.'}), 400

    question = data.get('question')
    if not question:
        return jsonify({'status': 'error', 'message': 'Question is required.'}), 400
    
    edited_sql = data.get('edited_sql')

    def generate_response_stream():
        final_sql = None
        try:
            if edited_sql:
                final_sql = edited_sql
                yield f"data: {json.dumps({'type': 'thinking_step', 'content': '[使用者提供] 正在使用您編輯後的 SQL...\n'}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'thinking_step', 'content': '--- 開始檢索上下文 ---\n'}, ensure_ascii=False)}\n\n"
                question_sql_list = vn.get_similar_question_sql(question)
                if question_sql_list:
                    qa_log = "**檢索相似問答對 (get_similar_question_sql):**\n" + "".join([f"- 問: {qa['question']}\\n  答: {qa['sql']}\\n" for qa in question_sql_list])
                    yield f"data: {json.dumps({'type': 'thinking_step', 'content': qa_log}, ensure_ascii=False)}\n\n"
                
                ddl_list = vn.get_related_ddl(question)
                if ddl_list:
                    yield f"data: {json.dumps({'type': 'thinking_step', 'content': '**檢索相關 DDL (get_related_ddl):**\n' + '\n'.join(ddl_list) + '\n'}, ensure_ascii=False)}\n\n"

                doc_list = vn.get_related_documentation(question)
                if doc_list:
                    yield f"data: {json.dumps({'type': 'thinking_step', 'content': '**檢索相關文檔 (get_related_documentation):**\n' + '\n'.join(doc_list) + '\n'}, ensure_ascii=False)}\n\n"
                
                yield f"data: {json.dumps({'type': 'thinking_step', 'content': '--- 上下文檢索完畢 ---\\n\\n--- 模型思考過程 ---\\n'}, ensure_ascii=False)}\n\n"
                
                sql_generator = vn.generate_sql(question=question, allow_llm_to_see_data=True)
                
                sql_buffer = []
                for chunk in sql_generator:
                    content = str(chunk.sql) if hasattr(chunk, 'sql') else str(chunk)
                    yield f"data: {json.dumps({'type': 'thinking_step', 'content': content}, ensure_ascii=False)}\n\n"
                    sql_buffer.append(content)
                
                full_response = "".join(sql_buffer).strip()
                match = re.search(r"```sql\\n(.*?)\\n```", full_response, re.DOTALL)
                if match:
                    final_sql = match.group(1).strip()
                else:
                    sql_match = re.search(r"(SELECT|WITH).+", full_response, re.DOTALL | re.IGNORECASE)
                    if sql_match:
                        final_sql = sql_match.group(0).strip()

            if final_sql:
                yield f"data: {json.dumps({'type': 'sql_result', 'sql': final_sql}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'thinking_step', 'content': '未能生成有效的 SQL 查詢。'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            app.logger.error(f"SQL generation error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'SQL Generation Error: {e}'}, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate_response_stream()), mimetype='text/event-stream')

@app.route('/api/execute_sql', methods=['POST'])
@api_login_required
def execute_sql():
    user_id = session['username']
    vn = get_vanna_instance(user_id)
    sql = request.get_json().get('sql')
    if not sql:
        return jsonify({'status': 'error', 'message': 'SQL is required.'}), 400
    try:
        if not hasattr(vn, 'run_sql_is_set') or not vn.run_sql_is_set:
            return jsonify({'status': 'error', 'message': 'Database connection not established.'}), 400
        df = vn.run_sql(sql=sql)
        return jsonify({'status': 'success', 'data': df.to_string()})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/datasets', methods=['GET', 'POST'])
@api_login_required
def handle_datasets():
    user_id = session['username']
    if request.method == 'GET':
        db_path = get_user_db_path(user_id)
        if not os.path.exists(db_path):
            return jsonify({'status': 'success', 'datasets': []})
        with get_user_db_connection(user_id) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, dataset_name, created_at FROM datasets ORDER BY created_at DESC")
            return jsonify({'status': 'success', 'datasets': [dict(row) for row in cursor.fetchall()]})
    
    if request.method == 'POST':
        dataset_name = request.form.get('dataset_name')
        files = request.files.getlist('files')
        if not dataset_name or not files:
            return jsonify({'status': 'error', 'message': 'Dataset name and files are required.'}), 400
        
        dataset_id = uuid.uuid4().hex[:12]
        db_dir = os.path.join('user_data', 'datasets')
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, f"{user_id}_{dataset_id}.sqlite")

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

@app.route('/api/datasets/activate', methods=['POST'])
@api_login_required
def activate_dataset():
    user_id = session['username']
    dataset_id = request.get_json().get('dataset_id')
    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'dataset_id is required.'}), 400
    
    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT db_path, dataset_name FROM datasets WHERE id = ?", (dataset_id,))
            row = cursor.fetchone()
        
        if row:
            db_path, dataset_name = row
            vn = get_vanna_instance(user_id)
            engine = create_engine(f"sqlite:///{db_path}")
            vn.engine = engine
            vn.run_sql = lambda sql: pd.read_sql_query(sql, engine)
            vn.run_sql_is_set = True
            session['active_dataset_id'] = dataset_id
            
            inspector = inspect(engine)
            schema_info = {name: [f"{col['name']} ({str(col['type'])})" for col in inspector.get_columns(name)] for name in inspector.get_table_names()}
            ddl_statements = []
            with engine.connect() as connection:
                for name in inspector.get_table_names():
                    ddl = connection.execute(text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{name}';")).scalar()
                    if ddl: ddl_statements.append(ddl + ";")

            return jsonify({'status': 'success', 'message': f"Dataset '{dataset_name}' activated.", 'active_dataset_id': dataset_id, 'schema': schema_info, 'ddl': ddl_statements})
        return jsonify({'status': 'error', 'message': 'Dataset not found.'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/datasets/<int:dataset_id>', methods=['DELETE'])
@api_login_required
def delete_dataset(dataset_id):
    user_id = session['username']
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path, dataset_name FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'status': 'error', 'message': 'Dataset not found.'}), 404
        db_path, dataset_name = row
        
        if session.get('active_dataset_id') == dataset_id:
            session.pop('active_dataset_id', None)
        
        cursor.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
        conn.commit()
        if os.path.exists(db_path): os.remove(db_path)
    return jsonify({'status': 'success', 'message': f"Dataset '{dataset_name}' deleted."})

@app.route('/api/correction_rules', methods=['GET', 'POST'])
@api_login_required
def handle_correction_rules():
    user_id = session['username']
    with get_user_db_connection(user_id) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if request.method == 'GET':
            cursor.execute("SELECT id, incorrect_name, correct_name FROM correction_rules ORDER BY created_at DESC")
            return jsonify({'status': 'success', 'rules': [dict(row) for row in cursor.fetchall()]})
        if request.method == 'POST':
            data = request.get_json()
            incorrect, correct = data.get('incorrect_name'), data.get('correct_name')
            if not incorrect or not correct:
                return jsonify({'status': 'error', 'message': 'Both names are required.'}), 400
            try:
                cursor.execute("INSERT INTO correction_rules (incorrect_name, correct_name) VALUES (?, ?)", (incorrect, correct))
                new_id = cursor.lastrowid
                conn.commit()
                return jsonify({'status': 'success', 'rule': {'id': new_id, 'incorrect_name': incorrect, 'correct_name': correct}}), 201
            except sqlite3.IntegrityError:
                return jsonify({'status': 'error', 'message': f'Rule for "{incorrect}" already exists.'}), 409

@app.route('/api/correction_rules/<int:rule_id>', methods=['DELETE'])
@api_login_required
def delete_correction_rule(rule_id):
    user_id = session['username']
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM correction_rules WHERE id = ?", (rule_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'Rule not found.'}), 404
    return jsonify({'status': 'success', 'message': 'Rule deleted.'})

@app.route('/api/generate_qa_from_sql', methods=['POST'])
@api_login_required
def generate_qa_from_sql():
    user_id = session['username']
    vn = get_vanna_instance(user_id)
    file = request.files.get('sql_file')
    if not file or file.filename == '':
        return jsonify({'status': 'error', 'message': 'No file selected.'}), 400
    
    sql_content = file.read().decode('utf-8')
    def generate_stream(content):
        sql_queries = [q.strip() for q in content.split(';') if q.strip()]
        total = len(sql_queries)
        yield f"data: {json.dumps({'status': 'starting', 'total': total}, ensure_ascii=False)}\n\n"
        for i, sql in enumerate(sql_queries):
            try:
                question = vn.generate_question(sql)
                yield f"data: {json.dumps({'status': 'progress', 'qa_pair': {'question': question, 'sql': sql}, 'count': i + 1, 'total': total}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error_partial', 'sql': sql, 'message': str(e)}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'status': 'completed', 'message': 'Generation complete.'}, ensure_ascii=False)}\n\n"
    return Response(stream_with_context(generate_stream(sql_content)), mimetype='text/event-stream')

@app.route('/api/schema', methods=['GET'])
@api_login_required
def get_schema():
    user_id = session['username']
    active_dataset_id = session.get('active_dataset_id')
    if not active_dataset_id:
        return jsonify({'schema': {}, 'ddl': []})
    
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (active_dataset_id,))
        row = cursor.fetchone()
    if not row:
        return jsonify({'status': 'error', 'message': 'Active dataset not found.'}), 404
    
    engine = create_engine(f"sqlite:///{row[0]}")
    inspector = inspect(engine)
    schema_info = {name: [f"{col['name']} ({str(col['type'])})" for col in inspector.get_columns(name)] for name in inspector.get_table_names()}
    ddl_statements = []
    with engine.connect() as connection:
        for name in inspector.get_table_names():
            ddl = connection.execute(text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{name}';")).scalar()
            if ddl: ddl_statements.append(ddl + ";")
    return jsonify({'schema': schema_info, 'ddl': ddl_statements})

@app.route('/api/training_data', methods=['GET'])
@api_login_required
def get_training_data():
    user_id = session['username']
    db_path = get_user_db_path(user_id)
    if not os.path.exists(db_path):
        return jsonify({'status': 'success', 'ddl': [], 'qa_pairs': [], 'documentation': []})
    
    with get_user_db_connection(user_id) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT ddl_statement FROM training_ddl ORDER BY created_at DESC")
        ddls = [row['ddl_statement'] for row in cursor.fetchall()]
        cursor.execute("SELECT id, question, sql_query as sql FROM training_qa ORDER BY created_at DESC")
        qa_pairs = [dict(row) for row in cursor.fetchall()]
        cursor.execute("SELECT documentation_text FROM training_documentation ORDER BY created_at DESC")
        documentation = [row['documentation_text'] for row in cursor.fetchall()]
    return jsonify({'status': 'success', 'ddl': ddls, 'qa_pairs': qa_pairs, 'documentation': documentation})

@app.route('/api/add_qa_question', methods=['POST'])
@api_login_required
def add_qa_question():
    user_id = session['username']
    data = request.get_json()
    question, sql_query = data.get('question'), data.get('sql')
    if not question or not sql_query:
        return jsonify({'status': 'error', 'message': 'Question and SQL are required.'}), 400
    
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO training_qa (question, sql_query) VALUES (?, ?)", (question, sql_query))
        new_id = cursor.lastrowid
        conn.commit()
    return jsonify({'status': 'success', 'id': new_id}), 201

@app.route('/api/update_qa_question', methods=['POST'])
@api_login_required
def update_qa_question():
    user_id = session['username']
    data = request.get_json()
    qa_id, new_question = data.get('id'), data.get('question')
    if not qa_id or new_question is None:
        return jsonify({'status': 'error', 'message': 'ID and question are required.'}), 400
    
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE training_qa SET question = ? WHERE id = ?", (new_question, qa_id))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'QA pair not found.'}), 404
    return jsonify({'status': 'success'})

@app.route('/api/save_ddl', methods=['POST'])
@api_login_required
def save_ddl():
    user_id = session['username']
    ddl_content = request.get_json().get('ddl')
    try:
        _save_single_entry_data(user_id, 'training_ddl', 'ddl_statement', ddl_content)
        return jsonify({'status': 'success', 'message': 'DDL saved.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/save_documentation', methods=['POST'])
@api_login_required
def save_documentation():
    user_id = session['username']
    doc_content = request.get_json().get('documentation')
    try:
        _save_single_entry_data(user_id, 'training_documentation', 'documentation_text', doc_content)
        return jsonify({'status': 'success', 'message': 'Documentation saved.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', debug=debug_mode, port=5001)