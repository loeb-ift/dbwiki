import sqlite3
import os

# 初始化训练数据库
def init_training_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建表结构
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS training_ddl (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ddl TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tags TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS training_documentation (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_name TEXT,
        documentation TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tags TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS training_qa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT,
        answer TEXT,
        sql TEXT,
        tags TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS training_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        example_type TEXT,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

# 添加列（如果不存在）
def add_column_if_not_exists(db_path, table_name, column_name, column_type):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查表是否有该列
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [column[1] for column in cursor.fetchall()]
    
    # 如果没有该列，则添加
    if column_name not in columns:
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            conn.commit()
        except Exception as e:
            print(f"Error adding column {column_name} to {table_name}: {e}")
    
    conn.close()

# 连接用户数据库
def connect_user_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建用户表（如果不存在）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    return conn

# 获取用户数据库路径
# These functions are deprecated and moved to app.core.db_utils
# def get_user_db_path(user_id: str) -> str:
#     ...
# def get_user_db_connection(user_id: str) -> sqlite3.Connection:
#     ...

# 获取数据集表列表
def get_dataset_tables(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [table[0] for table in cursor.fetchall() if table[0] != 'sqlite_sequence']
    return tables

# 检查提示词类型是否存在
def check_prompt_type_exists(conn, prompt_type):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM training_examples WHERE example_type = ?", (prompt_type,))
    return cursor.fetchone()[0] > 0

# 插入提示词类型
def insert_prompt_type(conn, prompt_type, content):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO training_examples (example_type, content) VALUES (?, ?)", (prompt_type, content))
    conn.commit()