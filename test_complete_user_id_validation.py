import os
import logging
from app.core.db_utils import validate_user_id, get_user_db_path, get_user_db_connection
from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request
import sqlite3

# 配置日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('complete_user_id_validation_test')

# 测试函数
def run_complete_test():
    print("=== 综合用户ID验证测试开始 ===\n")
    
    # 测试用例1：有效的用户ID
    print("=== 测试1：有效的用户ID ===")
    test_valid_user_id()
    print()
    
    # 测试用例2：无效的用户ID（包含点）
    print("=== 测试2：无效的用户ID（包含点） ===")
    test_invalid_user_id_with_dot()
    print()
    
    # 测试用例3：无效的用户ID（包含斜杠）
    print("=== 测试3：无效的用户ID（包含斜杠） ===")
    test_invalid_user_id_with_slash()
    print()
    
    # 测试用例4：无效的用户ID（包含空格）
    print("=== 测试4：无效的用户ID（包含空格） ===")
    test_invalid_user_id_with_space()
    print()
    
    # 测试用例5：无效的用户ID（空字符串）
    print("=== 测试5：无效的用户ID（空字符串） ===")
    test_invalid_user_id_empty()
    print()
    
    print("=== 综合用户ID验证测试完成 ===")

def test_valid_user_id():
    user_id = "valid_user_123"
    try:
        print(f"验证用户ID '{user_id}'")
        is_valid, message = validate_user_id(user_id)
        print(f"validate_user_id结果: 有效={is_valid}, 消息={message}")
        
        print(f"测试get_user_db_path: 'user_id'='{user_id}'")
        db_path = get_user_db_path(user_id)
        print(f"生成的数据库路径: {db_path}")
        
        print(f"测试get_user_db_connection: 'user_id'='{user_id}'")
        conn = get_user_db_connection(user_id)
        print("数据库连接成功创建")
        conn.close()
        
        print(f"测试get_vanna_instance: 'user_id'='{user_id}'")
        vn = get_vanna_instance(user_id)
        print("Vanna实例成功创建")
        
    except Exception as e:
        print(f"测试失败，预期应该成功但出现错误: {e}")

def test_invalid_user_id_with_dot():
    user_id = "invalid.user"
    run_invalid_test(user_id, "包含点号")

def test_invalid_user_id_with_slash():
    user_id = "invalid/user"
    run_invalid_test(user_id, "包含斜杠")

def test_invalid_user_id_with_space():
    user_id = "invalid user"
    run_invalid_test(user_id, "包含空格")

def test_invalid_user_id_empty():
    user_id = ""
    run_invalid_test(user_id, "空字符串")

def run_invalid_test(user_id, reason):
    try:
        print(f"验证用户ID '{user_id}' ({reason})")
        is_valid, message = validate_user_id(user_id)
        print(f"validate_user_id结果: 有效={is_valid}, 消息={message}")
        
        print(f"测试get_user_db_path应该失败: 'user_id'='{user_id}'")
        db_path = get_user_db_path(user_id)
        print(f"错误: 应该抛出异常但成功返回了路径: {db_path}")
    except ValueError as e:
        print(f"预期的ValueError: {e}")
    except Exception as e:
        print(f"测试失败，出现了意外异常: {e}")
    
    try:
        print(f"测试get_vanna_instance应该失败: 'user_id'='{user_id}'")
        vn = get_vanna_instance(user_id)
        print(f"错误: 应该抛出异常但成功创建了实例")
    except ValueError as e:
        print(f"预期的ValueError: {e}")
    except Exception as e:
        print(f"测试失败，出现了意外异常: {e}")

if __name__ == "__main__":
    run_complete_test()