#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库连接和模式信息测试脚本
用于验证系统是否能正确获取数据库模式信息和生成SQL查询
"""
import os
import sys
import logging
import sqlite3
from sqlalchemy import create_engine, inspect, text
import pandas as pd

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('db_connection_test')

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from app.core.db_utils import get_user_db_connection
    from app.core.helpers import get_dataset_tables
    from app.vanna_wrapper import get_vanna_instance
    from app.core.vanna_core import configure_vanna_for_request
    MODULES_LOADED = True
except ImportError as e:
    logger.error(f"无法导入必要的模块: {e}")
    MODULES_LOADED = False

def test_sql_generation(vn, test_questions):
    """测试SQL生成功能"""
    logger.info("\n测试SQL生成功能...")
    logger.info("================================")
    
    results = []
    
    for question in test_questions:
        try:
            logger.info(f"\n生成SQL查询 - 问题: {question}")
            
            # 生成SQL
            sql = vn.generate_sql(question)
            logger.info(f"生成的SQL: {sql}")
            
            # 执行SQL
            df = vn.run_sql(sql)
            logger.info(f"执行结果: {len(df)} 行数据")
            if not df.empty:
                logger.info(f"结果预览: {df.head(3).to_string()}")
            else:
                logger.info("查询结果为空")
            
            results.append({
                'question': question,
                'sql': sql,
                'success': not df.empty,
                'rows': len(df)
            })
            
        except Exception as e:
            logger.error(f"SQL生成或执行失败: {e}")
            results.append({
                'question': question,
                'error': str(e),
                'success': False
            })
    
    # 输出汇总结果
    logger.info("\nSQL生成测试汇总")
    logger.info("================================")
    success_count = sum(1 for r in results if r['success'])
    logger.info(f"总测试问题: {len(test_questions)}, 成功: {success_count}, 失败: {len(test_questions) - success_count}")
    
    return results

def test_db_connection():
    """测试数据库连接和模式信息获取"""
    try:
        # 使用默认的测试用户和数据集ID
        test_user_id = 'test_user'
        test_dataset_id = '1'  # 假设第一个数据集ID为1
        
        logger.info(f"开始测试数据库连接 - 用户ID: {test_user_id}, 数据集ID: {test_dataset_id}")
        
        # 1. 测试用户数据库连接
        logger.info("测试用户数据库连接...")
        try:
            with get_user_db_connection(test_user_id) as conn:
                logger.info("用户数据库连接成功")
                
                # 查询所有可用数据集
                cursor = conn.cursor()
                cursor.execute("SELECT id, dataset_name, db_path FROM datasets")
                datasets = cursor.fetchall()
                logger.info(f"找到 {len(datasets)} 个数据集")
                for dataset in datasets:
                    logger.info(f"数据集ID: {dataset[0]}, 名称: {dataset[1]}, 路径: {dataset[2]}")
                
                # 如果测试数据集不存在，使用第一个数据集
                if datasets and not any(d[0] == test_dataset_id for d in datasets):
                    test_dataset_id = datasets[0][0]
                    logger.info(f"切换到可用数据集ID: {test_dataset_id}")
        except Exception as e:
            logger.error(f"用户数据库连接失败: {e}")
            return False
        
        # 2. 测试获取数据集表信息
        logger.info(f"测试获取数据集表信息 - 数据集ID: {test_dataset_id}")
        try:
            tables_info, error = get_dataset_tables(test_user_id, test_dataset_id)
            if error:
                logger.error(f"获取表信息失败: {error}")
            else:
                logger.info(f"获取表信息成功，找到 {len(tables_info['table_names'])} 个表")
                logger.info(f"表名列表: {tables_info['table_names']}")
                logger.info("DDL语句预览:")
                for i, ddl in enumerate(tables_info['ddl_statements'][:3]):  # 只显示前3个DDL
                    logger.info(f"表 {i+1}: {ddl[:100]}...")
        except Exception as e:
            logger.error(f"获取表信息过程出错: {e}")
            return False
        
        # 3. 测试Vanna实例配置和SQL生成
        if MODULES_LOADED:
            logger.info("测试Vanna实例配置...")
            try:
                vn = get_vanna_instance(test_user_id)
                vn = configure_vanna_for_request(vn, test_user_id, test_dataset_id)
                logger.info("Vanna实例配置成功")
                
                # 测试获取相关DDL
                test_question = "显示所有产品信息"
                logger.info(f"测试获取相关DDL - 问题: {test_question}")
                related_ddl = vn.get_related_ddl(test_question)
                logger.info(f"获取到 {len(related_ddl)} 条相关DDL")
                for ddl in related_ddl:
                    logger.info(f"相关DDL: {ddl[:100]}...")
                
                # 测试简单查询
                test_sql = "SELECT name FROM sqlite_master WHERE type='table';"
                logger.info(f"执行测试SQL: {test_sql}")
                df = vn.run_sql(test_sql)
                logger.info(f"查询结果: {len(df)} 行")
                if not df.empty:
                    logger.info(f"表列表: {', '.join(df['name'].tolist())}")
                
                # 4. 测试SQL生成功能
                test_questions = [
                    "显示所有产品信息",
                    "查询价格高于1000的产品",
                    "统计每个类别的产品数量",
                    "显示所有订单信息"
                ]
                test_sql_generation(vn, test_questions)
                
            except Exception as e:
                logger.error(f"Vanna实例配置或操作失败: {e}")
                import traceback
                logger.error(f"错误堆栈: {traceback.format_exc()}")
        
        # 5. 直接测试数据库连接
        logger.info("直接测试数据库连接...")
        try:
            with get_user_db_connection(test_user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (test_dataset_id,))
                row = cursor.fetchone()
                if row:
                    db_path = row[0]
                    logger.info(f"直接连接到数据集: {db_path}")
                    engine = create_engine(f'sqlite:///{db_path}')
                    
                    # 测试表存在性
                    inspector = inspect(engine)
                    table_names = inspector.get_table_names()
                    logger.info(f"直接连接后找到的表: {table_names}")
                    
                    # 尝试查询第一个表的前几行
                    if table_names:
                        first_table = table_names[0]
                        test_query = f"SELECT * FROM {first_table} LIMIT 5"
                        logger.info(f"查询表 {first_table} 的前5行")
                        with engine.connect() as connection:
                            result = connection.execute(text(test_query))
                            rows = result.fetchall()
                            logger.info(f"查询返回 {len(rows)} 行数据")
                            if rows:
                                logger.info(f"列名: {result.keys()}")
                                logger.info(f"第一行数据: {rows[0]}")
        except Exception as e:
            logger.error(f"直接数据库连接测试失败: {e}")
        
        logger.info("数据库连接测试完成")
        return True
    except Exception as e:
        logger.error(f"测试过程发生未预期错误: {e}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return False

def main():
    """主函数"""
    logger.info("数据库连接和模式信息测试工具")
    logger.info("================================")
    
    # 环境信息
    logger.info(f"当前工作目录: {os.getcwd()}")
    logger.info(f"Python版本: {sys.version}")
    
    success = test_db_connection()
    
    if success:
        logger.info("测试成功完成！")
    else:
        logger.error("测试失败，请查看日志了解详细信息")
    
    logger.info("================================")
    
    # 提供修复建议
    if not success:
        logger.info("\n可能的解决方案：")
        logger.info("1. 确保已选择正确的数据集并激活")
        logger.info("2. 检查数据集文件是否存在且可访问")
        logger.info("3. 验证数据集包含表结构和数据")
        logger.info("4. 确认系统有足够权限读取数据集文件")
        logger.info("5. 尝试重新训练Vanna模型以加载模式信息")

if __name__ == "__main__":
    main()