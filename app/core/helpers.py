import os
import time
import re
from sqlalchemy import create_engine, inspect, text

from .db_utils import get_user_db_connection

def load_prompt_template(prompt_type: str, user_id: str = None):
    """
    Loads a prompt template from the database. If not found, it attempts to
    insert the default prompt and then retries.
    """
    from flask import session
    from app import app as flask_app
    from app.blueprints.prompts import get_default_prompt_content

    if user_id is None:
        user_id = session.get('username', 'system') # Fallback to a system-level user

    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Attempt to load the prompt
            cursor.execute(
                "SELECT prompt_content FROM training_prompts WHERE prompt_type = ? ORDER BY is_global ASC",
                (prompt_type,)
            )
            result = cursor.fetchone()

            if result:
                return result[0]

            # If not found, try to insert the default and reload
            flask_app.logger.warning(f"Prompt '{prompt_type}' not found for user '{user_id}'. Attempting to insert default.")
            
            default_content = get_default_prompt_content(prompt_type)
            if not default_content:
                raise FileNotFoundError(f"Default prompt for '{prompt_type}' not found in JSON file.")

            try:
                prompt_name = f"{prompt_type}_prompt"
                description = "Default prompt inserted on-demand."
                cursor.execute(
                    "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, prompt_description, is_global) VALUES (?, ?, ?, ?, ?)",
                    (prompt_name, default_content, prompt_type, description, 1)
                )
                conn.commit()
                flask_app.logger.info(f"Inserted default prompt for '{prompt_type}'.")
                return default_content
            except conn.IntegrityError:
                # Race condition: another thread inserted it. Retry loading.
                flask_app.logger.info(f"Default prompt for '{prompt_type}' was inserted by another process. Retrying load.")
                cursor.execute(
                    "SELECT prompt_content FROM training_prompts WHERE prompt_type = ? AND is_global = 1",
                    (prompt_type,)
                )
                result = cursor.fetchone()
                if result:
                    return result[0]
                raise
    except Exception as e:
        flask_app.logger.error(f"Error in load_prompt_template for '{prompt_type}': {e}", exc_info=True)
        raise

    raise FileNotFoundError(f"Unable to load or create prompt of type '{prompt_type}'.")

# The insert_default_prompt function is now obsolete and has been removed.
# The new load_prompt_template function handles on-demand prompt creation.

def write_ask_log(user_id: str, log_type: str, content: str):
    log_dir = os.path.join(os.getcwd(), 'ask_log')
    os.makedirs(log_dir, exist_ok=True)
    timestamp = int(time.time())
    file_path = os.path.join(log_dir, f"{user_id}_{log_type}_{timestamp}.log")
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"{content}\n")
    
    # 使用应用上下文来记录日志，避免在后台线程中出现问题
    try:
        from app import app as flask_app
        with flask_app.app_context():
            flask_app.logger.info(f"Ask log written to: {file_path}")
    except (ImportError, RuntimeError):
        # 如果创建上下文失败，至少确保文件已经写入
        print(f"Ask log written to: {file_path}")

# This function is deprecated after refactoring the dynamic prompt generation in ask.py
# def _get_all_ask_logs(user_id: str) -> dict:
#     ...

def _delete_all_ask_logs(user_id: str):
    log_dir = os.path.join(os.getcwd(), 'ask_log')
    if not os.path.exists(log_dir):
        return

    for filename in os.listdir(log_dir):
        if filename.startswith(f"{user_id}_") and filename.endswith(".log"):
            file_path = os.path.join(log_dir, filename)
            try:
                os.remove(file_path)
                try:
                    from app import app as flask_app
                    with flask_app.app_context():
                        flask_app.logger.info(f"Removed log file: {filename}")
                except (ImportError, RuntimeError):
                    print(f"Removed log file: {filename}")
            except Exception as e:
                try:
                    from app import app as flask_app
                    with flask_app.app_context():
                        flask_app.logger.error(f"Error removing log file {filename}: {e}")
                except (ImportError, RuntimeError):
                    print(f"Error removing log file {filename}: {e}")

def get_dataset_tables(user_id, dataset_id):
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
        if not row:
            return None, "Dataset not found"
        db_path = row[0]
    
    try:
        engine = create_engine(f'sqlite:///{db_path}')
        inspector = inspect(engine)
        # 确保返回的是标准Python列表
        table_names = list(inspector.get_table_names())
        
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

def extract_serial_number_candidates(qa_pairs: list) -> dict:
    """
    Analyzes a list of QA pairs to find potential serial number columns.
    It looks for WHERE clauses with string literals that have a mix of letters and numbers.
    """
    # Regex to find patterns like: WHERE column_name = 'string' OR WHERE column_name LIKE 'string%'
    where_clause_pattern = re.compile(r"WHERE\s+`?(\w+)`?\s*(?:=|LIKE)\s*'([^']+)'", re.IGNORECASE)
    
    candidates = {}
    
    if not qa_pairs:
        return candidates

    for qa in qa_pairs:
        # qa_pairs from cursor.fetchall() is a list of tuples, not dicts.
        # Access by index. Assuming the SQL query is the second element (index 1).
        if len(qa) < 2:
            continue
        sql = qa[1]
        if not sql:
            continue
            
        matches = where_clause_pattern.findall(sql)
        for column, value in matches:
            # Basic heuristic for serial numbers: contains both digits and letters, and is between 4 and 40 chars long.
            if re.search(r"\d", value) and re.search(r"[a-zA-Z]", value) and 4 < len(value) < 40:
                if column not in candidates:
                    candidates[column] = []
                if value not in candidates[column]:
                    candidates[column].append(value)
    
    # Return only candidates that have at least a few examples
    return {col: values for col, values in candidates.items() if len(values) >= 3}

def sample_column_data(db_path: str, table_name: str, column_name: str, sample_size: int = 100) -> list:
    """
    Connects to a SQLite database and samples data from a specific column.
    """
    samples = []
    try:
        engine = create_engine(f'sqlite:///{db_path}')
        with engine.connect() as connection:
            # Use `"` for table and column names to handle spaces or special characters
            query = text(f'SELECT DISTINCT "{column_name}" FROM "{table_name}" ORDER BY RANDOM() LIMIT {sample_size}')
            result = connection.execute(query)
            samples = [row[0] for row in result if row[0] is not None]
    except Exception as e:
        # In a real app, you'd want to log this error
        print(f"Error sampling column {table_name}.{column_name}: {e}")
    
    return samples