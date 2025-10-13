import sqlite3
import json

# 测试SQLite查询结果的字典转换
print("开始测试字典转换错误: cannot convert dictionary update sequence element #0 to a sequence")

# 测试场景1: 直接转换sqlite3.Row对象
def test_sqlite_row_conversion():
    print("\n测试场景1: 直接转换sqlite3.Row对象")
    conn = sqlite3.connect(':memory:')
    
    # 创建测试表
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE test_table (id INTEGER, name TEXT)')
    cursor.execute('INSERT INTO test_table VALUES (1, "Test")')
    conn.commit()
    
    # 设置row_factory为sqlite3.Row
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM test_table')
    rows = cursor.fetchall()
    
    print(f"获取到的行对象类型: {type(rows[0])}")
    
    try:
        # 尝试直接将sqlite3.Row转换为dict
        dict_rows = [dict(row) for row in rows]
        print(f"直接转换成功: {dict_rows}")
    except Exception as e:
        print(f"直接转换失败: {type(e).__name__}: {e}")
    
    # 测试修复方案: 使用cursor.description获取列名
    conn.row_factory = None  # 重置row_factory
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM test_table')
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    try:
        # 使用dict(zip(columns, row))转换
        fixed_dict_rows = [dict(zip(columns, row)) for row in rows]
        print(f"修复后转换成功: {fixed_dict_rows}")
    except Exception as e:
        print(f"修复后转换失败: {type(e).__name__}: {e}")
    
    conn.close()

# 测试场景2: 模拟不同类型的返回值

def test_various_return_types():
    print("\n测试场景2: 模拟不同类型的返回值")
    
    # 模拟可能的返回值类型
    test_cases = [
        # 测试1: 正常列表
        {"table_names": ["table1", "table2"], "ddl_statements": ["CREATE TABLE...", "CREATE TABLE..."]},
        # 测试2: 可能导致问题的类型
        {"table_names": tuple(["table1", "table2"]), "ddl_statements": ["CREATE TABLE...", "CREATE TABLE..."]},
        # 测试3: 空列表
        {"table_names": [], "ddl_statements": []},
        # 测试4: 包含非标准类型
        {"table_names": ["table1", "table2"], "ddl_statements": ["CREATE TABLE...", object()]}
    ]
    
    for i, test_case in enumerate(test_cases):
        print(f"\n测试{i+1}:")
        print(f"table_names类型: {type(test_case['table_names'])}")
        print(f"ddl_statements类型: {type(test_case['ddl_statements'])}")
        
        # 测试JSON序列化
        try:
            json_result = json.dumps(test_case)
            print(f"JSON序列化成功: {json_result}")
        except Exception as e:
            print(f"JSON序列化失败: {type(e).__name__}: {e}")

# 测试场景3: 测试get_dataset_tables函数的修复版本
def test_fixed_get_dataset_tables():
    print("\n测试场景3: 测试get_dataset_tables函数的修复版本")
    
    # 模拟数据库连接和查询
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    
    # 创建测试数据集表
    cursor.execute('CREATE TABLE datasets (id TEXT, db_path TEXT)')
    cursor.execute('INSERT INTO datasets VALUES ("test_id", ":memory:")')
    conn.commit()
    
    # 模拟用户数据库连接
    class MockUserDBConnection:
        def __init__(self, user_id):
            self.user_id = user_id
        def __enter__(self):
            return conn
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    
    # 模拟修复后的get_dataset_tables函数
    def fixed_get_dataset_tables(user_id, dataset_id):
        with MockUserDBConnection(user_id) as conn:
            cursor = conn.cursor()
            # 注意这里没有设置row_factory
            cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
            row = cursor.fetchone()
            if not row:
                return None, "Dataset not found"
            db_path = row[0]
        
        try:
            # 创建内存数据库并添加测试表
            test_conn = sqlite3.connect(':memory:')
            test_cursor = test_conn.cursor()
            test_cursor.execute('CREATE TABLE test_table1 (id INTEGER, name TEXT)')
            test_cursor.execute('CREATE TABLE test_table2 (id INTEGER, value INTEGER)')
            test_conn.commit()
            
            # 获取表名（这里确保返回的是标准列表）
            test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            table_names = [row[0] for row in test_cursor.fetchall()]
            
            # 获取DDL语句
            ddl_statements = []
            for name in table_names:
                test_cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,))
                ddl_row = test_cursor.fetchone()
                if ddl_row and ddl_row[0]:
                    ddl_statements.append(ddl_row[0] + ";")
            
            test_conn.close()
            
            return {
                'table_names': list(table_names),  # 确保是列表类型
                'ddl_statements': list(ddl_statements)  # 确保是列表类型
            }, None
        except Exception as e:
            return None, str(e)
    
    # 运行修复后的函数
    result, error = fixed_get_dataset_tables("test_user", "test_id")
    
    if error:
        print(f"修复后函数执行失败: {error}")
    else:
        print(f"修复后函数执行成功")
        print(f"返回结果: {result}")
        print(f"table_names类型: {type(result['table_names'])}")
        print(f"ddl_statements类型: {type(result['ddl_statements'])}")
        
        # 测试JSON序列化
        try:
            json_result = json.dumps(result)
            print(f"JSON序列化成功: {json_result}")
        except Exception as e:
            print(f"JSON序列化失败: {type(e).__name__}: {e}")
    
    conn.close()

# 运行所有测试
if __name__ == "__main__":
    test_sqlite_row_conversion()
    test_various_return_types()
    test_fixed_get_dataset_tables()
    
    print("\n测试完成。基于测试结果，最可能的问题是在某个地方使用了conn.row_factory = sqlite3.Row后直接尝试将查询结果转换为字典。")
    print("建议的修复方案是在get_dataset_tables函数中避免使用row_factory，或者确保在转换为字典时使用正确的方法。")