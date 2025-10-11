import os
import sys
import os
from app.core.vanna_core import get_vanna_instance, configure_vanna_for_request

# 添加项目根目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

# 测试函数
def test_sql_generation():
    # 模拟用户会话信息
    os.environ['OLLAMA_MODEL'] = 'gpt-oss:20b'
    os.environ['OLLAMA_HOST'] = 'http://10.227.135.98:11434'
    os.environ['OLLAMA_NUM_CTX'] = '16384'
    
    # 使用一个测试用户ID和数据集ID
    user_id = 'test_user'
    # 替换为实际存在的数据集ID
    dataset_id = '1'
    
    try:
        # 获取Vanna实例并配置
        vn_instance = get_vanna_instance(user_id)
        vn = configure_vanna_for_request(vn_instance, user_id, dataset_id)
        
        # 打印数据库结构信息，验证是否正确加载
        print("\n=== 数据库结构信息 ===")
        if vn.db_schema_info:
            print(vn.db_schema_info)
        else:
            print("警告: 没有加载到数据库结构信息")
        
        # 测试问题
        test_questions = [
            "显示所有表的名称和结构",
            "查询订单表中的前10条记录"
        ]
        
        print("\n=== SQL生成测试 ===")
        for question in test_questions:
            print(f"\n问题: {question}")
            
            try:
                # 生成SQL
                sql = vn.generate_sql(question=question)
                print(f"生成的SQL: {sql}")
                
                # 执行SQL（可选，如果数据库中有数据）
                try:
                    if vn.run_sql_is_set:
                        df = vn.run_sql(sql)
                        print(f"查询结果行数: {len(df)}")
                        if not df.empty:
                            print("前几行结果:")
                            print(df.head())
                except Exception as e:
                    print(f"SQL执行错误: {str(e)}")
            except Exception as e:
                print(f"SQL生成错误: {str(e)}")
    except Exception as e:
        print(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_sql_generation()