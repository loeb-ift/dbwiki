import requests

# 测试1：检查主页是否重定向到登录页面
def test_home_redirect():
    print("测试1：检查主页重定向到登录页面")
    response = requests.get('http://localhost:5003/', allow_redirects=False)
    print(f"状态码: {response.status_code}")
    print(f"是否重定向: {response.is_redirect}")
    if response.is_redirect:
        print(f"重定向位置: {response.headers.get('Location')}")
    print()

# 测试2：获取登录页面
def test_get_login():
    print("测试2：获取登录页面")
    response = requests.get('http://localhost:5003/login')
    print(f"状态码: {response.status_code}")
    print(f"页面包含表单: {'<form' in response.text}")
    print(f"页面标题: {'Login' in response.text}")
    print()

# 测试3：尝试登录（使用配置的用户）
def test_login():
    print("测试3：尝试使用配置的用户登录")
    # 从日志中看到的配置用户是user1/pass1
    data = {'username': 'user1', 'password': 'pass1'}
    response = requests.post('http://localhost:5003/login', data=data, allow_redirects=False)
    print(f"状态码: {response.status_code}")
    print(f"是否重定向到主页: {response.is_redirect and response.headers.get('Location') == '/'}")
    print()

if __name__ == '__main__':
    test_home_redirect()
    test_get_login()
    test_login()
    print("测试完成！如果所有测试都通过，说明登录功能正常工作。")