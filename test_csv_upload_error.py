import os
import sqlite3
from sqlalchemy import create_engine, inspect, text

# 确保这个脚本可以在项目根目录下运行
sys_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
if sys_path not in os.sys.path:
    os.sys.path.append(sys_path)

# 导入get_user_db_connection函数
try:
    from app.core.db_utils import get_user_db_connection
    print("成功导入get_user_db_connection函数")
except ImportError as e:
    print(f"导入错误: {e}")
    
    # 为了测试，我们创建一个模拟的get_user_db_connection函数
    def mock_get_user_db_connection(user_id):
        class MockConn:
            def __init__(self):
                self.conn = sqlite3.connect(':memory:')
                cursor = self.conn.cursor()
                cursor.execute('CREATE TABLE IF NOT EXISTS datasets (id TEXT, db_path TEXT)')
                cursor.execute('INSERT INTO datasets VALUES ("test_id", ":memory:")')
                self.conn.commit()
            
            def __enter__(self):
                return self.conn
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                self.conn.close()
        
        return MockConn()
    
    get_user_db_connection = mock_get_user_db_connection
    print("使用模拟的get_user_db_connection函数进行测试")

# 定义测试的get_dataset_tables函数，模拟实际代码的行为
def test_get_dataset_tables(user_id, dataset_id):
    print(f"\n测试get_dataset_tables函数 - 用户ID: {user_id}, 数据集ID: {dataset_id}")
    
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
        if not row:
            print("数据集不存在")
            return None, "Dataset not found"
        db_path = row[0]
        print(f"找到数据库路径: {db_path}")
    
    try:
        # 创建一个临时的SQLite数据库进行测试
        if db_path == ':memory:':
            engine = create_engine('sqlite:///:memory:')
            # 创建一些测试表
            with engine.connect() as connection:
                connection.execute(text('CREATE TABLE test_table1 (id INTEGER, name TEXT)'))
                connection.execute(text('CREATE TABLE test_table2 (id INTEGER, value INTEGER)'))
                connection.commit()
        else:
            engine = create_engine(f'sqlite:///{db_path}')
        
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        print(f"获取到的表名: {table_names}")
        print(f"表名类型: {type(table_names)}")
        
        ddl_statements = []
        with engine.connect() as connection:
            for name in table_names:
                ddl = connection.execute(text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{name}';")).scalar()
                if ddl: 
                    ddl_statements.append(ddl + ";")
                    print(f"表 {name} 的DDL: {ddl[:50]}...")
        
        print(f"DDL语句列表: {ddl_statements}")
        print(f"DDL语句列表类型: {type(ddl_statements)}")
        
        # 测试返回值的转换
        result = {
            'table_names': table_names,
            'ddl_statements': ddl_statements
        }
        
        print(f"返回结果: {result}")
        
        # 测试JSON序列化
        import json
        json_result = json.dumps(result)
        print(f"JSON序列化结果: {json_result}")
        
        return result, None
    except Exception as e:
        print(f"发生错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None, str(e)

# 执行测试
if __name__ == "__main__":
    print("开始测试数据集CSV上传后的错误: cannot convert dictionary update sequence element #0 to a sequence")
    
    # 测试1: 使用模拟数据
    result, error = test_get_dataset_tables("test_user", "test_id")
    
    print("\n测试结果总结:")
    if error:
        print(f"测试失败: {error}")
    else:
        print(f"测试成功，结果类型: {type(result)}")
        print(f"table_names类型: {type(result['table_names'])}")
        print(f"ddl_statements类型: {type(result['ddl_statements'])}")
    
    print("\n可能的错误原因:")
    print("1. SQLite查询结果转换为字典时出错")
    print("2. 返回的数据结构格式不兼容JSON序列化")
    print("3. 表名或DDL语句的数据类型异常")
    
    print("\n建议的修复方案:")
    print("- 确保所有返回的列表都是标准Python列表而非特殊对象")
    print("- 在返回前对数据结构进行验证和转换")
    print("- 添加异常处理来捕获和处理字典转换错误")