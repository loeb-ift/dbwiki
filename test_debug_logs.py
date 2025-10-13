import os
import logging
import sys
from app.core.db_utils import validate_user_id, get_user_db_path
from app.vanna_wrapper import get_vanna_instance

# 配置根日志记录器，确保所有日志都能输出到控制台
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# 为特定模块设置DEBUG级别
logging.getLogger('app.core.db_utils').setLevel(logging.DEBUG)
logging.getLogger('app.vanna_wrapper').setLevel(logging.DEBUG)

print("=== 调试日志功能测试开始 ===\n")

# 测试用例1：有效的用户ID
print("=== 测试1：有效的用户ID ===")
valid_user_id = "test_user_123"
print(f"\n使用有效的用户ID: '{valid_user_id}'")

# 测试validate_user_id函数
print("\n调用validate_user_id:")
result = validate_user_id(valid_user_id)
print(f"验证结果: {result}\n")

# 测试get_user_db_path函数
print("调用get_user_db_path:")
db_path = get_user_db_path(valid_user_id)
print(f"生成的数据库路径: {db_path}\n")

# 测试get_vanna_instance函数
print("调用get_vanna_instance:")
vn = get_vanna_instance(valid_user_id)
print(f"成功获取Vanna实例\n")

# 测试用例2：无效的用户ID（包含点号）
print("\n=== 测试2：无效的用户ID（包含点号） ===")
invalid_user_id = "invalid.user"
print(f"\n使用无效的用户ID: '{invalid_user_id}'")

# 测试validate_user_id函数
print("\n调用validate_user_id:")
result = validate_user_id(invalid_user_id)
print(f"验证结果: {result}\n")

# 测试get_user_db_path函数（预期会抛出异常）
print("调用get_user_db_path（预期会抛出异常）:")
try:
    db_path = get_user_db_path(invalid_user_id)
except ValueError as e:
    print(f"预期的ValueError: {e}\n")

# 测试get_vanna_instance函数（预期会抛出异常）
print("调用get_vanna_instance（预期会抛出异常）:")
try:
    vn = get_vanna_instance(invalid_user_id)
except ValueError as e:
    print(f"预期的ValueError: {e}\n")

print("\n=== 调试日志功能测试完成 ===")
print("请检查控制台输出，确认所有debug日志都已正确显示。")