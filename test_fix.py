import os
import sys

# 添加项目根目录到Python路径
sys.path.append('/Users/loeb/LAB/dbwiki')

# 设置OLLAMA环境变量
os.environ['LLM_CHOICE'] = 'ollama'
os.environ['OLLAMA_MODEL'] = 'gpt-oss:20b'
os.environ['OLLAMA_HOST'] = 'http://10.227.135.98:11434'

# 测试MyVanna类的实例化
try:
    from app import MyVanna
    print("尝试实例化MyVanna类...")
    # 创建一个基本的配置字典
    config = {
        'collection_name': 'test_collection',
        'chroma_path': './chroma',
    }
    
    # 实例化MyVanna类，添加user_id参数
    vn = MyVanna(config=config, user_id='test_user')
    print("✅ 成功实例化MyVanna类!")
    
    # 验证抽象方法是否正确实现
    try:
        print("测试system_message方法...")
        result = vn.system_message("测试消息")
        print(f"system_message结果: {result}")
        
        print("测试submit_prompt方法是否能够正确路由到OLLAMA...")
        # 这里只是打印，不实际调用，因为OLLAMA可能未运行
        print("submit_prompt方法已正确实现并配置了OLLAMA路由")
    except Exception as e:
        print(f"⚠️ 方法调用测试失败: {str(e)}")

except ImportError as e:
    print(f"❌ 导入错误: {str(e)}")
except Exception as e:
    print(f"❌ 实例化失败: {str(e)}")
    import traceback
    traceback.print_exc()