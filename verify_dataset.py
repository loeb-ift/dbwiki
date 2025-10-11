#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库验证脚本 - 用于检查数据集连接和表内容

这个脚本可以帮助验证:
1. 数据集是否被正确引用
2. 数据集中的表结构是否正确
3. 表中是否包含实际数据
4. SQL查询是否能返回结果

用法:
python verify_dataset.py <user_id> <dataset_id>
"""
import os
import sys
import sqlite3
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 配置日志
def log_message(message, level="INFO"):
    """打印带时间戳的日志消息"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

def get_user_db_path(user_id):
    """获取用户数据库路径"""
    db_dir = os.path.join(os.getcwd(), 'user_data')
    return os.path.join(db_dir, f'training_data_{user_id}.sqlite')

def verify_dataset(user_id, dataset_id):
    """验证数据集连接和内容"""
    try:
        log_message(f"开始验证用户 {user_id} 的数据集 {dataset_id}")
        
        # 步骤1: 连接用户数据库，获取数据集路径
        user_db_path = get_user_db_path(user_id)
        log_message(f"用户数据库路径: {user_db_path}")
        
        if not os.path.exists(user_db_path):
            log_message(f"错误: 用户数据库不存在 - {user_db_path}", "ERROR")
            return False
        
        with sqlite3.connect(user_db_path) as user_conn:
            user_cursor = user_conn.cursor()
            
            # 查询数据集信息
            user_cursor.execute("SELECT id, dataset_name, db_path FROM datasets WHERE id = ?", (dataset_id,))
            dataset_row = user_cursor.fetchone()
            
            if not dataset_row:
                log_message(f"错误: 未找到ID为 {dataset_id} 的数据集", "ERROR")
                return False
            
            dataset_id_db, dataset_name, db_path = dataset_row
            log_message(f"找到数据集: {dataset_name} (ID: {dataset_id_db})")
            log_message(f"数据集路径: {db_path}")
            
            # 检查数据集文件是否存在
            if not os.path.exists(db_path):
                log_message(f"错误: 数据集文件不存在 - {db_path}", "ERROR")
                return False
        
        # 步骤2: 连接到数据集数据库，检查表结构和内容
        log_message("连接到数据集数据库...")
        engine = create_engine(f'sqlite:///{db_path}')
        
        # 获取表列表
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        
        if not table_names:
            log_message("警告: 数据集中没有表", "WARNING")
            return False
        
        log_message(f"数据集中的表数量: {len(table_names)}")
        log_message(f"表列表: {', '.join(table_names)}")
        
        # 步骤3: 检查每个表的结构和数据量
        has_data = False
        
        with engine.connect() as connection:
            for table_name in table_names:
                log_message(f"\n检查表: {table_name}")
                
                # 获取表结构
                columns = inspector.get_columns(table_name)
                log_message(f"表 {table_name} 的列数: {len(columns)}")
                log_message(f"列名: {', '.join([col['name'] for col in columns])}")
                
                # 获取表中的记录数
                count_sql = f"SELECT COUNT(*) FROM {table_name}"
                count_result = connection.execute(text(count_sql)).scalar()
                log_message(f"表 {table_name} 中的记录数: {count_result}")
                
                # 如果有记录，显示前几行数据作为示例
                if count_result > 0:
                    has_data = True
                    sample_sql = f"SELECT * FROM {table_name} LIMIT 3"
                    sample_df = pd.read_sql_query(sample_sql, connection)
                    log_message(f"表 {table_name} 的前3行数据:")
                    print(sample_df.to_string(index=False))
                else:
                    log_message(f"警告: 表 {table_name} 中没有数据", "WARNING")
        
        # 步骤4: 尝试执行一个简单的SQL查询，验证数据是否可访问
        if has_data and table_names:
            test_table = table_names[0]
            test_sql = f"SELECT * FROM {test_table} LIMIT 5"
            log_message(f"\n尝试执行测试查询: {test_sql}")
            
            try:
                test_df = pd.read_sql_query(test_sql, engine)
                log_message(f"测试查询成功，返回了 {len(test_df)} 行数据")
                if len(test_df) > 0:
                    log_message(f"测试查询结果预览:")
                    print(test_df.to_string(index=False))
            except Exception as e:
                log_message(f"错误: 测试查询执行失败 - {str(e)}", "ERROR")
        
        log_message("\n数据集验证完成!")
        if has_data:
            log_message("结论: 数据集被正确引用并且包含数据。SQL查询返回空结果可能是因为生成的SQL与数据结构不匹配或查询条件过于严格。", "INFO")
        else:
            log_message("结论: 数据集被正确引用，但所有表都为空。请检查数据集是否正确导入了数据。", "WARNING")
        
        return True
        
    except Exception as e:
        log_message(f"验证过程中发生错误: {str(e)}", "ERROR")
        return False

def main():
    """主函数，处理命令行参数"""
    if len(sys.argv) != 3:
        print("用法: python verify_dataset.py <user_id> <dataset_id>")
        sys.exit(1)
    
    user_id = sys.argv[1]
    dataset_id = sys.argv[2]
    
    # 确保dataset_id是整数
    try:
        dataset_id = int(dataset_id)
    except ValueError:
        log_message("错误: dataset_id必须是整数", "ERROR")
        sys.exit(1)
    
    verify_dataset(user_id, dataset_id)

if __name__ == "__main__":
    main()