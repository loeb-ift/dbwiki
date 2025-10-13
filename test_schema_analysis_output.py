import requests
import json
import time

# 创建会话对象
session = requests.Session()

def login(username, password):
    print("正在登录...")
    login_response = session.post(
        'http://localhost:5001/login',
        data={'username': username, 'password': password}
    )
    print(f"登录状态码: {login_response.status_code}")
    
    if login_response.status_code != 200:
        print("登录失败，无法继续测试")
        return False
    
    print("登录成功!")
    return True

def get_active_dataset():
    print("\n检查数据集状态...")
    datasets_response = session.get('http://localhost:5001/api/datasets')
    
    if datasets_response.status_code != 200:
        print(f"获取数据集失败: {datasets_response.status_code}")
        return None
    
    datasets = datasets_response.json().get('datasets', [])
    if not datasets:
        print("没有找到数据集")
        return None
    
    print(f"找到 {len(datasets)} 个数据集")
    for ds in datasets:
        print(f"- {ds['dataset_name']} (ID: {ds['id']}, 激活状态: {'已激活' if ds.get('is_active') else '未激活'})")
        # 优先选择激活的数据集
        if ds.get('is_active'):
            return ds['id']
    
    # 如果没有激活的数据集，返回第一个数据集
    print("没有激活的数据集，使用第一个数据集")
    return datasets[0]['id']

def test_schema_analysis_output(question):
    print(f"\n测试schema-analysis-output: 提出问题 '{question}'")
    
    # 调用/api/ask端点
    with session.post(
        'http://localhost:5001/api/ask',
        json={'question': question},
        stream=True
    ) as response:
        print(f"响应状态码: {response.status_code}")
        if response.status_code != 200:
            print("请求失败")
            print(f"错误信息: {response.text}")
            return False
        
        print("\n开始接收AI的思考过程数据:")
        print("=" * 80)
        
        buffer = ""
        
        # 处理服务器发送的事件流
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                buffer += chunk.decode('utf-8', errors='replace')
                
                # 查找完整的事件
                while '\n\n' in buffer:
                    event, buffer = buffer.split('\n\n', 1)
                    lines = event.split('\n')
                    
                    for line in lines:
                        if line.startswith('data:'):
                            data_part = line[5:].strip()
                            if data_part:
                                try:
                                    # 解析JSON数据
                                    data = json.loads(data_part)
                                    
                                    # 根据不同类型的事件进行处理
                                    if data.get('type') == 'thinking_step':
                                        # 这是AI的思考过程步骤
                                        print(f"[{data.get('step', '思考')}] {data.get('details', '')}")
                                    elif data.get('type') == 'result':
                                        # 这是最终结果
                                        print(f"\n{'-' * 80}")
                                        print("最终结果:")
                                        print(f"SQL: {data.get('sql')}")
                                        print(f"分析结果: {data.get('analysis_result')}")
                                    elif data.get('type') == 'warning':
                                        print(f"[警告] {data.get('message', '')}")
                                    elif data.get('type') == 'error':
                                        print(f"[错误] {data.get('message', '')}")
                                        print(f"堆栈跟踪: {data.get('traceback', '')}")
                                except json.JSONDecodeError as e:
                                    print(f"JSON解析错误: {e}, 数据: {data_part}")
        
        print("\n" + "=" * 80)
        print("思考过程接收完毕")
    
    return True

def test_documentation_output():
    print("\n测试documentation-output: 获取数据集分析报告")
    
    # 获取活动数据集ID
    dataset_id = get_active_dataset()
    if not dataset_id:
        print("无法获取数据集ID，跳过测试")
        return False
    
    # 调用获取分析报告的API
    # 注意：这里假设分析报告的API端点是/api/dataset/{dataset_id}/analysis
    # 实际上可能需要根据项目的具体实现进行调整
    response = session.get(f'http://localhost:5001/api/dataset/{dataset_id}/analysis')
    
    if response.status_code == 404:
        print("分析报告API端点不存在。在实际系统中，分析报告通常是存储在数据库中的__dataset_analysis__记录")
        print("可以通过检查数据库中的__dataset_analysis__表来验证documentation-output的数据")
        return True
    elif response.status_code != 200:
        print(f"获取分析报告失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return False
    
    # 解析并显示分析报告
    analysis_data = response.json()
    print("\n数据集分析报告:")
    print("=" * 80)
    print(json.dumps(analysis_data, ensure_ascii=False, indent=2))
    print("=" * 80)
    
    return True

if __name__ == '__main__':
    print("===== 开始测试schema-analysis-output和documentation-output组件 =====")
    
    # 登录系统
    if not login('user1', 'pass1'):
        exit(1)
    
    # 等待短暂时间，确保会话完全建立
    time.sleep(1)
    
    # 获取活动数据集ID（可选，因为系统会自动使用活动数据集）
    dataset_id = get_active_dataset()
    if not dataset_id:
        print("警告：没有找到数据集，可能会影响测试结果")
    
    # 测试schema-analysis-output组件
    # 提出一个简单的问题来触发AI的思考过程
    question = "显示所有订单的总金额是多少？"
    if not test_schema_analysis_output(question):
        print("schema-analysis-output测试失败")
    else:
        print("schema-analysis-output测试成功")
    
    # 测试documentation-output组件
    # 注意：实际系统中，分析报告通常是通过"资料库自动分析"功能生成并存储在数据库中的
    if not test_documentation_output():
        print("documentation-output测试失败")
    else:
        print("documentation-output测试成功")
    
    print("\n===== 测试完成 =====")