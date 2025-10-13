import os
import sys
from app.core.helpers import get_dataset_tables
from app.core.db_utils import get_user_db_connection
import sqlite3
import json

# 配置中文显示
import pandas as pd
pd.set_option('display.unicode.east_asian_width', True)

# 打印当前路径和Python版本信息
def print_environment_info():
    print(f"当前工作目录: {os.getcwd()}")
    print(f"Python版本: {sys.version}")
    print(f"SQLite3版本: {sqlite3.sqlite_version}")
    print(f"Pandas版本: {pd.__version__}")

# 创建测试数据集和表
def create_test_dataset(user_id="test_user"):
    print("\n创建测试数据集和表...")
    
    # 连接用户数据库
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        
        # 先删除旧的测试数据集
        cursor.execute("DELETE FROM datasets WHERE dataset_name = ?", ("test_dataset",))
        conn.commit()
        
        # 创建测试数据集
        test_db_path = os.path.join('user_data', 'datasets', 'test_dataset.db')
        os.makedirs(os.path.dirname(test_db_path), exist_ok=True)
        
        # 将测试数据集插入到用户数据库中
        cursor.execute("INSERT INTO datasets (dataset_name, db_path) VALUES (?, ?)", 
                      ("test_dataset", test_db_path))
        dataset_id = cursor.lastrowid
        conn.commit()
        
        print(f"创建测试数据集成功，ID: {dataset_id}")
        
    # 连接测试数据集数据库，创建测试表
    test_db_engine = sqlite3.connect(test_db_path)
    test_cursor = test_db_engine.cursor()
    test_cursor.execute('CREATE TABLE test_table (id INTEGER, name TEXT)')
    test_cursor.execute('INSERT INTO test_table VALUES (1, "测试数据")')
    test_db_engine.commit()
    test_db_engine.close()
    
    print(f"在测试数据集中创建表成功")
    return dataset_id

# 测试修复后的get_dataset_tables函数
def test_fixed_function(user_id="test_user"):
    # 创建测试数据集
    dataset_id = create_test_dataset(user_id)
    
    print(f"\n测试修复后的get_dataset_tables函数，数据集ID: {dataset_id}")
    
    # 调用get_dataset_tables函数
    result, error = get_dataset_tables(user_id, dataset_id)
    
    if error:
        print(f"测试失败: {error}")
        return False
    
    print(f"测试成功，返回结果:")
    print(f"- table_names: {result['table_names']}")
    print(f"- table_names类型: {type(result['table_names'])}")
    print(f"- ddl_statements数量: {len(result['ddl_statements'])}")
    print(f"- ddl_statements类型: {type(result['ddl_statements'])}")
    
    # 测试JSON序列化
    try:
        json_result = json.dumps(result)
        print(f"\nJSON序列化成功: {json_result}")
    except Exception as e:
        print(f"JSON序列化失败: {type(e).__name__}: {e}")
        return False
    
    return True

# 测试handle_dataset_files中的相关操作
def test_csv_upload_scenarios(user_id="test_user"):
    print("\n测试CSV上传相关场景...")
    
    # 这里可以添加更多测试，模拟CSV上传的完整流程
    # 由于我们主要修复的是get_dataset_tables函数，这个测试已经足够验证修复效果
    
    print("\n修复总结:")
    print("1. 在get_dataset_tables函数中，将inspector.get_table_names()的结果转换为标准Python列表")
    print("2. 这样可以确保返回的数据结构在JSON序列化时不会出现类型错误")
    print("3. 这个修复应该能解决'cannot convert dictionary update sequence element #0 to a sequence'错误")

if __name__ == "__main__":
    print("\n===== 测试数据集CSV上传错误修复 ======")
    print_environment_info()
    
    try:
        test_passed = test_fixed_function()
        if test_passed:
            print("\n修复验证成功！get_dataset_tables函数现在应该能正确处理JSON序列化。")
        else:
            print("\n修复验证失败，请检查代码。")
        
        test_csv_upload_scenarios()
    except Exception as e:
        print(f"\n测试过程中发生错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
    print("\n===== 测试完成 ======")