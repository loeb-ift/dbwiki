#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用工具和装饰器模块
这个模块用于存放不依赖于特定蓝图的通用工具和装饰器
"""
import functools
import logging
from flask import session, redirect, url_for, request, jsonify

# 配置日志
logger = logging.getLogger(__name__)

def login_required(func):
    """\登录装饰器，确保用户已登录
    
    装饰器用于保护需要登录才能访问的路由。如果用户未登录，将重定向到登录页面。
    
    Args:
        func: 被装饰的视图函数
        
    Returns:
        装饰后的函数，如果用户已登录则调用原函数，否则重定向到登录页面
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # 检查用户是否已登录
        if 'username' not in session:
            logger.warning(f"未登录用户尝试访问受保护资源: {request.path}")
            # 判断是否是API请求（以/api/开头）
            if request.path.startswith('/api/'):
                # API请求返回JSON格式的错误
                return jsonify({'status': 'error', 'message': '需要登录'}), 401
            else:
                # 普通页面请求保存当前请求路径，以便登录后重定向回来
                session['next_url'] = request.path
                # 重定向到登录页面
                return redirect(url_for('auth.login'))
        # 用户已登录，调用原函数
        return func(*args, **kwargs)
    return wrapper