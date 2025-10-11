import os
import logging
import os
import json
from flask import Flask
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    return logging.getLogger(__name__)

# 创建Flask应用实例
def create_app():
    # 获取项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 创建Flask应用并设置模板和静态文件目录
    app = Flask(__name__, 
                template_folder=os.path.join(project_root, 'templates'),
                static_folder=os.path.join(project_root, 'static'))
                
    # 增强SECRET_KEY安全性，确保生产环境不使用默认值
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-only-' + os.urandom(24).hex())
    
    # 设置会话 cookie 的安全选项
    app.config['SESSION_COOKIE_SECURE'] = not is_debug_mode()  # 在非调试模式下使用HTTPS
    app.config['SESSION_COOKIE_HTTPONLY'] = True  # 防止JavaScript访问cookie
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 防止CSRF攻击
    
    # 用户认证配置
    # 优先从APP_USERS环境变量加载JSON格式的用户配置
    APP_USERS = os.getenv('APP_USERS')
    USERS = {}
    
    if APP_USERS:
        try:
            users_dict = json.loads(APP_USERS)
            # 将简单的密码映射转换为完整的用户配置
            for username, password in users_dict.items():
                USERS[username] = {
                    'password': password,
                    'is_admin': False  # 默认非管理员
                }
        except json.JSONDecodeError:
            logging.error("Failed to parse APP_USERS environment variable")
    
    # 如果从环境变量加载失败或为空，使用默认配置
    if not USERS:
        USERS = {
            os.getenv('USER1', 'admin'): {
                'password': os.getenv('USER1_PASSWORD', 'password'),
                'is_admin': True
            },
            os.getenv('USER2', 'user'): {
                'password': os.getenv('USER2_PASSWORD', 'password'),
                'is_admin': False
            }
        }
    
    app.config['USERS'] = USERS
    
    # 配置目录路径
    app.config['DB_PATH'] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'training_data_qa.db')
    app.config['USER_DB_PATH'] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'user_data.db')
    
    # Vanna配置
    app.config['VANNA_MODEL'] = os.getenv('VANNA_MODEL', 'ollama/gemma:2b-it')
    app.config['VANNA_API_KEY'] = os.getenv('VANNA_API_KEY', 'local')
    
    return app

# 端口配置
def get_port():
    return int(os.getenv('PORT', 5001))

# 调试模式配置
def is_debug_mode():
    # 在生产环境中默认禁用调试模式以增强安全性
    return os.getenv('DEBUG', 'False').lower() == 'true'