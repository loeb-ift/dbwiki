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
    
    if login_response.status_code != 200:
        print(f"登录失败: 状态码 {login_response.status_code}")
        print("无法继续测试")
        return False
    
    print("登录成功!")
    return True

def test_schema_analysis_thought_process(question):
    print(f"\n测试schema-analysis-output: 提出问题 '{question}'")
    print("=" * 80)
    print("AI的思考过程:")
    print("=" * 80)
    
    # 调用/api/ask端点，获取思考过程
    with session.post(
        'http://localhost:5001/api/ask',
        json={'question': question},
        stream=True
    ) as response:
        if response.status_code != 200:
            print(f"请求失败: 状态码 {response.status_code}")
            print(f"错误信息: {response.text}")
            return False
        
        buffer = ""
        
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                buffer += chunk.decode('utf-8', errors='replace')
                
                # 处理接收到的事件流
                while '\n\n' in buffer:
                    event, buffer = buffer.split('\n\n', 1)
                    lines = event.split('\n')
                    
                    for line in lines:
                        if line.startswith('data:'):
                            data_part = line[5:].strip()
                            if data_part:
                                try:
                                    data = json.loads(data_part)
                                    
                                    # 特别关注AI的思考过程
                                    if data.get('type') == 'thinking_step':
                                        # 这是思考过程的步骤
                                        step_type = data.get('step', '思考')
                                        details = data.get('details', '')
                                        
                                        # 显示AI的思考过程，模拟schema-analysis-output的显示
                                        print(f"[{step_type}] {details}")
                                    
                                except json.JSONDecodeError:
                                    # 如果解析失败，可能是因为数据不完整，继续接收
                                    pass
    
    print("=" * 80)
    print("思考过程接收完毕")
    return True

if __name__ == '__main__':
    print("===== 开始测试schema-analysis-output组件 =====")
    
    # 使用user1/pass1登录
    if not login('user1', 'pass1'):
        exit(1)
    
    # 等待短暂时间，确保会话完全建立
    time.sleep(1)
    
    # 测试schema-analysis-output组件
    # 提出一个问题来触发AI的思考过程
    question = "公司的销售数据如何？"
    
    if not test_schema_analysis_thought_process(question):
        print("\nschema-analysis-output测试失败")
    else:
        print("\nschema-analysis-output测试成功")
    
    print("\n===== 测试完成 =====")
    print("\n注意：")
    print("1. schema-analysis-output组件显示的是AI在生成SQL时的即时思考过程")
    print("2. 思考过程包括检索到的相关DDL、业务文件、相似问答范例以及构建最终提示的过程")
    print("3. 这个测试脚本模拟了schema-analysis-output组件的核心功能")