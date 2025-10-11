from flask import Blueprint, render_template, request, redirect, url_for, session, current_app
from app.core.db_utils import init_training_db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Access users from the application config
        users = current_app.config.get('USERS', {})
        
        # Check if user exists
        if username in users:
            # Handle both formats: {username: password} and {username: {password: '...', is_admin: ...}}
            if isinstance(users[username], dict) and 'password' in users[username]:
                password_correct = (users[username]['password'] == password)
                is_admin = users[username].get('is_admin', False)
            else:
                password_correct = (users[username] == password)
                is_admin = False  # Default to not admin if using simple format
                
            if password_correct:
                session['username'] = username
                session['is_admin'] = is_admin
                
                # 自动选择默认数据集（如果未设置）
                if 'active_dataset' not in session:
                    # 使用默认数据集ID 'training_data_qa'
                    session['active_dataset'] = 'training_data_qa'
                
                init_training_db(username)
                return redirect(url_for('main.index'))
        
        return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    # 完全清除所有会话数据
    session.clear()
    return redirect(url_for('auth.login'))