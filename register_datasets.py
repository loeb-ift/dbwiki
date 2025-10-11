#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sqlite3
import time
import re

"""该脚本用于将user_data/datasets目录下的所有SQLite数据库文件注册到用户数据库的datasets表中"""

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 用户数据目录
USER_DATA_DIR = os.path.join(PROJECT_ROOT, 'user_data')

# 数据集目录
DATASETS_DIR = os.path.join(USER_DATA_DIR, 'datasets')

# 用户数据库文件路径
USER_DB_PATH = os.path.join(USER_DATA_DIR, 'training_data_user1.sqlite')


def is_sqlite_db(file_path):
    """检查文件是否为SQLite数据库文件"""
    try:
        # 尝试打开文件连接
        conn = sqlite3.connect(file_path)
        cursor = conn.cursor()
        # 尝试执行一个简单的SQL查询
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        conn.close()
        return True
    except Exception:
        return False


def register_datasets():
    """将datasets目录下的所有SQLite数据库文件注册到用户数据库的datasets表中"""
    # 确保数据集目录存在
    if not os.path.exists(DATASETS_DIR):
        print(f"数据集目录 {DATASETS_DIR} 不存在")
        return

    # 确保用户数据库文件存在
    if not os.path.exists(USER_DB_PATH):
        print(f"用户数据库文件 {USER_DB_PATH} 不存在")
        return

    try:
        # 连接用户数据库
        user_conn = sqlite3.connect(USER_DB_PATH)
        user_cursor = user_conn.cursor()

        # 获取已注册的数据集路径
        user_cursor.execute("SELECT db_path FROM datasets")
        registered_paths = {row[0] for row in user_cursor.fetchall()}

        # 遍历数据集目录下的所有文件
        for filename in os.listdir(DATASETS_DIR):
            file_path = os.path.join(DATASETS_DIR, filename)
            
            # 跳过目录
            if os.path.isdir(file_path):
                continue
            
            # 只处理SQLite数据库文件
            if filename.endswith('.sqlite') and is_sqlite_db(file_path):
                # 确保路径是相对路径（相对于项目根目录）
                relative_path = os.path.relpath(file_path, PROJECT_ROOT)
                
                # 如果该数据集尚未注册
                if relative_path not in registered_paths:
                    # 从文件名生成数据集名称（去掉扩展名，将下划线替换为空格，首字母大写）
                    dataset_name = re.sub(r'[^a-zA-Z0-9_]', '_', filename.replace('.sqlite', ''))
                    dataset_name = dataset_name.replace('_', ' ').title()
                    
                    # 如果数据集名称太长，进行截断
                    if len(dataset_name) > 100:
                        dataset_name = dataset_name[:97] + '...'
                    
                    # 获取当前时间戳
                    timestamp = int(time.time())
                    
                    # 将数据集注册到用户数据库
                    user_cursor.execute(
                        "INSERT INTO datasets (dataset_name, db_path, created_at) VALUES (?, ?, ?)",
                        (dataset_name, relative_path, timestamp)
                    )
                    
                    print(f"已注册数据集: {dataset_name} ({file_path})")
                    registered_paths.add(relative_path)
                else:
                    print(f"数据集已注册: {file_path}")

        # 提交更改
        user_conn.commit()
        
        # 关闭连接
        user_cursor.close()
        user_conn.close()
        
        print("所有数据集注册完成")
        
    except Exception as e:
        print(f"注册数据集时出错: {e}")


if __name__ == '__main__':
    register_datasets()