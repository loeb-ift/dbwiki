import os
import time
from sqlalchemy import create_engine, inspect, text

from .db_utils import get_user_db_connection

def load_prompt_template(filename):
    # This function has a dependency on the session, which might be problematic
    # in a refactored structure. We will address this when creating blueprints.
    try:
        from flask import session
        from app import app as flask_app
        with flask_app.app_context():
            if 'username' in session:
                user_id = session['username']
                with get_user_db_connection(user_id) as conn:
                    cursor = conn.cursor()
                    prompt_name = os.path.splitext(filename)[0]
                    cursor.execute(
                        "SELECT prompt_content FROM training_prompts WHERE prompt_name = ? AND is_global = 0", 
                        (prompt_name,)
                    )
                    result = cursor.fetchone()
                    if result:
                        flask_app.logger.info(f"Loaded custom prompt template '{filename}' from user database for user '{user_id}'")
                        return result[0]
                    cursor.execute(
                        "SELECT prompt_content FROM training_prompts WHERE prompt_name = ? AND is_global = 1", 
                        (prompt_name,)
                    )
                    result = cursor.fetchone()
                    if result:
                        flask_app.logger.info(f"Loaded global prompt template '{filename}' from user database for user '{user_id}'")
                        return result[0]
    except Exception as e:
        try:
            from app import app as flask_app
            with flask_app.app_context():
                flask_app.logger.warning(f"Failed to load prompt template from database: {e}")
        except (ImportError, RuntimeError):
            print(f"Failed to load prompt template from database: {e}")
    
    path = os.path.join('prompts', filename)
    
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            try:
                from app import app as flask_app
                with flask_app.app_context():
                    flask_app.logger.info(f"Loaded prompt template '{filename}' from file system")
            except (ImportError, RuntimeError):
                print(f"Loaded prompt template '{filename}' from file system")
            return f.read()
    else:
        raise FileNotFoundError(f"Prompt template file not found in 'prompts/': {filename}")

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

def _get_all_ask_logs(user_id: str) -> dict:
    log_dir = os.path.join(os.getcwd(), 'ask_log')
    if not os.path.exists(log_dir):
        return {}

    all_logs = {}
    for filename in os.listdir(log_dir):
        if filename.startswith(f"{user_id}_") and filename.endswith(".log"):
            # 正确解析文件名，提取日志类型
            # 文件名格式: {user_id}_{log_type}_{timestamp}.log
            # 使用正则表达式匹配而不是简单的split
            import re
            # 修改正则表达式以支持log_type中包含下划线
            pattern = r"^{}_(.+?)_\d+\.log$".format(user_id)
            match = re.match(pattern, filename)
            if match:
                log_type = match.group(1)
                
                file_path = os.path.join(log_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        all_logs.setdefault(log_type, []).append(content)
                except Exception as e:
                    try:
                        from app import app as flask_app
                        with flask_app.app_context():
                            flask_app.logger.error(f"Error reading log file {filename}: {e}")
                    except (ImportError, RuntimeError):
                        print(f"Error reading log file {filename}: {e}")
    
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
        table_names = inspector.get_table_names()
        
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