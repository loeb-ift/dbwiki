import os
import sys
import sqlite3
import uuid
import json
import re
import time
import tempfile
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.inspection import inspect
from sqlalchemy.exc import DatabaseError, OperationalError
from functools import wraps
from flask import jsonify, Response, stream_with_context, session

# Import from local modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import create_app
from app.models import init_training_db, add_column_if_not_exists, connect_user_db, get_dataset_tables, check_prompt_type_exists, insert_prompt_type, get_user_db_connection, get_user_db_path
from app.utils import load_prompt_template, write_log, read_log, delete_log, df_to_json, extract_similar_qa_details, save_temp_file, generate_unique_id
from app.vanna_wrapper import configure_vanna_for_request

import threading
import queue
import logging

logger = logging.getLogger(__name__)

# 登录装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'error': 'Login required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# API登录装饰器
def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'error': 'Login required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# 管理员装饰器
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or not session.get('is_admin', False):
            return jsonify({'error': 'Admin required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Helper function to ensure dataset is properly loaded and accessible
def ensure_dataset_loaded(dataset_id):
    """确保数据集已正确加载并可访问"""
    user_id = session['username']
    
    # 检查数据集是否存在并获取数据库路径
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (int(dataset_id),))
        row = cursor.fetchone()
        if not row:
            return None, "Dataset not found"
        db_path = row[0]
    
    # 验证数据库文件存在
    if not os.path.exists(db_path):
        return None, f"Database file not found at {db_path}"
    
    try:
        # 获取数据库中的所有表
        engine = create_engine(f'sqlite:///{db_path}')
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        
        # 获取每个表的DDL语句
        ddl_statements = []
        with engine.connect() as connection:
            for name in table_names:
                ddl = connection.execute(text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{name}';")).scalar()
                if ddl: 
                    ddl_statements.append(ddl + ";")
        
        return {
            'db_path': db_path,
            'table_names': table_names,
            'ddl_statements': ddl_statements,
            'dataset_id': dataset_id
        }, None
    except Exception as e:
        return None, str(e)

# 创建Flask应用实例
app = create_app()





# 注意：所有路由定义已经移到相应的blueprint文件中
# 这个文件现在只包含辅助函数和应用初始化逻辑