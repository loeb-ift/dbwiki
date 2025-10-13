#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试Ollama连接问题的脚本
"""
import os
import sys
import logging
import requests
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ollama_test')

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# 1. 检查环境变量
logger.info("=== 检查Ollama环境变量 ===")
ollama_host = os.getenv('OLLAMA_HOST', '未设置')
ollama_model = os.getenv('OLLAMA_MODEL', '未设置')
logger.info(f"OLLAMA_HOST: {ollama_host}")
logger.info(f"OLLAMA_MODEL: {ollama_model}")
logger.info(f"OLLAMA_NUM_CTX: {os.getenv('OLLAMA_NUM_CTX', '未设置')}")

# 2. 测试Ollama服务器连接
def test_ollama_connection():
    """测试Ollama服务器连接是否正常"""
    logger.info("\n=== 测试Ollama服务器连接 ===")
    try:
        if ollama_host == '未设置':
            logger.warning("OLLAMA_HOST未设置，使用默认值测试")
            test_host = "http://localhost:11434"
        else:
            test_host = ollama_host
        
        # 测试API连接
        url = f"{test_host}/api/tags"
        logger.info(f"正在测试连接到: {url}")
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            logger.info(f"✅ 成功连接到Ollama服务器！状态码: {response.status_code}")
            try:
                models = response.json().get('models', [])
                logger.info(f"服务器上可用的模型数量: {len(models)}")
                # 检查配置的模型是否存在
                if ollama_model != '未设置':
                    model_found = any(m.get('name') == ollama_model for m in models)
                    if model_found:
                        logger.info(f"✅ 模型 '{ollama_model}' 存在于服务器上")
                    else:
                        logger.warning(f"⚠️ 模型 '{ollama_model}' 不存在于服务器上")
            except Exception as e:
                logger.error(f"解析响应JSON时出错: {e}")
        else:
            logger.error(f"❌ 连接Ollama服务器失败，状态码: {response.status_code}")
            logger.error(f"响应内容: {response.text}")
    except requests.ConnectionError:
        logger.error(f"❌ 无法连接到Ollama服务器: {test_host}")
        logger.error("请确认Ollama服务正在运行，并且主机地址正确")
    except requests.Timeout:
        logger.error(f"❌ 连接Ollama服务器超时: {test_host}")
    except Exception as e:
        logger.error(f"❌ 连接Ollama服务器时发生未知错误: {e}")

# 3. 尝试创建MyVanna实例并调用submit_prompt
def test_vanna_ollama():
    """测试MyVanna与Ollama的集成"""
    logger.info("\n=== 测试MyVanna与Ollama集成 ===")
    try:
        from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request
        
        # 创建测试用户ID
        test_user_id = "test_user"
        logger.info(f"创建MyVanna实例，用户ID: {test_user_id}")
        vn = get_vanna_instance(test_user_id)
        
        # 打印MyVanna实例的Ollama配置
        logger.info(f"MyVanna LLM配置: {vn.llm_config}")
        
        # 检查是否使用了Ollama
        if hasattr(vn, 'llm_choice'):
            logger.info(f"MyVanna LLM选择: {vn.llm_choice}")
            if vn.llm_choice != 'ollama':
                logger.warning(f"⚠️ MyVanna选择的LLM不是Ollama，而是: {vn.llm_choice}")
                return
        else:
            logger.info("MyVanna实例没有llm_choice属性，继续测试")
            
        # 创建一个简单的prompt进行测试
        test_prompt = [
            {'role': 'system', 'content': '你是一个SQL助手，将SQL转换为自然语言问题。'}, 
            {'role': 'user', 'content': 'SELECT COUNT(*) FROM users;'}
        ]
        
        logger.info("尝试调用submit_prompt方法...")
        response = vn.submit_prompt(test_prompt)
        logger.info(f"✅ submit_prompt调用成功！")
        logger.info(f"响应内容: {response}")
        
    except ImportError as e:
        logger.error(f"❌ 导入MyVanna相关模块时出错: {e}")
    except Exception as e:
        logger.error(f"❌ 测试MyVanna与Ollama集成时发生错误: {e}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")

if __name__ == '__main__':
    # 运行测试
    test_ollama_connection()
    test_vanna_ollama()
    
    # 提供诊断建议
    logger.info("\n=== 诊断建议 ===")
    if ollama_host == '未设置' or ollama_model == '未设置':
        logger.warning("1. 请确保.env文件中正确设置了OLLAMA_HOST和OLLAMA_MODEL")
    
    logger.info("2. 确保Ollama服务正在运行，并且可以从当前网络访问")
    logger.info("3. 检查OLLAMA_HOST是否包含正确的协议(http://)和端口号")
    logger.info("4. 验证配置的模型是否已在Ollama服务器上拉取")
    logger.info("5. 如果使用的是远程服务器，请确保网络连接正常且防火墙已配置")
    
    logger.info("\n测试完成。根据上述结果可以确定Ollama连接问题的原因。")