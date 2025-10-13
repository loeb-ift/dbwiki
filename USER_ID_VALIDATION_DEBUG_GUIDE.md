# 用户ID格式验证和调试日志指南

本指南介绍了系统中的用户ID格式验证功能以及如何使用调试日志来诊断格式不符的问题。

## 用户ID格式要求

系统要求用户ID必须满足以下格式要求：
- 不能包含点号 (`.`)、斜杠 (`/`) 或空白字符
- 不能为空
- 长度不能超过50个字符

## 调试日志功能

为了帮助诊断用户ID格式不符的问题，我们在系统中添加了全面的调试日志功能。这些日志可以帮助您确定：
- 正在验证的用户ID具体是什么
- 验证失败的具体原因是什么
- 验证失败发生在哪个函数中

## 查看调试日志

### 1. 运行测试脚本

系统提供了两个测试脚本来验证用户ID格式和查看调试日志：

```bash
# 运行用户ID验证测试
python test_user_id_validation.py

# 运行调试日志功能测试
python test_debug_logs.py
```

### 2. 启用应用程序调试日志

在运行应用程序时，可以通过环境变量或直接在代码中设置日志级别为DEBUG：

```bash
# 通过环境变量设置日志级别
export LOG_LEVEL=DEBUG
python run.py
```

## 常见问题诊断

如果遇到用户ID格式不符的问题，可以通过以下步骤进行诊断：

1. 查看日志中 `Validating user ID: '{user_id}'` 的输出，确定系统正在验证的具体用户ID值
2. 查看日志中 `Validation failed: xxx` 的输出，了解验证失败的具体原因
3. 根据失败原因调整用户ID格式

### 示例错误日志和解决方案

#### 错误示例1：包含点号
```
2025-10-13 00:04:40,018 - app.core.db_utils - DEBUG - Validating user ID: 'invalid.user'
2025-10-13 00:04:40,018 - app.core.db_utils - DEBUG - Validation failed: User ID 'invalid.user' contains invalid characters
2025-10-13 00:04:40,018 - app.core.db_utils - ERROR - Invalid user ID: User ID 'invalid.user' contains invalid characters (. / or whitespace)
```
解决方案：移除用户ID中的点号，改为 `invalid_user`

#### 错误示例2：包含空格
```
2025-10-13 00:04:40,018 - app.core.db_utils - DEBUG - Validating user ID: 'invalid user'
2025-10-13 00:04:40,018 - app.core.db_utils - DEBUG - Validation failed: User ID 'invalid user' contains invalid characters
2025-10-13 00:04:40,018 - app.core.db_utils - ERROR - Invalid user ID: User ID 'invalid user' contains invalid characters (. / or whitespace)
```
解决方案：移除用户ID中的空格，改为 `invalid_user` 或 `invalid-user`

#### 错误示例3：用户ID为空
```
2025-10-13 00:04:40,018 - app.core.db_utils - DEBUG - Validating user ID: ''
2025-10-13 00:04:40,018 - app.core.db_utils - DEBUG - Validation failed: User ID is empty
2025-10-13 00:04:40,018 - app.core.db_utils - ERROR - Invalid user ID: User ID cannot be empty
```
解决方案：确保用户ID不为空

#### 错误示例4：用户ID过长
```
2025-10-13 00:04:40,018 - app.core.db_utils - DEBUG - Validating user ID: 'this_is_a_very_long_user_id_that_exceeds_the_maximum_length_limit_of_fifty_characters'
2025-10-13 00:04:40,018 - app.core.db_utils - DEBUG - Validation failed: User ID 'this_is_a_very_long_user_id_that_exceeds_the_maximum_length_limit_of_fifty_characters' is too long (65 characters, max 50)
2025-10-13 00:04:40,018 - app.core.db_utils - ERROR - Invalid user ID: User ID is too long (max 50 characters)
```
解决方案：缩短用户ID，使其不超过50个字符

## 集成点

用户ID验证功能在以下关键位置进行集成：

1. `app/core/db_utils.py` 中的 `validate_user_id` 函数 - 核心验证逻辑
2. `get_user_db_path` 函数 - 生成用户数据库路径前验证
3. `get_user_db_connection` 函数 - 创建数据库连接前验证
4. `app/vanna_wrapper.py` 中的 `get_vanna_instance` 函数 - 创建Vanna实例前验证
5. 所有API端点函数 - 记录传入的用户ID和相关参数

## 自定义日志级别

如果需要调整日志输出级别，可以修改相关文件中的日志配置：

```python
# 在 app/core/db_utils.py 或 app/vanna_wrapper.py 中
logger.setLevel(logging.DEBUG)  # 更改为 DEBUG, INFO, WARNING, ERROR 或 CRITICAL
```

## 注意事项

1. 调试日志会包含用户ID等敏感信息，请确保在生产环境中适当保护这些日志
2. 在生产环境中，建议将日志级别设置为 INFO 或更高，以减少日志量
3. 如果需要调试特定模块，可以仅为该模块设置DEBUG级别日志