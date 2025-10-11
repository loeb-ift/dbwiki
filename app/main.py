from flask import Blueprint, session, redirect, url_for, render_template, Response

main = Blueprint('main', __name__)

@main.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('auth.login'))
    return render_template('index.html', username=session.get('username'))

# 处理 @vite/client 请求的路由 - 解决 404 错误
@main.route('/@vite/client')
def vite_client():
    return Response('// Mock Vite client script', mimetype='application/javascript')