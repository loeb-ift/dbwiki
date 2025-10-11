import sqlite3
import os
import logging

# 配置日志记录器
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def get_user_db_path(user_id: str) -> str:
    db_dir = os.path.join(os.getcwd(), 'user_data')
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, f'training_data_{user_id}.sqlite')

def get_user_db_connection(user_id: str) -> sqlite3.Connection:
    db_path = get_user_db_path(user_id)
    return sqlite3.connect(db_path)

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
            
            # This part depends on `load_prompt_template` which is in helpers.
            # We will address this dependency later.
            # For now, we comment it out to avoid circular imports.
            # try:
            #     base_prompt_types = [
            #         ('ask_analysis_prompt', '用於分析用戶問題和生成SQL的提示詞'),
            #         ('qa_generation_system_prompt', '用於從SQL生成問答配對的提示詞'),
            #         ('documentation_prompt', '用於生成數據庫文檔的提示詞')
            #     ]
                
            #     for prompt_name, prompt_desc in base_prompt_types:
            #         cursor.execute("SELECT COUNT(*) FROM training_prompts WHERE prompt_name = ?", (prompt_name,))
            #         if cursor.fetchone()[0] == 0:
            #             try:
            #                 from .helpers import load_prompt_template
            #                 prompt_content = load_prompt_template(f"{prompt_name}.txt")
            #                 cursor.execute(
            #                     "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, is_global) VALUES (?, ?, ?, ?)",
            #                     (prompt_name, prompt_content, prompt_desc, 1)
            #                 )
            #             except Exception as e:
            #                 app.logger.warning(f"Failed to load default prompt {prompt_name}: {e}")
            # except Exception as e:
            #     app.logger.warning(f"Failed to initialize base prompt types: {e}")
            
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Could not initialize/update training database for user '{user_id}': {e}")
        raise