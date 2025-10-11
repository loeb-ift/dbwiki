#!/usr/bin/env python3
"""
模块导入测试脚本
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    try:
        # 测试配置模块导入
        from app.config import create_app, setup_logging
        print("✅ 成功导入配置模块")
        
        # 测试模型模块导入
        from app.models import init_training_db, get_dataset_tables
        print("✅ 成功导入模型模块")
        
        # 测试工具模块导入
        from app.utils import load_prompt_template, df_to_json
        print("✅ 成功导入工具模块")
        
        # 测试Vanna包装器模块导入
        from app.vanna_wrapper import get_vanna_instance
        print("✅ 成功导入Vanna包装器模块")
        
        # 测试路由模块导入
        from app.routes import app as flask_app
        print("✅ 成功导入路由模块")
        
        # 测试主模块导入
        from app.main import initialize_app
        print("✅ 成功导入主模块")
        
        print("🎉 所有模块导入测试通过！")
        return True
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        return False

if __name__ == '__main__':
    print("开始测试模块导入...")
    success = test_imports()
    
    if success:
        print("\n提示：您可以使用 python run.py 启动应用")
        sys.exit(0)
    else:
        print("\n模块导入测试失败，请检查文件结构和导入语句")
        sys.exit(1)