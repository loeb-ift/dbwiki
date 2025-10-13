#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接诊断数据集上传功能的脚本
这个脚本避免使用Flask测试客户端，直接模拟请求对象并调用处理函数
"""
import os
import sys
import json
import logging
from datetime import datetime
from io import BytesIO
import pandas as pd
from werkzeug.datastructures import FileStorage

# 添加项目根目录到Python路径
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# 配置详细的日志记录
log_file = 'direct_dataset_upload_diagnostic.log'
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 模拟Flask请求和会话对象
class MockRequest:
    def __init__(self, method='POST', files=None, args=None, form=None, json=None):
        self.method = method
        self.files = files or {}
        self.args = args or {}
        self.form = form or {}
        self.json = json
    
    def get_json(self):
        return self.json
    
    def getlist(self, key):
        if key in self.files:
            return [self.files[key]] if not isinstance(self.files[key], list) else self.files[key]
        return []

class MockSession:
    def __init__(self):
        self.data = {}
    
    def __getitem__(self, key):
        return self.data[key]
    
    def __setitem__(self, key, value):
        self.data[key] = value

# 创建模拟CSV文件
def create_mock_csv():
    df = pd.DataFrame({
        'id': [1, 2, 3],
        'name': ['测试数据1', '测试数据2', '测试数据3'],
        'value': [100, 200, 300]
    })
    
    csv_buffer = BytesIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8')
    csv_buffer.seek(0)
    
    return csv_buffer, df

# 直接测试文件上传函数
def test_direct_file_upload(user_id="user1"):
    try:
        logger.info(f"开始直接测试文件上传功能 (用户: {user_id})...")
        
        # 动态导入应用模块，这样可以捕获导入错误
        logger.info("尝试导入应用模块...")
        try:
            # 导入实际存在的模块
            from app.core.db_utils import get_user_db_connection
            logger.info("成功导入应用模块")
        except ImportError as e:
            logger.error(f"导入应用模块失败: {str(e)}")
            logger.error("请检查项目依赖和Python路径配置")
            return False
        
        # 创建模拟CSV文件
        csv_buffer, df = create_mock_csv()
        logger.info(f"创建了包含 {len(df)} 行的模拟CSV文件")
        
        # 准备数据集名称
        dataset_name = f"direct_test_dataset_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 直接测试数据处理流程
        try:
            # 检查用户数据库连接
            logger.info(f"检查用户 '{user_id}' 的数据库连接...")
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                
                # 检查datasets表是否存在并获取记录数
                cursor.execute("SELECT COUNT(*) FROM datasets")
                count = cursor.fetchone()[0]
                logger.info(f"用户 '{user_id}' 有 {count} 个现有数据集")
                
                # 直接创建测试数据集记录
                test_db_path = os.path.join('user_data', 'datasets', f'{dataset_name}.sqlite')
                cursor.execute("INSERT INTO datasets (dataset_name, db_path) VALUES (?, ?)", 
                              (dataset_name, test_db_path))
                dataset_id = cursor.lastrowid
                conn.commit()
                logger.info(f"成功创建测试数据集，ID: {dataset_id}")
                
                # 尝试写入CSV数据到SQLite
                try:
                    engine = create_engine(f'sqlite:///{test_db_path}')
                    df.to_sql('data_table', engine, index=False, if_exists='replace')
                    logger.info("成功将测试数据写入SQLite数据库")
                    
                    # 验证数据是否写入成功
                    with engine.connect() as connection:
                        result = connection.execute(text("SELECT COUNT(*) FROM data_table"))
                        row_count = result.scalar()
                        logger.info(f"数据表中的记录数量: {row_count}")
                except Exception as e:
                    logger.error(f"数据写入失败: {type(e).__name__}: {str(e)}")
                    
                # 清理测试数据
                if os.path.exists(test_db_path):
                    os.remove(test_db_path)
                    logger.info(f"已删除测试数据库文件")
                
                cursor.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
                conn.commit()
                logger.info(f"已从数据库移除测试数据集记录")
                
            return True
        except Exception as e:
            logger.error(f"文件处理过程中出现异常: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            return False
    except Exception as e:
        logger.error(f"测试过程中出现意外异常: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return False

# 测试直接API函数调用
def test_api_function_directly(user_id="user1"):
    try:
        logger.info(f"开始直接测试API函数 (用户: {user_id})...")
        
        # 导入API相关函数
        from app.blueprints.datasets import create_dataset_endpoint
        
        # 创建模拟CSV文件
        csv_buffer, df = create_mock_csv()
        csv_buffer.seek(0)
        
        # 创建FileStorage对象
        mock_file = FileStorage(
            stream=csv_buffer,
            filename='test_data.csv',
            name='files',
            content_type='text/csv'
        )
        
        # 创建模拟请求和会话
        dataset_name = f"api_test_dataset_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        mock_request = MockRequest(
            method='POST',
            files={'files': mock_file},
            form={'dataset_name': dataset_name}
        )
        
        mock_session = MockSession()
        mock_session['username'] = user_id
        
        # 直接调用API端点函数
        logger.info(f"直接调用create_dataset_endpoint函数...")
        try:
            # 由于这是Flask视图函数，我们需要模拟响应对象
            response = create_dataset_endpoint(mock_request, mock_session)
            logger.info(f"API函数调用返回: {response}")
            return True
        except Exception as e:
            logger.error(f"API函数调用异常: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    except Exception as e:
        logger.error(f"API函数测试异常: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# 运行诊断测试
def run_diagnostics():
    logger.info("=== 开始数据集上传诊断测试 ===")
    
    # 测试1：直接调用文件处理函数
    logger.info("\n--- 测试1: 直接调用文件处理函数 ---")
    file_upload_success = test_direct_file_upload("user1")
    
    # 测试2：检查目录权限
    logger.info("\n--- 测试2: 检查目录权限 ---")
    check_directory_permissions()
    
    # 测试3：检查用户数据表结构
    logger.info("\n--- 测试3: 检查用户数据表结构 ---")
    check_user_database_structure("user1")
    
    logger.info("\n=== 诊断测试完成，请查看日志文件获取详细信息 ===")
    
    return file_upload_success

# 检查目录权限
def check_directory_permissions():
    try:
        # 检查用户数据集目录
        user_data_dir = os.path.join('user_data', 'datasets')
        
        # 检查目录是否存在
        if not os.path.exists(user_data_dir):
            logger.info(f"目录 '{user_data_dir}' 不存在，尝试创建...")
            os.makedirs(user_data_dir, exist_ok=True)
            logger.info(f"成功创建目录 '{user_data_dir}'")
        
        # 检查权限
        is_writable = os.access(user_data_dir, os.W_OK)
        logger.info(f"目录 '{user_data_dir}' 是否可写: {is_writable}")
        
        # 尝试创建测试文件
        test_file = os.path.join(user_data_dir, 'permission_test.txt')
        try:
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('Permission test')
            logger.info(f"成功创建测试文件: {test_file}")
            
            # 测试读取权限
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"成功读取测试文件内容: {content}")
            
            os.remove(test_file)
            logger.info(f"成功删除测试文件")
        except Exception as e:
            logger.error(f"创建测试文件失败: {type(e).__name__}: {str(e)}")
            
    except Exception as e:
        logger.error(f"检查目录权限时出错: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")

# 检查用户数据库结构
def check_user_database_structure(user_id):
    try:
        from app.core.db_utils import get_user_db_connection
        
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # 检查datasets表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='datasets'")
            result = cursor.fetchone()
            
            if result:
                logger.info("datasets表存在")
                
                # 检查表结构
                cursor.execute("PRAGMA table_info(datasets)")
                columns = cursor.fetchall()
                logger.info(f"datasets表列: {[col[1] for col in columns]}")
                
                # 检查是否有id列（注意：这里应该是id而不是dataset_id）
                has_id = any(col[1] == 'id' for col in columns)
                logger.info(f"datasets表包含id列: {has_id}")
                
                # 显示表中的数据（如果有）
                cursor.execute("SELECT COUNT(*) FROM datasets")
                count = cursor.fetchone()[0]
                logger.info(f"datasets表中的记录数量: {count}")
                
                if count > 0:
                    cursor.execute("SELECT id, dataset_name FROM datasets LIMIT 3")
                    sample_data = cursor.fetchall()
                    logger.info(f"datasets表示例数据: {sample_data}")
                
            else:
                logger.error("datasets表不存在")
                
    except Exception as e:
        logger.error(f"检查数据库结构时出错: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")

if __name__ == "__main__":
    # 导入必要的额外模块
    from sqlalchemy import create_engine, text
    
    # 打印系统信息
    logger.info(f"当前工作目录: {os.getcwd()}")
    logger.info(f"Python版本: {sys.version}")
    logger.info(f"用户数据集目录: {os.path.abspath(os.path.join('user_data', 'datasets'))}")
    
    # 运行诊断测试
    success = run_diagnostics()
    
    if success:
        logger.info("\n===== 诊断测试成功完成 =====")
    else:
        logger.info("\n===== 诊断测试完成，但有失败项 =====")
    
    print(f"\n诊断测试完成，请查看日志文件: {log_file}")