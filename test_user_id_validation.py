import re
import os
import logging
from app.core.db_utils import get_user_db_path
from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request

# 配置日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('user_id_validation_test')

# 用户ID验证函数
def validate_user_id(user_id):
    """验证用户ID是否符合要求，不含 . / 空白等特殊字符"""
    if not user_id:
        return False, "User ID cannot be empty"
    
    # 检查是否包含不允许的字符：. / 和空白字符
    if re.search(r'[./\s]', user_id):
        return False, f"User ID '{user_id}' contains invalid characters (. / or whitespace)"
    
    # 检查长度是否合理
    if len(user_id) > 50:
        return False, "User ID is too long (max 50 characters)"
    
    return True, "User ID is valid"

# 测试不同格式的用户ID
def test_user_id_formats():
    test_cases = [
        "user1",            # 有效格式
        "user_123",         # 有效格式，包含下划线
        "user.name",        # 无效格式，包含点
        "user/path",        # 无效格式，包含斜杠
        "user name",        # 无效格式，包含空格
        "user\ttab",        # 无效格式，包含制表符
        "",                 # 无效格式，空字符串
        "a" * 51            # 无效格式，太长
    ]
    
    print("=== Testing User ID Formats ===")
    for user_id in test_cases:
        is_valid, message = validate_user_id(user_id)
        print(f"User ID: '{user_id}' - Valid: {is_valid}, Message: {message}")
        
        if is_valid:
            try:
                # 测试数据库路径生成
                db_path = get_user_db_path(user_id)
                print(f"  Generated DB Path: {db_path}")
            except Exception as e:
                print(f"  Error generating DB path: {e}")
    
    print("=== Test Completed ===")

if __name__ == "__main__":
    test_user_id_formats()