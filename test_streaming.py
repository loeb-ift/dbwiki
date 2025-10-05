import requests
import json
import time

# 登录并获取会话cookie
session = requests.Session()
login_response = session.post('http://localhost:5001/login', data={'username': 'user1', 'password': 'pass1'})
print(f'登录状态码: {login_response.status_code}')
print(f'登录响应: {login_response.text}')

# 检查是否有一个激活的数据集
if login_response.status_code == 200:
    # 先检查当前激活的数据集
    datasets_response = session.get('http://localhost:5001/api/datasets')
    print(f'数据集状态码: {datasets_response.status_code}')
    print(f'数据集响应: {datasets_response.text}')
    
    # 尝试上传SQL文件并测试流式响应
    # 使用更简单的SQL文件内容，直接嵌入到请求中
    simple_sql = "SELECT * FROM users;"
    files = {'sql_file': ('simple_test.sql', simple_sql, 'text/plain')}
    
    print('开始上传SQL文件并测试流式响应...')
    start_time = time.time()
    
    # 使用stream=True来处理流式响应
    response = session.post('http://localhost:5001/api/generate_qa_from_sql', files=files, stream=True)
    
    if response.status_code == 200:
        print(f'请求成功，状态码: {response.status_code}')
        print(f'响应头: {response.headers}')
        
        # 处理流式响应
        buffer = ''
        for chunk in response.iter_content(chunk_size=1):  # 逐字节读取以更好地观察流
            if chunk:
                char = chunk.decode('utf-8')
                buffer += char
                print(f'收到字符: "{char}" 缓冲区: "{buffer}"')
                # 当遇到完整的事件流消息时处理
                if '\n\n' in buffer:
                    event, buffer = buffer.split('\n\n', 1)
                    print(f'完整事件: "{event}"')
                    if event.startswith('data: '):
                        json_str = event[6:].strip()
                        if json_str:
                            try:
                                data = json.loads(json_str)
                                print(f'解析数据: {data}')
                            except json.JSONDecodeError:
                                print(f'无法解析JSON: {json_str}')
            # 为了看到实时效果，添加短暂延迟
            time.sleep(0.01)
            
        end_time = time.time()
        print(f'流式响应处理完成，耗时: {end_time - start_time:.2f}秒')
        print(f'最终缓冲区内容: "{buffer}"')
    else:
        print(f'请求失败，状态码: {response.status_code}')
        print(f'响应内容: {response.text}')
else:
    print(f'登录失败，无法测试API端点')
    # 打印cookie信息以便调试
    print(f'Cookie jar: {session.cookies}')