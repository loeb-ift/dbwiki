import sqlite3
import os
import logging
import json
import re

handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def validate_user_id(user_id: str) -> tuple[bool, str]:
    """验证用户ID是否符合要求，不含 . / 空白等特殊字符"""
    logger.debug(f"Validating user ID: '{user_id}'")
    
    if not user_id:
        logger.debug(f"Validation failed: User ID is empty")
        return False, "User ID cannot be empty"
    
    # 检查是否包含不允许的字符：. / 和空白字符
    if re.search(r'[./\s]', user_id):
        logger.debug(f"Validation failed: User ID '{user_id}' contains invalid characters")
        return False, f"User ID '{user_id}' contains invalid characters (. / or whitespace)"
    
    # 检查长度是否合理
    if len(user_id) > 50:
        logger.debug(f"Validation failed: User ID '{user_id}' is too long ({len(user_id)} characters, max 50)")
        return False, "User ID is too long (max 50 characters)"
    
    logger.debug(f"User ID '{user_id}' validation passed")
    return True, "User ID is valid"

def get_user_db_path(user_id: str) -> str:
    # 验证用户ID格式
    is_valid, message = validate_user_id(user_id)
    if not is_valid:
        logger.error(f"Invalid user ID: {message}")
        raise ValueError(message)
    
    db_dir = os.path.join(os.getcwd(), 'user_data')
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, f'training_data_{user_id}.sqlite')

def get_user_db_connection(user_id: str) -> sqlite3.Connection:
    # 验证用户ID格式
    is_valid, message = validate_user_id(user_id)
    if not is_valid:
        logger.error(f"Invalid user ID: {message}")
        raise ValueError(message)
    
    db_path = get_user_db_path(user_id)
    conn = sqlite3.connect(db_path)
    
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='datasets';")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        logger.info(f"Table 'datasets' not found for user '{user_id}'. Initializing database.")
        _init_db_tables_and_prompts(conn, user_id)
        logger.info(f"Database initialization finished for user '{user_id}'.")
    else:
        # This is for migrating older databases. Since we deleted the db, this won't run now,
        # but it's good practice to keep it for future schema changes.
        _run_migration_for_existing_db(conn, user_id)

    return conn

def get_db_connection() -> sqlite3.Connection:
    return sqlite3.connect('vanna.db')

def init_training_db(user_id: str):
    try:
        with get_user_db_connection(user_id) as conn:
             pass
    except sqlite3.Error as e:
        logger.error(f"Could not initialize/update training database for user '{user_id}': {e}")
        raise

def _init_db_tables_and_prompts(conn: sqlite3.Connection, user_id: str):
    try:
        cursor = conn.cursor()
        tables = {
            "training_ddl": "(id INTEGER PRIMARY KEY AUTOINCREMENT, ddl_statement TEXT NOT NULL, dataset_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "training_documentation": "(id INTEGER PRIMARY KEY AUTOINCREMENT, documentation_text TEXT NOT NULL, table_name TEXT, dataset_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(dataset_id, table_name))",
            "training_qa": "(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, sql_query TEXT NOT NULL, table_name TEXT, dataset_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "datasets": "(id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_name TEXT NOT NULL, db_path TEXT NOT NULL UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "correction_rules": "(id INTEGER PRIMARY KEY AUTOINCREMENT, incorrect_name TEXT NOT NULL UNIQUE, correct_name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "training_prompts": "(id INTEGER PRIMARY KEY AUTOINCREMENT, prompt_name TEXT NOT NULL, prompt_content TEXT NOT NULL, prompt_type TEXT NOT NULL, prompt_description TEXT, is_global INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(prompt_name, prompt_type))"
        }
        for table_name, schema in tables.items():
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} {schema};")
        
        _insert_default_prompts(conn)
        
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Could not initialize/update training database for user '{user_id}': {e}")
        raise

def _insert_default_prompts(conn: sqlite3.Connection):
    cursor = conn.cursor()
    try:
        prompts_file_path = os.path.join(os.getcwd(), 'prompts', 'default_prompts.json')
        if not os.path.exists(prompts_file_path):
            logger.warning(f"Default prompts file not found at '{prompts_file_path}'. Skipping initialization.")
            return

        with open(prompts_file_path, 'r', encoding='utf-8') as f:
            default_prompts_content = json.load(f)

        prompt_descriptions = {
            'sql_generation': '（核心）指導 AI 如何根據上下文生成 SQL 查詢。',
            'analysis': '（核心）指導 AI 對資料庫的所有訓練資料進行全面的元分析。',
            'documentation': '（核心）指導 AI 作為架構師，從 DDL 逆向工程生成技術文件。',
            'qa_generation_system': '（核心）指導 AI 作為領域專家，從一批 SQL 反向生成高品質的業務問題。',
            'followup_question_generation': '指導 AI 在查詢後生成相關的後續問題。',
            'summary_generation': '指導 AI 對查詢結果生成自然語言摘要。',
            'question_rewriting': '指導 AI 在多輪對話中合併相關問題。',
            'plotly_generation': '指導 AI 根據查詢結果生成視覺化圖表程式碼。',
            'sql_explanation': '指導 AI 解釋 SQL 查詢的含義。',
        }

        for prompt_type, prompt_content in default_prompts_content.items():
            # First, check if a prompt with the given type and global status already exists.
            cursor.execute("SELECT COUNT(*) FROM training_prompts WHERE prompt_type = ? AND is_global = 1", (prompt_type,))
            if cursor.fetchone()[0] > 0:
                logger.debug(f"Default prompt for type '{prompt_type}' already exists. Skipping.")
                continue

            # If not, proceed with insertion.
            prompt_name = f"{prompt_type}_prompt"
            description = prompt_descriptions.get(prompt_type, "預設提示詞。")
            try:
                cursor.execute(
                    "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, prompt_description, is_global) VALUES (?, ?, ?, ?, ?)",
                    (prompt_name, prompt_content, prompt_type, description, 1)
                )
            except sqlite3.IntegrityError:
                # This is a fallback, in case of race conditions in a multi-threaded environment.
                logger.warning(f"Default prompt '{prompt_name}' with type '{prompt_type}' already exists. Skipping.")
    except Exception as e:
        logger.error(f"Failed to initialize default prompts from file: {e}")

def _run_migration_for_existing_db(conn: sqlite3.Connection, user_id: str):
    logger.info(f"Running migration check for existing database of user '{user_id}'.")
    cursor = conn.cursor()

    # Check if the prompts table exists before attempting migrations
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='training_prompts';")
    prompts_table_exists = cursor.fetchone()

    def add_column_if_not_exists(table, column, col_type):
        cursor.execute(f"PRAGMA table_info({table})")
        if column not in [info[1] for info in cursor.fetchall()]:
            logger.info(f"Applying schema migration: Adding column '{column}' to table '{table}'.")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    add_column_if_not_exists('training_ddl', 'dataset_id', 'TEXT')
    add_column_if_not_exists('training_qa', 'dataset_id', 'TEXT')
    add_column_if_not_exists('training_documentation', 'dataset_id', 'TEXT')
    
    # Only add description column if the table exists
    if prompts_table_exists:
        add_column_if_not_exists('training_prompts', 'prompt_description', 'TEXT')
        _insert_default_prompts(conn)
    
    # Removed explicit commit call as the context manager handles this