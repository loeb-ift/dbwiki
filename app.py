import logging
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, session
import os
from dotenv import load_dotenv
import re
import json
import sqlite3

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DatabaseError
from vanna.ollama import Ollama
from vanna.chromadb import ChromaDB_VectorStore
from vanna.types import TrainingPlan
import pandas as pd

from werkzeug.middleware.proxy_fix import ProxyFix
import requests

# 加載環境變量
load_dotenv()

def init_training_db():
    """Initializes the training database and creates tables if they don't exist."""
    db_path = os.getenv('TRAINING_DATA_DB_PATH', 'training_data.sqlite') # Provide a default path
    
    # Ensure db_path is an absolute path
    db_path = os.path.abspath(db_path)

    if not db_path: # Check again after abspath, though unlikely to be empty
        print("WARNING: TRAINING_DATA_DB_PATH is empty after path resolution. Skipping training DB initialization.")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create training_ddl table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_ddl (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ddl_statement TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create training_documentation table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_documentation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                documentation_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create training_qa table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_qa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                sql_query TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.commit()
        
        # Verify if training_qa table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='training_qa';")
        if cursor.fetchone() is None:
            conn.close()
            print(f"ERROR: 'training_qa' table was not created in database at '{db_path}'.") # Add print for visibility
            raise Exception(f"ERROR: 'training_qa' table was not created in database at '{db_path}'.")

        conn.close()
        print(f"INFO: Training database at '{db_path}' initialized successfully.")
    except sqlite3.Error as e:
        print(f"ERROR: Could not initialize training database at '{db_path}': {e}")
        raise # Re-raise the exception to propagate it
    except Exception as e: # Catch any other exceptions during initialization
        print(f"ERROR: An unexpected error occurred during training database initialization at '{db_path}': {e}")
        raise


# 初始化 Flask 應用
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1, x_prefix=1)

# 初始化訓練數據庫
init_training_db()

# 創建 Vanna 實例
class MyVanna(Ollama, ChromaDB_VectorStore):
    def __init__(self, config=None, collection_name='my_collection', persist_directory='./chroma_data'):
        model = os.getenv('OLLAMA_MODEL')
        if model is None:
            raise ValueError("OLLAMA_MODEL environment variable not set. Please set it in your .env file.")

        ollama_config = {
            'model': model,
            'ollama_host': os.getenv('OLLAMA_HOST'),
        }
        Ollama.__init__(self, config=ollama_config)
        # 设置 ChromaDB 的持久化目录
        chroma_config = {
            'collection_name': collection_name,
            'persist_directory': persist_directory # 将数据持久化到项目根目录下的 chroma_data 文件夹
        }
        ChromaDB_VectorStore.__init__(self, config=chroma_config)

# --- 猴子補丁：阻止 Vanna 自動拉取模型 ---
# 當前的 Vanna 庫版本似乎忽略了 'pull_model' 配置。
# 此補丁將覆蓋負責拉取模型的私有方法，使其不執行任何操作。
def _noop_pull_model(self, client, model_name):
    """一個空操作函數，用於替換模型拉取邏輯。"""
    print(f"INFO: 補丁已激活。跳過對 '{model_name}' 的 Ollama 模型拉取。")
    pass

Ollama._Ollama__pull_model_if_ne = _noop_pull_model
# ----------------------------------------------------

print(f"DEBUG: OLLAMA_MODEL before MyVanna init: {os.getenv('OLLAMA_MODEL')}")

# 全局字典，用于存储不同数据集的 Vanna 实例
vanna_instances = {}
# 当前活跃的 Vanna 实例的键
current_vanna_instance_key = None

def get_vanna_instance(collection_name='my_collection', persist_directory='./chroma_data'):
    global current_vanna_instance_key
    key = f"{collection_name}-{persist_directory}"
    if key not in vanna_instances:
        print(f"INFO: Creating new Vanna instance for collection '{collection_name}' in '{persist_directory}'")
        vanna_instances[key] = MyVanna(collection_name=collection_name, persist_directory=persist_directory)
    current_vanna_instance_key = key
    return vanna_instances[key]

# 初始 Vanna 实例
vn = get_vanna_instance()

def load_training_data_from_db(vanna_instance):
    """Loads all training data from the SQLite database and trains the Vanna model."""
    db_path = os.getenv('TRAINING_DATA_DB_PATH')
    if not db_path or not os.path.exists(db_path):
        print(f"INFO: Training data database not found at '{db_path}'. Skipping initial training.")
        return

    print(f"INFO: Loading training data from '{db_path}'...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. Load DDL
        cursor.execute("SELECT ddl_statement FROM training_ddl")
        ddl_rows = cursor.fetchall()
        ddls = list(set([row[0] for row in ddl_rows]))

        # 2. Load Documentation
        cursor.execute("SELECT documentation_text FROM training_documentation")
        doc_rows = cursor.fetchall()
        docs = list(set([row[0] for row in doc_rows]))

        # 3. Load QA pairs
        cursor.execute("SELECT question, sql_query FROM training_qa")
        qa_rows = cursor.fetchall()
        qa_pairs = [{'question': row[0], 'sql': row[1]} for row in qa_rows]

        conn.close()

        # 4. Train the model with loaded data
        if ddls or docs or qa_pairs:
            print("INFO: Training Vanna model with loaded data...")

            # 獲取現有的訓練資料，以便檢查重複
            existing_training_data = vanna_instance.get_training_data()
            print(f"DEBUG: Existing training data types: {existing_training_data['training_data_type'].unique()}")
            existing_ddls = set(existing_training_data[existing_training_data['training_data_type'].str.lower() == 'ddl']['content'].tolist())
            existing_docs = set(existing_training_data[existing_training_data['training_data_type'].str.lower() == 'documentation']['content'].tolist())

            # 先處理 DDL 語句
            for ddl in ddls:
                if ddl not in existing_ddls:
                    vanna_instance.train(ddl=ddl)
                else:
                    print(f"INFO: Skipping DDL training for already existing DDL: {ddl[:50]}...")

            # 處理文檔
            for doc in docs:
                if doc not in existing_docs:
                    vanna_instance.train(documentation=doc)
                else:
                    print(f"INFO: Skipping documentation training for already existing documentation: {doc[:50]}...")

            # 處理 QA 配對 (這裡假設 QA 配對不會重複，或者重複訓練是可接受的)
            for pair in qa_pairs:
                vanna_instance.train(question=pair['question'], sql=pair['sql'])

        print("INFO: Training data loaded and Vanna model trained.")

    except Exception as e:
        print(f"ERROR: Failed to load training data from DB: {e}")

# Load existing training data on startup
load_training_data_from_db(vn)

@app.route('/')
def index():
    """
    渲染主頁面。
    """
    return render_template('index.html')

# --- API Endpoints ---
@app.route('/api/get_db_config', methods=['GET'])
def get_db_config():
    """
    API 端點：讀取 .env 文件並返回數據庫配置。
    """
    try:
        # 重新加載 .env 文件以確保獲取最新值
        load_dotenv(override=True)

        configs = {
            "postgresql": {"enabled": False},
            "mysql": {"enabled": False},
            "mssql": {"enabled": False},
            "sqlite": {"enabled": False},
            "csv": {"enabled": False}
        }
        
        active_type = os.getenv('DB_TYPE')
        if active_type:
            active_type = active_type.lower()

        # 遍歷所有可能的數據庫類型，從環境變量中提取配置
        for db_type_key in configs.keys():
            prefix = f"DB_{db_type_key.upper()}_"
            current_config = {}
            
            # 檢查特定於類型的變量
            for key_suffix in ["HOST", "PORT", "USER", "PASSWORD", "NAME", "FILE"]:
                env_var_name = f"{prefix}{key_suffix}"
                value = os.getenv(env_var_name)
                if value is not None:
                    current_config[key_suffix.lower()] = value
            
            # 檢查通用變量，如果特定類型沒有設置
            if not current_config.get("host"):
                current_config["host"] = os.getenv("DB_HOST")
            if not current_config.get("port"):
                current_config["port"] = os.getenv("DB_PORT")
            if not current_config.get("user"):
                current_config["user"] = os.getenv("DB_USER")
            if not current_config.get("password"):
                current_config["password"] = os.getenv("DB_PASSWORD")
            if not current_config.get("name"):
                current_config["name"] = os.getenv("DB_NAME")
            if not current_config.get("file"):
                current_config["file"] = os.getenv("DB_FILE")

            # 根據配置的存在性設置 enabled 狀態
            if db_type_key in ['sqlite', 'csv']:
                configs[db_type_key]["enabled"] = bool(current_config.get("file") or current_config.get("name"))
            else:
                configs[db_type_key]["enabled"] = bool(current_config.get("host") and current_config.get("name"))

            # 為了與前端兼容，重命名一些鍵
            if "user" in current_config:
                current_config["username"] = current_config.pop("user")
            if "name" in current_config:
                current_config["database"] = current_config.pop("name")
            if "file" in current_config:
                current_config["database_file"] = current_config.pop("file")

            configs[db_type_key].update(current_config)

        return jsonify({
            "active_type": active_type,
            "configs": configs
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def get_connection_uri(config):
    """根據配置生成 SQLAlchemy 連接 URI。"""
    db_type = config.get('type')
    user = config.get('username')
    password = config.get('password')
    host = config.get('host')
    port = config.get('port')
    dbname = config.get('database') # For SQLite, this will be the file path

    if db_type == 'postgresql':
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    elif db_type == 'mysql':
        return f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{dbname}"
    elif db_type == 'mssql':
        # 注意：MSSQL 可能需要 ODBC 驅動
        driver = 'ODBC Driver 17 for SQL Server'
        return f"mssql+pyodbc://{user}:{password}@{host}:{port}/{dbname}?driver={driver}"
    elif db_type == 'sqlite':
        return f"sqlite:///{dbname}" # dbname is the path to the .db file
    else:
        return None

import tempfile
from werkzeug.utils import secure_filename

@app.route('/api/connect', methods=['POST'])
def connect_database():
    global vn
    """
    API 端點：連接到用戶指定的數據庫並提取 DDL。
    現在支持標準 SQL 數據庫、SQLite 和上傳的 CSV 文件。
    """
    # 檢查請求是 JSON 還是 FormData
    if request.is_json:
        config = request.json
        db_type = config.get('type')
        dataset_name = config.get('dataset_name', 'default_dataset') # 从请求中获取数据集名称
    else:
        config = request.form.to_dict()
        db_type = config.get('type')
        dataset_name = config.get('dataset_name', 'default_dataset') # 从请求中获取数据集名称

    # 根据数据集名称动态设置 ChromaDB 的 collection_name 和 persist_directory
    collection_name = f"vanna_collection_{dataset_name}"
    persist_directory = f"./chroma_data_{dataset_name}"

    # 获取或创建 Vanna 实例
    current_vn = get_vanna_instance(collection_name=collection_name, persist_directory=persist_directory)
    
    # 處理文件上傳 (CSV 或 SQLite)
    if 'database_file' in request.files:
        file = request.files['database_file']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'No selected file'}), 400
        
        filename = secure_filename(file.filename)
        # 將文件保存到臨時目錄
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, filename)
        file.save(file_path)
        
        config['database'] = file_path # 將路徾以用於後續處理

    # 處理 CSV 文件
    if db_type == 'csv':
        csv_path = config.get('database')
        if not csv_path or not os.path.exists(csv_path):
            return jsonify({'status': 'error', 'message': f"CSV file not found at path: {csv_path}"}), 400
        
        try:
            # 1. 讀取 CSV 到 DataFrame
            df = pd.read_csv(csv_path)
            file_root, _ = os.path.splitext(os.path.basename(csv_path))
            table_name = file_root.replace('-', '_').replace(' ', '_')

            # 2. 創建一個臨時的 SQLite 資料庫文件
            temp_db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
            temp_db_path = temp_db_file.name
            temp_db_file.close()
            
            # 將臨時文件路徾儲存起來，以防止它被垃圾回收
            app.config['TEMP_DB_PATH'] = temp_db_path
            
            # 3. 將 DataFrame 寫入到這個臨時的 SQLite 文件中
            engine = create_engine(f'sqlite:///{temp_db_path}')
            df.to_sql(table_name, engine, index=False, if_exists='replace')

            # 4. 直接將創建的引擎賦值給 Vanna 實例
            current_vn.engine = engine
            
            # 5. 設定 run_sql 函數以使用臨時 SQLite 資料庫
            def run_sql_sqlite(sql: str) -> pd.DataFrame:
                print(f"Executing SQL: {sql}")
                with current_vn.engine.connect() as connection:
                    result = connection.execute(text(sql))
                    rows = result.fetchall()
                    columns = result.keys()
                    return pd.DataFrame(rows, columns=columns)
            current_vn.run_sql = run_sql_sqlite
            current_vn.run_sql_is_set = True
            
            # 6. 從 DataFrame 生成 DDL
            from pandas.io import sql as pd_sql
            ddl = pd_sql.get_schema(df, table_name)
            
            # 更新全局 Vanna 实例
            vn = current_vn

            return jsonify({
                'status': 'success',
                'message': f"CSV data loaded into in-memory database. Table '{table_name}' created. DDL generated.",
                'ddl': ddl
            })
        except Exception as e:
            app.logger.error(f"Error processing CSV file: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': f"Error processing CSV file: {str(e)}"}), 500
 
    # 處理基於 SQLAlchemy 的數據庫 (PostgreSQL, MySQL, MSSQL, SQLite)
    try:
        if db_type == 'postgresql':
            current_vn.connect_to_postgresql(host=config.get('host'), dbname=config.get('database'), user=config.get('username'), password=config.get('password'), port=config.get('port'))
            current_vn.run_sql_is_set = True
        elif db_type == 'mysql':
            current_vn.connect_to_mysql(host=config.get('host'), db=config.get('database'), user=config.get('username'), password=config.get('password'), port=config.get('port'))
            current_vn.run_sql_is_set = True
        elif db_type == 'mssql':
            # 构建 ODBC 连接字符串
            odbc_conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={config.get('host')},{config.get('port')};"
                f"DATABASE={config.get('database')};"
                f"UID={config.get('username')};"
                f"PWD={config.get('password')}"
            )
            current_vn.connect_to_mssql(odbc_conn_str=odbc_conn_str)
            current_vn.run_sql_is_set = True
        elif db_type == 'sqlite':
            current_vn.connect_to_sqlite(config.get('database'))
            current_vn.run_sql_is_set = True
        else:
            return jsonify({'status': 'error', 'message': f"Unsupported database type: {db_type}"}), 400
 
        # 更新全局 Vanna 实例
        vn = current_vn

        ddl_statements = current_vn.get_ddl()
 
        return jsonify({
            'status': 'success',
            'message': 'Connection successful. DDL extracted.',
            'ddl': ddl_statements
        })
    except DatabaseError as e:
        if db_type == 'sqlite' and 'file is not a database' in str(e):
            return jsonify({'status': 'error', 'message': 'The uploaded file is not a valid SQLite database. Please check the file or select the correct database type (e.g., CSV).'}), 400
        return jsonify({'status': 'error', 'message': f"A database error occurred: {str(e)}", 'error_type': type(e).__name__}), 500
    except Exception as e:
        app.logger.error(f"An unexpected error occurred in connect_database: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': f"An unexpected error occurred: {str(e)}", 'error_type': type(e).__name__}), 500

@app.route('/api/get_csv_table_info', methods=['GET'])
def get_csv_table_info():
    """
    API 端點：獲取當前連接的 SQLite 資料庫（來自 CSV 轉換）中的表名和行數。
    """
    global current_vanna_instance_key, vanna_instances
    if current_vanna_instance_key is None or current_vanna_instance_key not in vanna_instances:
        return jsonify({'status': 'error', 'message': '沒有活躍的 Vanna 實例。'}), 400
    
    current_vn = vanna_instances[current_vanna_instance_key]

    if not hasattr(current_vn, 'engine') or current_vn.engine.name != 'sqlite':
        return jsonify({'status': 'error', 'message': '未連接到 SQLite 資料庫或未從 CSV 轉換。'}), 400

    try:
        inspector = inspect(current_vn.engine)
        table_names = inspector.get_table_names()
        
        if not table_names:
            return jsonify({'status': 'error', 'message': 'SQLite 資料庫中沒有找到表。'}), 404

        # 假設只有一個表，或者我們只關心第一個表
        if not table_names:
            return jsonify({'status': 'error', 'message': 'SQLite 資料庫中沒有找到表。'}), 404
        table_name = table_names[0]
        
        with vn.engine.connect() as connection:
            result = connection.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            total_rows = result.scalar()

        return jsonify({
            'status': 'success',
            'table_name': table_name,
            'total_rows': total_rows
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"獲取表信息失敗: {str(e)}"}), 500

@app.route('/api/get_table_data', methods=['GET'])
def get_table_data():
    """
    API 端點：獲取指定 SQLite 表的帶分頁數據。
    """
    table_name = request.args.get('table_name')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))

    if not table_name:
        return jsonify({'status': 'error', 'message': '缺少表名。'}), 400

    global current_vanna_instance_key, vanna_instances
    if current_vanna_instance_key is None or current_vanna_instance_key not in vanna_instances:
        return jsonify({'status': 'error', 'message': '沒有活躍的 Vanna 實例。'}), 400
    
    current_vn = vanna_instances[current_vanna_instance_key]

    if not hasattr(current_vn, 'engine') or current_vn.engine.name != 'sqlite':
        return jsonify({'status': 'error', 'message': '未連接到 SQLite 資料庫。'}), 400

    try:
        offset = (page - 1) * page_size
        with current_vn.engine.connect() as connection:
            # 獲取列名
            columns_result = connection.execute(text(f"PRAGMA table_info({table_name})"))
            column_names = [row[1] for row in columns_result.fetchall()] # 提取列名

            # 獲取分頁數據
            data_result = connection.execute(text(f"SELECT * FROM {table_name} LIMIT {page_size} OFFSET {offset}"))
            rows = data_result.fetchall()
            
            # 將行轉換為字典列表
            data = [dict(zip(column_names, row)) for row in rows]

        return jsonify({
            'status': 'success',
            'data': data,
            'page': page,
            'page_size': page_size
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"獲取表數據失敗: {str(e)}"}), 500


@app.route('/api/analyze_ddl', methods=['POST'])
def analyze_ddl():
    """
    API 端點：使用 LLM 分析 DDL 並生成業務文檔。
    """
    data = request.json
    ddl = data.get('ddl')

    if not ddl:
        return jsonify({'status': 'error', 'message': 'DDL is required.'}), 400

    try:
        # 建立一個提示，要求 LLM 為 DDL 生成文件
        prompt = f"Please generate business-friendly documentation for the following DDL statements:\n\n{ddl}"

        # 直接使用繼承自 Ollama 的 submit_prompt 方法與 LLM 互動
        # 我們假設 submit_prompt 返回的是一個字串
        documentation = vn.submit_prompt([{'role': 'user', 'content': prompt}])
        
        return jsonify({'status': 'success', 'documentation': documentation})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/generate_qa_from_sql', methods=['POST'])
def generate_qa_from_sql():
    """
    API 端點：從上傳的 .sql 文件串流生成問答配對。
    """
    if 'sql_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No sql_file part in the request'}), 400

    file = request.files['sql_file']

    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No selected file'}), 400

    if not file or not file.filename.lower().endswith('.sql'):
        return jsonify({'status': 'error', 'message': 'Invalid file type. Please upload a .sql file.'}), 400

    sql_content = file.read().decode('utf-8')

    def stream_qa_generation(sql_content):
        """生成器函式，用於串流問答配對的生成過程。"""
        try:
            app.logger.info("Entered stream_qa_generation function.")
            queries = [q.strip() for q in sql_content.split(';') if q.strip()]
            total_queries = len(queries)

            # 1. Yield 一個初始事件，包含總數
            yield f"data: {json.dumps({'status': 'starting', 'total': total_queries})}\n\n"

            system_prompt = "You are an expert at guessing the business question that a SQL query is answering. The user will provide a SQL query. Your task is to return a single, concise business question, in Traditional Chinese (繁體中文), that the SQL query answers. Do not add any explanation or preamble."

            # 2. 遍歷查詢並生成問答
            llm_host = os.getenv('OLLAMA_HOST', 'N/A')
            llm_model = os.getenv('OLLAMA_MODEL', 'N/A')
            app.logger.info(f"Starting QA generation for {total_queries} queries using model '{llm_model}' at host '{llm_host}'.")
            
            for i, sql_query in enumerate(queries):
                qa_pair = {}
                try:
                    app.logger.info(f"[Query {i+1}/{total_queries}] Sending SQL to LLM: {sql_query}")
                    question = vn.submit_prompt([
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': sql_query}
                    ])
                    
                    if question:
                        app.logger.info(f"[Query {i+1}/{total_queries}] Generated Question: {question}")
                        qa_pair = {'question': question, 'sql': sql_query}
                    else:
                        # 如果無法生成問題，也提供一個有效的結構
                        qa_pair = {'question': '無法為此 SQL 生成問題。', 'sql': sql_query}
    
                except Exception as e:
                    app.logger.error(f"[Query {i+1}/{total_queries}] Could not generate question for SQL: {sql_query}. Error: {e}")
                    qa_pair = {'question': f"生成問題時發生錯誤: {str(e)}", 'sql': sql_query}
                
                # 3. Yield 一個進度事件，包含當前計數、總數和生成的配對
                yield f"data: {json.dumps({'status': 'progress', 'count': i + 1, 'total': total_queries, 'qa_pair': qa_pair})}\n\n"
            
            # 4. Yield 一個最終的完成事件
            yield f"data: {json.dumps({'status': 'completed', 'message': '問答配對已全部生成！'})}\n\n"

        except Exception as e:
            # 在發生錯誤時，記錄詳細的錯誤日誌並發送事件
            app.logger.error(f"An error occurred in stream_qa_generation: {e}", exc_info=True)
            error_message = json.dumps({'status': 'error', 'message': str(e)})
            yield f"data: {error_message}\n\n"

    # 5. 返回串流響應
    return Response(stream_with_context(stream_qa_generation(sql_content)), mimetype='text/event-stream')


@app.route('/api/regenerate_question', methods=['POST'])
def regenerate_question():
    """
    API 端點：為單一的 SQL 查詢重新生成問題。
    """
    data = request.get_json()
    sql_query = data.get('sql')

    if not sql_query:
        return jsonify({'status': 'error', 'message': 'SQL query is required.'}), 400

    try:
        # 定義一個包含繁體中文指令的系統提示詞
        system_prompt = "You are an expert at guessing the business question that a SQL query is answering. The user will provide a SQL query. Your task is to return a single, concise business question, in Traditional Chinese (繁體中文), that the SQL query answers. Do not add any explanation or preamble."

        # 組合提示詞並發送給 LLM
        question = vn.submit_prompt([
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': sql_query}
        ])
        if question:
            return jsonify({'question': question})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to generate question.'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/get_training_data', methods=['GET'])
def get_training_data():
    """
    API 端點：獲取所有已儲存的訓練資料。
    """
    db_path = os.getenv('TRAINING_DATA_DB_PATH')
    if not db_path or not os.path.exists(db_path):
        return jsonify({
            'ddl': [],
            'documentation': [],
            'qa_pairs': []
        })
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row # 允許按列名訪問
        cursor = conn.cursor()

        # 1. 獲取 DDL
        cursor.execute("SELECT ddl_statement FROM training_ddl")
        ddl_rows = cursor.fetchall()
        ddls = [row['ddl_statement'] for row in ddl_rows]

        # 2. 獲取文件
        cursor.execute("SELECT documentation_text FROM training_documentation")
        doc_rows = cursor.fetchall()
        docs = [row['documentation_text'] for row in doc_rows]

        # 3. 獲取 QA 配對 (包含 id)
        cursor.execute("SELECT id, question, sql_query FROM training_qa")
        qa_rows = cursor.fetchall()
        qa_pairs = [{'id': row['id'], 'question': row['question'], 'sql': row['sql_query']} for row in qa_rows]

        conn.close()

        return jsonify({
            'ddl': ddls,
            'documentation': docs,
            'qa_pairs': qa_pairs
        })

    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"Database error: {e}"}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/update_qa_question', methods=['POST'])
def update_qa_question():
    """
    API 端點：更新單一問答配對的問題。
    """
    data = request.get_json()
    qa_id = data.get('id')
    new_question = data.get('question')

    logging.info(f"Received update_qa_question request: qa_id={qa_id}, new_question={new_question}")

    if not qa_id or new_question is None:
        logging.warning(f"Invalid request for update_qa_question: qa_id={qa_id}, new_question={new_question}")
        return jsonify({'status': 'error', 'message': 'ID and question are required.'}), 400

    db_path = os.getenv('TRAINING_DATA_DB_PATH')
    if not db_path:
        logging.error("TRAINING_DATA_DB_PATH not configured.")
        return jsonify({'status': 'error', 'message': 'Training database path not configured.'}), 500

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE training_qa SET question = ? WHERE id = ?", (new_question, qa_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            conn.close()
            logging.warning(f"No QA pair found with id {qa_id} for update.")
            return jsonify({'status': 'error', 'message': f'No QA pair found with id {qa_id}.'}), 404

        conn.close()
        logging.info(f"Successfully updated QA pair with id {qa_id}.")
        return jsonify({'status': 'success', 'message': 'Question updated successfully.'})

    except sqlite3.Error as e:
        logging.exception(f"Database error during update_qa_question for id {qa_id}.")
        return jsonify({'status': 'error', 'message': f"Database error: {e}"}), 500
    except Exception as e:
        logging.exception(f"Unexpected error during update_qa_question for id {qa_id}.")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/add_qa_question', methods=['POST'])
def add_qa_question():
    """
    API 端點：添加新的問答配對。
    """
    data = request.get_json()
    question = data.get('question')
    sql_query = data.get('sql')

    if not question or not sql_query:
        return jsonify({'status': 'error', 'message': 'Question and SQL query are required.'}), 400

    db_path = os.getenv('TRAINING_DATA_DB_PATH', 'training_data.sqlite') # Provide a default path
    
    # Ensure db_path is an absolute path
    db_path = os.path.abspath(db_path)

    if not db_path: # Check again after abspath, though unlikely to be empty
        return jsonify({'status': 'error', 'message': 'Training database path not configured or is empty.'}), 500

    # 確保資料庫文件存在，如果不存在則嘗試初始化
    if not os.path.exists(db_path):
        print(f"INFO: Training database file not found at '{db_path}'. Attempting to re-initialize.")
        init_training_db()
        if not os.path.exists(db_path):
            return jsonify({'status': 'error', 'message': 'Training database could not be initialized.'}), 500

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 檢查是否已存在相同的 question 和 sql_query
        cursor.execute("SELECT id FROM training_qa WHERE question = ? AND sql_query = ?", (question, sql_query))
        existing_qa = cursor.fetchone()

        if existing_qa:
            conn.close()
            return jsonify({'status': 'info', 'message': 'QA pair already exists. Skipping addition.', 'id': existing_qa})
        
        cursor.execute("INSERT INTO training_qa (question, sql_query) VALUES (?, ?)", (question, sql_query))
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'QA pair added successfully.', 'id': new_id})

    except sqlite3.Error as e:
        app.logger.error(f"SQLite database error in add_qa_question: {e}", exc_info=True)
        print(f"ERROR: SQLite database error in add_qa_question: {e}") # Add print for visibility
        return jsonify({'status': 'error', 'message': f"Database error: {e}"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in add_qa_question: {e}", exc_info=True)
        print(f"ERROR: Unexpected error in add_qa_question: {e}") # Add print for visibility
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/train', methods=['POST'])
def train_model():
    """
    API 端點：使用 DDL、文件和問答配對統一進行訓練。
    此端點使用串流響應來回報進度。
    """
    def generate_progress():
        try:
            # 0. 發送開始信號
            yield f"data: {json.dumps({'status': 'starting', 'message': '開始訓練...', 'percentage': 0})}\n\n"

            # 1. 從請求中提取所有訓練資料
            ddl = request.form.get('ddl')
            documentation = request.form.get('doc', '')
            qa_pairs_json = request.form.get('qa_pairs')

            # 處理文件上傳
            if 'doc_file' in request.files:
                doc_file = request.files['doc_file']
                if doc_file.filename != '':
                    doc_content = doc_file.read().decode('utf-8')
                    documentation += f"\n\n{doc_content}"

            # 解析 QA 配對
            qa_pairs = []
            if qa_pairs_json:
                try:
                    qa_pairs = json.loads(qa_pairs_json)
                    if not isinstance(qa_pairs, list):
                        qa_pairs = [] # 如果格式不對，則清空
                except json.JSONDecodeError:
                    error_message = json.dumps({'status': 'error', 'message': 'Invalid JSON format for qa_pairs.'})
                    yield f"data: {error_message}\n\n"
                    return

            # 2. 將訓練資料儲存到資料庫 (如果需要)
            # 這部分可以保持同步，因為它通常很快
            db_path = os.getenv('TRAINING_DATA_DB_PATH')
            if db_path:
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
                                # 檢查是否已存在相同的 question 和 sql_query
                                cursor.execute("SELECT id FROM training_qa WHERE question = ? AND sql_query = ?", (pair['question'], pair['sql']))
                                existing_qa = cursor.fetchone()
                                if not existing_qa:
                                    cursor.execute("INSERT INTO training_qa (question, sql_query) VALUES (?, ?)", (pair['question'], pair['sql']))
                                else:
                                    print(f"INFO: Skipping QA pair addition for already existing: Question='{pair['question'][:50]}...', SQL='{pair['sql'][:50]}...'")
                    conn.commit()
                    conn.close()
                except sqlite3.Error as e:
                    print(f"WARNING: Could not save training data to database '{db_path}': {e}")


            # 3. 使用 Vanna 實例分步進行訓練並回報進度
            total_steps = bool(ddl) + bool(documentation) + bool(qa_pairs)
            completed_steps = 0
            
            if not total_steps:
                message = 'No new training data was provided to train.'
                yield f"data: {json.dumps({'status': 'completed', 'message': message, 'percentage': 100})}\n\n"
                return

            # 訓練 DDL
            if ddl:
                vn.train(ddl=ddl)
                completed_steps += 1
                percentage = int((completed_steps / total_steps) * 100) if total_steps > 0 else 0
                yield f"data: {json.dumps({'status': 'progress', 'percentage': percentage, 'message': 'DDL 訓練完成。'})}\n\n"

            # 訓練文件
            if documentation:
                vn.train(documentation=documentation)
                completed_steps += 1
                percentage = int((completed_steps / total_steps) * 100) if total_steps > 0 else 0
                yield f"data: {json.dumps({'status': 'progress', 'percentage': percentage, 'message': '文件訓練完成。'})}\n\n"

            # 訓練 QA 配對
            trained_pairs = 0
            if qa_pairs:
                for pair in qa_pairs:
                    if pair.get('question') and pair.get('sql'):
                        vn.train(question=pair['question'], sql=pair['sql'])
                        trained_pairs += 1
                completed_steps += 1
                percentage = int((completed_steps / total_steps) * 100) if total_steps > 0 else 0
                yield f"data: {json.dumps({'status': 'progress', 'percentage': percentage, 'message': f'問答配對 ({trained_pairs} 組) 訓練完成。'})}\n\n"

            # 4. 返回最終結果
            message = f"Training completed successfully. Trained on: {1 if ddl else 0} DDL, {1 if documentation else 0} documentation, {trained_pairs} QA pairs."
            llm_info = {
                'model': os.getenv('OLLAMA_MODEL'),
                'host': os.getenv('OLLAMA_HOST')
            }
            yield f"data: {json.dumps({'status': 'completed', 'message': message, 'llm_info': llm_info, 'percentage': 100})}\n\n"

        except Exception as e:
            error_message = json.dumps({'status': 'error', 'message': str(e)})
            yield f"data: {error_message}\n\n"

    return Response(stream_with_context(generate_progress()), mimetype='text/event-stream')


@app.route('/api/ask', methods=['POST'])
def ask_question():
    """
    API 端點：接收用戶問題，並以串流方式返回思考過程和最終的 SQL。
    """
    data = request.json
    question = data.get('question')

    if not question:
        return jsonify({'status': 'error', 'message': 'Question is required.'}), 400

    def generate_response_stream():
        import re # Explicitly import re within the function scope
        final_sql = None
        try:
            app.logger.info(f"Received question: {question}")
            app.logger.info("Generating SQL with Vanna in streaming mode...")

            sql_generator = vn.generate_sql(question=question, allow_llm_to_see_data=True)
            
            final_sql = None
            sql_buffer = []

            for chunk in sql_generator:
                if hasattr(chunk, 'sql') and chunk.sql:
                    final_sql = chunk.sql
                    break
                elif isinstance(chunk, str):
                    yield f"data: {json.dumps({'type': 'thinking_step', 'content': chunk})}\n\n"
                    sql_buffer.append(chunk)

            if final_sql is None:
                full_response_str = "".join(sql_buffer).strip()
                sql_match = re.search(r"SELECT.*", full_response_str, re.DOTALL | re.IGNORECASE)
                if sql_match:
                    final_sql = sql_match.group(0)

            if final_sql:
                app.logger.info(f"Final Extracted SQL: {final_sql}")
                yield f"data: {json.dumps({'type': 'sql_result', 'sql': final_sql})}\n\n"
            else:
                raise Exception("Could not extract final SQL from Vanna's response.")

        except Exception as e:
            app.logger.error(f"An error occurred during SQL generation: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'SQL Generation Error: {e}'})}\n\n"
            return

        # --- Execute SQL ---
        try:
            if not hasattr(vn, 'run_sql_is_set') or not vn.run_sql_is_set:
                app.logger.info("Database connection not established before running SQL.")
                yield f"data: {json.dumps({'type': 'error', 'message': 'Database connection not established. Please connect to a database first.'})}\n\n"
                return

            app.logger.info(f"Executing SQL with vn.run_sql...")
            # 從 final_sql 中提取純粹的 SQL 語句，或直接使用 final_sql
            import re
            sql_match = re.search(r'Extracted SQL:\s*(.*)', final_sql, re.DOTALL)
            if sql_match:
                cleaned_sql = sql_match.group(1).strip()
                app.logger.info(f"Cleaned SQL (extracted): {cleaned_sql}")
            else:
                cleaned_sql = final_sql.strip()
                app.logger.info(f"Cleaned SQL (direct use): {cleaned_sql}")

            if cleaned_sql:
                # 檢查 SQL 是否包含 CTE 語法，如果包含，則在前面加上 WITH 關鍵字
                # 判斷是否為缺少 WITH 的 CTE 語法
                # 條件：以 SELECT 開頭，且在某個 ')' 後面緊接著 'CTE_NAME AS (' 的模式
                if re.match(r"^\s*SELECT.*?\)\s*(\w+)\s*AS\s*\(", cleaned_sql, re.DOTALL | re.IGNORECASE):
                    cleaned_sql = "WITH " + cleaned_sql
                df = vn.run_sql(sql=cleaned_sql)
            else:
                raise Exception("Could not determine SQL from Vanna's response.")
            result_string = df.to_string()
            yield f"data: {json.dumps({'type': 'data_result', 'data': result_string})}\n\n"

        except Exception as e:
            app.logger.error(f"Error executing SQL with vn.run_sql: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'SQL Execution Error: {e}'})}\n\n"

    return Response(stream_with_context(generate_response_stream()), mimetype='text/event-stream')

@app.route('/api/generate_questions', methods=['POST'])
def generate_questions():
    """
    API 端點：自動生成訓練問題並立即用於訓練。
    """
    # 生成問題
    try:
        questions = vn.generate_questions()
        if not questions:
            return jsonify({'status': 'success', 'message': 'No new questions were generated.', 'questions': []})

        # 使用生成的問題進行訓練
        for q in questions:
            # 假設 q 是一個包含 'question' 和 'sql' 的字典
            if q.get('question') and q.get('sql'):
                vn.train(question=q.get('question'), sql=q.get('sql'))
        
        return jsonify({'status': 'success', 'message': f'{len(questions)} questions generated and model retrained.', 'questions': questions})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/reload_training_data', methods=['POST'])
def reload_training_data():
    """
    API 端點：重新載入訓練資料並重新訓練 Vanna 模型。
    """
    try:
        load_training_data_from_db(vn)
        return jsonify({'status': 'success', 'message': 'Training data reloaded and model retrained successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to reload training data: {str(e)}'}), 500

@app.route('/api/deduplicate_qa', methods=['POST'])
def deduplicate_qa():
    """
    API 端點：清理 training_qa 表中的重複問答對。
    """
    db_path = os.getenv('TRAINING_DATA_DB_PATH')
    if not db_path or not os.path.exists(db_path):
        return jsonify({'status': 'error', 'message': 'Training database path not configured or database file not found.'}), 500

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 找到所有重複的問答對，並保留每個重複組中的一個最小 ID
        cursor.execute("""
            DELETE FROM training_qa
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM training_qa
                GROUP BY question, sql_query
            );
        """)
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        response_data = {
            'status': 'success',
            'message': f'Successfully removed {deleted_count} duplicate QA pairs.',
            'deleted_count': deleted_count
        }
        print(json.dumps(response_data, ensure_ascii=False, indent=4)) # 打印 JSON 響應到控制台
        return jsonify(response_data)

    except sqlite3.Error as e:
        return jsonify({'status': 'error', 'message': f"Database error during deduplication: {e}"}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"An unexpected error occurred during deduplication: {str(e)}"}), 500


if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', debug=debug_mode, port=5001)


@app.route('/@vite/client')
def vite_client():
    """
    代理 Vite 開發伺服器的 @vite/client 請求。
    """
    try:
        resp = requests.get('http://localhost:5173/@vite/client')
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for name, value in resp.raw.headers.items() if name.lower() not in excluded_headers]
        return Response(resp.content, resp.status_code, headers)
    except requests.exceptions.ConnectionError:
        return "Vite development server not running", 500

@app.route('/src/<path:filename>')
def vite_src(filename):
    """
    代理 Vite 開發伺服器的 /src/ 請求。
    """
    try:
        resp = requests.get(f'http://localhost:5173/src/{filename}')
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for name, value in resp.raw.headers.items() if name.lower() not in excluded_headers]
        return Response(resp.content, resp.status_code, headers)
    except requests.exceptions.ConnectionError:
        return "Vite development server not running", 500