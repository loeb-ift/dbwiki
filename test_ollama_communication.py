import os
import sys

# 添加项目根目录到Python路径
sys.path.append('/Users/loeb/LAB/dbwiki')

# 设置OLLAMA环境变量
os.environ['LLM_CHOICE'] = 'ollama'
os.environ['OLLAMA_MODEL'] = 'gpt-oss:20b'
os.environ['OLLAMA_HOST'] = 'http://10.227.135.98:11434'

# 测试MyVanna类与OLLAMA的通信
try:
    from app import MyVanna
    print("尝试实例化MyVanna类...")
    
    # 实例化MyVanna类
    vn = MyVanna(user_id='test_user')
    print("✅ 成功实例化MyVanna类!")
    
    # 尝试与OLLAMA通信
    try:
        print("尝试与OLLAMA服务通信...")
        simple_prompt = [
            vn.system_message("你是一个助手，用简短的中文回答问题。"),
            vn.user_message("你好，简单测试一下。")
        ]
        
        response = vn.submit_prompt(simple_prompt)
        print(f"✅ 成功接收OLLAMA响应: {response}")
        
    except Exception as e:
        print(f"⚠️ OLLAMA通信测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

except ImportError as e:
    print(f"❌ 导入错误: {str(e)}")
except Exception as e:
    print(f"❌ 实例化失败: {str(e)}")
    import traceback
    traceback.print_exc()