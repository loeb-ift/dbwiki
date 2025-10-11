import os
import json
import pytest
from flask import Flask, session
from unittest.mock import patch
from app.blueprints.auth import auth_bp
from app.main import main as main_blueprint

# 导入需要mock的函数
from app.blueprints import auth

# 设置环境变量
def test_login_function():
    """测试登录功能"""
    # 创建一个测试Flask应用
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test_secret_key'
    app.config['TESTING'] = True
    
    # 设置测试用户，使用简单格式与生产环境保持一致
    app.config['USERS'] = {
        'testuser': 'password'
    }
    
    # 注册蓝图
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_blueprint)
    
    # 创建测试客户端
    client = app.test_client()
    
    # 使用mock替换auth模块中的init_training_db函数
    with patch.object(auth, 'init_training_db') as mock_init_db:
        # 模拟登录请求
        response = client.post('/login', data={
            'username': 'testuser',
            'password': 'password'
        }, follow_redirects=True)
        
        # 检查登录是否成功（重定向到首页）
        assert response.status_code == 200
        
        # 在测试请求上下文内检查会话
        with client.session_transaction() as sess:
            assert sess.get('username') == 'testuser'
            assert sess.get('active_dataset') == 'training_data_qa'
        
        # 验证init_training_db被调用
        mock_init_db.assert_called_once_with('testuser')
    
    print("登录测试成功！")

if __name__ == '__main__':
    # 如果直接运行脚本，则执行测试
    test_login_function()