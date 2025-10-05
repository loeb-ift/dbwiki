import requests
import json
import time

# 创建会话对象
session = requests.Session()

# 1. 登录获取会话cookie
print("正在登录...")
login_response = session.post(
    'http://localhost:5001/login',
    data={'username': 'user1', 'password': 'pass1'}
)
print(f"登录状态码: {login_response.status_code}")

if login_response.status_code != 200:
    print("登录失败，无法继续测试")
    exit(1)

# 2. 检查当前活跃的数据集状态
print("\n检查数据集状态...")
datasets_response = session.get('http://localhost:5001/api/datasets')
datasets = datasets_response.json().get('datasets', [])
if datasets:
    print(f"找到 {len(datasets)} 个数据集")
    for ds in datasets:
        print(f"- {ds['dataset_name']} (ID: {ds['id']}, 激活状态: {'已激活' if ds.get('is_active') else '未激活'})")

# 3. 创建一个简单的SQL文件内容
sql_content = """SELECT * FROM users;
SELECT * FROM products;
SELECT * FROM orders;"""

# 4. 测试流式响应
print("\n开始测试/api/generate_qa_from_sql端点的流式响应...")
start_time = time.time()

# 使用流式请求
with session.post(
    'http://localhost:5001/api/generate_qa_from_sql',
    files={'sql_file': ('test.sql', sql_content)},  # 直接传入SQL内容作为文件
    stream=True
) as response:
    print(f"响应状态码: {response.status_code}")
    if response.status_code != 200:
        print("请求失败")
        print(f"错误信息: {response.text}")
        exit(1)

    # 处理流式响应
    buffer = ""
    qa_pairs_received = 0
    
    print("\n开始接收流式数据:")
    print("=" * 50)
    
    for chunk in response.iter_content(chunk_size=1):
        if chunk:
            buffer += chunk.decode('utf-8')
            # 检查是否有完整的行
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if line.strip().startswith('data:'):
                    try:
                        data_part = line.strip()[5:].strip()  # 去掉 'data: ' 前缀
                        if data_part:
                            data = json.loads(data_part)
                            
                            if data.get('status') == 'progress':
                                qa_pairs_received += 1
                                print(f"收到问答对 {qa_pairs_received}:")
                                print(f"  问题: {data['qa_pair']['question']}")
                                print(f"  SQL: {data['qa_pair']['sql']}")
                                print(f"  进度: {data['count']}/{data['total']}")
                                print("-" * 50)
                            elif data.get('status') == 'completed':
                                print(f"\n处理完成: {data['message']}")
                            elif data.get('status') == 'error' or data.get('status') == 'error_partial':
                                print(f"错误: {data['message']}")
                    except json.JSONDecodeError as e:
                        print(f"JSON解析错误: {e}, 行内容: {line}")

end_time = time.time()
print(f"\n测试完成，耗时: {end_time - start_time:.2f} 秒")
print(f"总共接收 {qa_pairs_received} 个问答对")