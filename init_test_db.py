#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化和演示数据导入脚本
用于创建用户数据库表结构并导入示例数据集
"""
import os
import sys
import logging
import sqlite3
from sqlalchemy import create_engine, text

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('db_init')

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from app.core.db_utils import get_user_db_path, get_user_db_connection, init_training_db
    from app.core.helpers import get_dataset_tables
    MODULES_LOADED = True
except ImportError as e:
    logger.error(f"无法导入必要的模块: {e}")
    MODULES_LOADED = False

def init_test_user_db(user_id='test_user'):
    """初始化测试用户数据库"""
    logger.info(f"开始初始化测试用户数据库 - 用户ID: {user_id}")
    
    try:
        # 初始化训练数据库
        if MODULES_LOADED:
            logger.info("调用系统初始化函数...")
            init_training_db(user_id)
        else:
            # 如果无法导入模块，手动创建必要的表
            logger.info("手动创建必要的表结构...")
            db_path = os.path.join('user_data', f'training_data_{user_id}.sqlite')
            os.makedirs('user_data', exist_ok=True)
            
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                # 创建datasets表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS datasets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dataset_name TEXT NOT NULL,
                        db_path TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                
                # 创建其他必要的表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS training_ddl (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ddl_statement TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS training_documentation (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        documentation_text TEXT NOT NULL,
                        table_name TEXT,
                        dataset_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(dataset_id, table_name)
                    );
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS training_qa (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question TEXT NOT NULL,
                        sql_query TEXT NOT NULL,
                        table_name TEXT,
                        dataset_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                
                conn.commit()
        
        logger.info("测试用户数据库初始化成功")
        return True
    except Exception as e:
        logger.error(f"测试用户数据库初始化失败: {e}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return False

def create_sample_dataset(user_id='test_user', dataset_name='示例产品数据集'):
    """创建示例数据集"""
    logger.info(f"创建示例数据集 - 用户ID: {user_id}, 数据集名称: {dataset_name}")
    
    try:
        # 创建示例数据集文件
        dataset_dir = os.path.join('user_data', 'datasets', user_id)
        os.makedirs(dataset_dir, exist_ok=True)
        dataset_path = os.path.join(dataset_dir, f'{dataset_name.replace(" ", "_")}.sqlite')
        
        # 创建示例数据库和表
        logger.info(f"创建示例数据库文件: {dataset_path}")
        engine = create_engine(f'sqlite:///{dataset_path}')
        
        with engine.connect() as connection:
            # 创建产品表
            connection.execute(text('''
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    price REAL NOT NULL,
                    stock INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            '''))
            
            # 插入示例数据
            connection.execute(text('''
                INSERT INTO products (name, category, price, stock) VALUES
                ('智能手机A', '电子产品', 2999.99, 100),
                ('笔记本电脑B', '电子产品', 5999.99, 50),
                ('平板电脑C', '电子产品', 1999.99, 75),
                ('无线耳机D', '配件', 899.99, 200),
                ('智能手表E', '配件', 1299.99, 150);
            '''))
            
            # 创建订单表
            connection.execute(text('''
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    customer_name TEXT NOT NULL,
                    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_amount REAL NOT NULL
                );
            '''))
            
            # 插入示例订单数据
            connection.execute(text('''
                INSERT INTO orders (order_number, customer_name, total_amount) VALUES
                ('ORD-2024-001', '张三', 3899.98),
                ('ORD-2024-002', '李四', 5999.99),
                ('ORD-2024-003', '王五', 1299.99);
            '''))
            
            connection.commit()
        
        # 将数据集信息添加到用户数据库
        logger.info("将数据集信息添加到用户数据库...")
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO datasets (dataset_name, db_path) VALUES (?, ?)",
                (dataset_name, dataset_path)
            )
            dataset_id = cursor.lastrowid
            conn.commit()
        
        logger.info(f"示例数据集创建成功 - 数据集ID: {dataset_id}")
        return dataset_id
    except Exception as e:
        logger.error(f"示例数据集创建失败: {e}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return None

def verify_dataset(user_id='test_user', dataset_id=None):
    """验证数据集是否可以正确访问"""
    logger.info(f"验证数据集 - 用户ID: {user_id}, 数据集ID: {dataset_id}")
    
    try:
        # 如果没有提供数据集ID，获取第一个数据集
        if dataset_id is None:
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM datasets LIMIT 1")
                row = cursor.fetchone()
                if not row:
                    logger.error("没有找到任何数据集")
                    return False
                dataset_id = row[0]
                logger.info(f"使用数据集ID: {dataset_id}")
        
        # 测试获取数据集表信息
        if MODULES_LOADED:
            tables_info, error = get_dataset_tables(user_id, dataset_id)
            if error:
                logger.error(f"获取表信息失败: {error}")
            else:
                logger.info(f"获取表信息成功，找到 {len(tables_info['table_names'])} 个表")
                logger.info(f"表名列表: {tables_info['table_names']}")
                logger.info("DDL语句预览:")
                for i, ddl in enumerate(tables_info['ddl_statements'][:3]):  # 只显示前3个DDL
                    logger.info(f"表 {i+1}: {ddl[:100]}...")
        
        # 直接连接数据集验证
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
            row = cursor.fetchone()
            if not row:
                logger.error(f"找不到数据集ID: {dataset_id}")
                return False
            
            db_path = row[0]
            logger.info(f"直接连接到数据集: {db_path}")
            
            # 检查文件是否存在
            if not os.path.exists(db_path):
                logger.error(f"数据集文件不存在: {db_path}")
                return False
            
            # 连接数据集并查询
            engine = create_engine(f'sqlite:///{db_path}')
            with engine.connect() as connection:
                # 查询表列表
                result = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
                tables = [row[0] for row in result.fetchall()]
                logger.info(f"数据集包含的表: {tables}")
                
                # 查询第一个表的数据
                if tables:
                    first_table = tables[0]
                    result = connection.execute(text(f"SELECT COUNT(*) FROM {first_table}"))
                    count = result.scalar()
                    logger.info(f"表 {first_table} 包含 {count} 行数据")
                    
                    # 查询前几行数据
                    result = connection.execute(text(f"SELECT * FROM {first_table} LIMIT 3"))
                    rows = result.fetchall()
                    logger.info(f"表 {first_table} 的前3行数据:")
                    logger.info(f"列名: {result.keys()}")
                    for i, row_data in enumerate(rows):
                        logger.info(f"行 {i+1}: {row_data}")
        
        logger.info("数据集验证成功")
        return True
    except Exception as e:
        logger.error(f"数据集验证失败: {e}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return False

def main():
    """主函数"""
    logger.info("数据库初始化和示例数据集创建工具")
    logger.info("===================================")
    
    # 环境信息
    logger.info(f"当前工作目录: {os.getcwd()}")
    logger.info(f"Python版本: {sys.version}")
    
    # 初始化测试用户数据库
    test_user_id = 'test_user'
    
    # 步骤1: 初始化用户数据库
    init_success = init_test_user_db(test_user_id)
    if not init_success:
        logger.error("用户数据库初始化失败，无法继续")
        return
    
    # 步骤2: 创建示例数据集
    dataset_id = create_sample_dataset(test_user_id)
    if dataset_id is None:
        logger.error("示例数据集创建失败，无法继续")
        return
    
    # 步骤3: 验证数据集
    verify_success = verify_dataset(test_user_id, dataset_id)
    
    logger.info("===================================")
    
    if verify_success:
        logger.info("\n数据库初始化和示例数据集创建成功！")
        logger.info(f"测试用户ID: {test_user_id}")
        logger.info(f"示例数据集ID: {dataset_id}")
        logger.info("\n请使用以下信息测试系统功能:")
        logger.info("1. 用户ID: test_user")
        logger.info("2. 数据集ID: 1 (或查看日志中的实际ID)")
        logger.info("3. 可尝试的查询问题示例:")
        logger.info("   - 显示所有产品信息")
        logger.info("   - 查询价格高于1000的产品")
        logger.info("   - 统计每个类别的产品数量")
        logger.info("   - 显示所有订单信息")
    else:
        logger.error("\n数据库初始化和示例数据集创建失败！")
        logger.error("请查看日志了解详细信息")

if __name__ == "__main__":
    main()