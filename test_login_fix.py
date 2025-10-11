import requests
import time

def test_login_persistence():
    # 测试登录功能和会话持久性
    base_url = 'http://localhost:5000'
    login_url = f'{base_url}/login'
    index_url = f'{base_url}/'
    
    # 创建会话对象以保存cookies
    session = requests.Session()
    
    # 执行登录
    login_data = {
        'username': 'user1',
        'password': 'pass1'
    }
    
    print("执行登录...")
    response = session.post(login_url, data=login_data)
    
    # 检查登录是否成功
    if response.status_code == 200:
        # 如果重定向到主页，获取重定向后的内容
        if response.url == index_url:
            print("登录成功，已重定向到主页")
        else:
            print("登录失败，可能是用户名或密码错误")
            print(f"响应URL: {response.url}")
            return
    else:
        print(f"登录请求失败，状态码: {response.status_code}")
        return
    
    # 验证会话是否保持
    print("验证会话持久性...")
    time.sleep(2)  # 等待几秒钟
    
    # 尝试直接访问主页
    response = session.get(index_url)
    
    if response.status_code == 200 and "資料庫整理介面" in response.text:
        print("会话保持成功，可以访问受保护的页面")
        print("修复已验证，登录信息不再消失")
    else:
        print("会话未保持，可能需要进一步排查")
        print(f"响应状态码: {response.status_code}")
    
    # 打印Cookie信息用于调试
    print("\nCookie信息:")
    for cookie in session.cookies:
        print(f"- {cookie.name}: {cookie.value} (过期时间: {cookie.expires})")
    
if __name__ == '__main__':
    print("=== 测试登录会话持久性 ===")
    test_login_persistence()
    print("=== 测试完成 ===")