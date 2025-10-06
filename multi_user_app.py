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
from sqlalchemy.exc import DatabaseError, OperationalError
from queue import Queue
from threading import Thread

# Add 'src' to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from vanna.ollama import Ollama
from vanna.chromadb import ChromaDB_VectorStore
from vanna.types import TrainingPlan

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
                "correction_rules": "(id INTEGER PRIMARY KEY AUTOINCREMENT, incorrect_name TEXT NOT NULL UNIQUE, correct_name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            }
            for table_name, schema in tables.items():
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} {schema};")
            
            def add_column_if_not_exists(table, column, col_type):
                cursor.execute(f"PRAGMA table_info({table})")
                if column not in [info[1] for info in cursor.fetchall()]:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            
            add_column_if_not_exists('training_documentation', 'dataset_id', 'TEXT')
            add_column_if_not_exists('training_qa', 'dataset_id', 'TEXT')
            
            conn.commit()
    except sqlite3.Error as e:
        app.logger.error(f"Could not initialize/update training database for user '{user_id}': {e}")
        raise

# --- Vanna AI Integration ---
class MyVanna(Ollama, ChromaDB_VectorStore):
    def __init__(self, user_id: str, config=None):
        self.log_queue = Queue()
        model = os.getenv('OLLAMA_MODEL')
        if not model: raise ValueError("OLLAMA_MODEL not set.")
        ollama_host = os.getenv('OLLAMA_HOST', 'http://host.docker.internal:11434')
        Ollama.__init__(self, config={'model': model, 'ollama_host': ollama_host})
        ChromaDB_VectorStore.__init__(self, config={'collection_name': f"vanna_training_data_{user_id}"})

    def log(self, message: str, title: str = "Info"):
        self.log_queue.put({'type': 'thinking_step', 'step': title, 'details': message})

def _noop_pull_model(self, client, model_name):
    app.logger.info(f"Patch: Skipping Ollama model pull for '{model_name}'")
Ollama._Ollama__pull_model_if_ne = _noop_pull_model

def get_vanna_instance(user_id: str) -> MyVanna:
    return MyVanna(user_id=user_id)

def configure_vanna_for_request(vn, user_id):
    dataset_id = session.get('active_dataset_id')
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

@app.route('/api/datasets', methods=['GET', 'POST'])
@api_login_required
def handle_datasets():
    user_id = session['username']
    if request.method == 'GET':
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
        vn = configure_vanna_for_request(vn, user_id)
        
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

    return jsonify({
        'documentation': documentation,
        'qa_pairs': qa_pairs,
        'dataset_analysis': dataset_analysis,
        'pagination': {
            'current_page': page,
            'total_pages': total_pages,
            'total_count': total_count
        }
    })

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
    vn = get_vanna_instance(user_id)
    vn = configure_vanna_for_request(vn, user_id)

    def generate_progress():
        try:
            ddl = request.form.get('ddl')
            documentation = request.form.get('doc', '')
            qa_pairs_json = request.form.get('qa_pairs')
            qa_pairs = json.loads(qa_pairs_json) if qa_pairs_json else []

            yield f"data: {json.dumps({'percentage': 0, 'message': '開始訓練...'})}\n\n"
            
            total_steps = bool(ddl) + bool(documentation) + bool(qa_pairs)
            completed_steps = 0

            if ddl:
                vn.train(ddl=ddl)
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*100, 'message': 'DDL 訓練完成。'})}\n\n"
            
            if documentation:
                vn.train(documentation=documentation)
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*100, 'message': '文件訓練完成。'})}\n\n"

            if qa_pairs:
                for pair in qa_pairs:
                    if pair.get('question') and pair.get('sql'):
                        vn.train(question=pair['question'], sql=pair['sql'])
                completed_steps += 1
                yield f"data: {json.dumps({'percentage': (completed_steps/total_steps)*100, 'message': f'問答配對 ({len(qa_pairs)} 組) 訓練完成。'})}\n\n"

            yield f"data: {json.dumps({'percentage': 100, 'message': '所有訓練步驟已完成。'})}\n\n"

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

    vn = get_vanna_instance(user_id)
    
    def run_vanna_in_thread(question):
        try:
            vn_thread = configure_vanna_for_request(get_vanna_instance(user_id), user_id)
            sql = vn_thread.generate_sql(question=question)
            vn.log_queue.put({'type': 'sql_result', 'sql': sql})
            
            df = vn_thread.run_sql(sql=sql)
            result_string = df.to_string()
            vn.log_queue.put({'type': 'data_result', 'data': result_string})

        except Exception as e:
            vn.log_queue.put({'type': 'error', 'message': str(e)})
        finally:
            vn.log_queue.put(None)

    thread = Thread(target=run_vanna_in_thread, args=(question,))
    thread.start()

    def stream_logs():
        while True:
            item = vn.log_queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

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
        try:
            vn = get_vanna_instance(user_id)
            vn = configure_vanna_for_request(vn, user_id)
            queries = [q.strip() for q in sql_content.split(';') if q.strip()]
            total_queries = len(queries)
            yield f"data: {json.dumps({'status': 'starting', 'total': total_queries})}\n\n"
            system_prompt = "You are an expert at guessing the business question that a SQL query is answering. The user will provide a SQL query. Your task is to return a single, concise business question, in Traditional Chinese (繁體中文), that the SQL query answers. Do not add any explanation or preamble."
            
            for i, sql_query in enumerate(queries):
                try:
                    question = vn.submit_prompt([
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': sql_query}
                    ])
                    qa_pair = {'question': question, 'sql': sql_query}
                except Exception as e:
                    qa_pair = {'question': f"生成問題時發生錯誤: {str(e)}", 'sql': sql_query}
                
                yield f"data: {json.dumps({'status': 'progress', 'count': i + 1, 'total': total_queries, 'qa_pair': qa_pair})}\n\n"
            
            yield f"data: {json.dumps({'status': 'completed', 'message': '問答配對已全部生成！'})}\n\n"
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
        prompt = f"""
        基於以下 DDL 語句：
        ---
        {ddl}
        ---
        請為我生成兩部分內容：

        1.  **實體關係圖 (ER Model)**：使用純文字和 ASCII 字元，創建一個垂直的實體關係圖，清晰地展示資料表之間的關係 (例如 one-to-one, one-to-many)。
        2.  **實體結構說明**：在圖表下方，用簡潔的業務術語逐點描述每個資料表及其主要用途。

        請將這兩部分內容合併為一個單一的、格式化的純文字區塊返回，不要包含任何 Markdown 標籤。
        """
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
    try:
        vn = get_vanna_instance(user_id)
        vn = configure_vanna_for_request(vn, user_id)

        df_information_schema = vn.run_sql("""
            SELECT
                'main' as table_catalog,
                'main' as table_schema,
                m.name as table_name,
                p.name as column_name,
                p.type as data_type,
                '' as comment
            FROM sqlite_master m
            JOIN pragma_table_info(m.name) p
            WHERE m.type = 'table' AND m.name NOT LIKE 'sqlite_%'
        """)

        if df_information_schema.empty:
             return jsonify({"status": "success", "analysis": []})

        training_plan = vn.get_training_plan_generic(df=df_information_schema)
        
        analysis_results = []
        for item in training_plan._plan:
            if item.item_type == 'documentation':
                analysis_results.append({
                    "table_name": item.item_name,
                    "suggested_documentation": item.item_value,
                })

        return jsonify({"status": "success", "analysis": analysis_results})
    except Exception as e:
        app.logger.error(f"Schema analysis failed for user '{user_id}': {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', debug=debug_mode, port=5001)