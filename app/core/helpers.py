import os
import time
import re
import numpy as np
from scipy.stats import entropy
from collections import Counter
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
    Returns a dictionary mapping column name to table name.
    """
    # Regex to find patterns like: WHERE column_name = 'string' OR WHERE column_name LIKE 'string%'
    where_clause_pattern = re.compile(r"WHERE\s+`?(\w+)`?\s*(?:=|LIKE)\s*'([^']+)'", re.IGNORECASE)
    
    candidates = {}
    
    if not qa_pairs:
        return candidates

    for qa in qa_pairs:
        # qa_pairs from cursor.fetchall() is a list of tuples: (question, sql_query, table_name)
        if len(qa) < 3:
            continue
        sql = qa[1]
        table_name = qa[2] if qa[2] else 'global' # Use 'global' if table_name is not specified
        if not sql:
            continue
            
        matches = where_clause_pattern.findall(sql)
        for column, value in matches:
            # Basic heuristic for serial numbers: contains both digits and letters, and is between 4 and 40 chars long.
            if re.search(r"\d", value) and re.search(r"[a-zA-Z]", value) and 4 < len(value) < 40:
                # We found a potential candidate. Map the column to its table.
                # If a column is found multiple times, this will just overwrite, which is fine.
                candidates[column] = table_name
    
    return candidates

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
def extract_column_features(values: list = None, db_path: str = None, table_name: str = None, column_name: str = None, sample_size: int = 1000) -> dict:
    """
    Extracts detailed statistical features from a list of values or a database column.
    """
    if values:
        samples = values
    elif db_path and table_name and column_name:
        samples = sample_column_data(db_path, table_name, column_name, sample_size)
    else:
        samples = []

    if not samples:
        return {
            "total_samples": 0,
            "unique_count": 0,
            "null_count": "N/A", # Assuming sample_column_data filters out nulls
            "length_distribution": {},
            "character_composition": {}
        }

    # Convert all samples to string for consistent analysis
    samples = [str(s) for s in samples]
    
    # Basic counts
    total_samples = len(samples)
    unique_count = len(set(samples))
    
    # Length distribution
    lengths = [len(s) for s in samples]
    length_dist = {
        "min": int(np.min(lengths)) if lengths else 0,
        "max": int(np.max(lengths)) if lengths else 0,
        "mode": int(Counter(lengths).most_common(1)[0][0]) if lengths else 0,
        "median": int(np.median(lengths)) if lengths else 0,
        "std_dev": float(np.std(lengths)) if lengths else 0.0
    }
    
    # Character composition
    full_text = "".join(samples)
    total_chars = len(full_text)
    alpha_count = sum(c.isalpha() for c in full_text)
    digit_count = sum(c.isdigit() for c in full_text)
    symbol_count = total_chars - alpha_count - digit_count
    
    char_comp = {
        "alpha_ratio": round(alpha_count / total_chars, 2) if total_chars > 0 else 0,
        "digit_ratio": round(digit_count / total_chars, 2) if total_chars > 0 else 0,
        "symbol_ratio": round(symbol_count / total_chars, 2) if total_chars > 0 else 0,
    }

    # Positional analysis (entropy)
    positional_analysis = []
    if samples:
        max_len = length_dist['max']
        for i in range(max_len):
            chars_at_pos = [s[i] for s in samples if len(s) > i]
            if chars_at_pos:
                # Calculate entropy
                counts = Counter(chars_at_pos)
                probabilities = [count / len(chars_at_pos) for count in counts.values()]
                pos_entropy = entropy(probabilities, base=2)
                
                # Determine dominant type
                pos_types = Counter([
                    'letter' if c.isalpha() else 'digit' if c.isdigit() else 'symbol'
                    for c in chars_at_pos
                ])
                dominant_type = pos_types.most_common(1)[0][0]

                positional_analysis.append({
                    "pos": i,
                    "type": dominant_type,
                    "entropy": round(pos_entropy, 2)
                })
    char_comp["position_analysis"] = positional_analysis

    return {
        "total_samples": total_samples,
        "unique_count": unique_count,
        "null_count": 0, # sample_column_data filters nulls
        "length_distribution": length_dist,
        "character_composition": char_comp
    }