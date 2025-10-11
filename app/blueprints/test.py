from flask import Blueprint, jsonify
import logging

# 创建测试blueprint
test_bp = Blueprint('test', __name__)

# 创建logger
logger = logging.getLogger(__name__)

@test_bp.route('/api/test_ollama', methods=['GET'])
def test_ollama():
    """测试Ollama连接的端点"""
    try:
        from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request
        import os
        
        # 使用默认的测试用户
        user_id = 'user1'
        dataset_id = os.getenv('TEST_DATASET_ID', '1')
        
        # 获取vanna实例并配置
        vn = get_vanna_instance(user_id)
        vn = configure_vanna_for_request(vn, user_id, dataset_id)
        
        # 准备测试提示词
        test_prompt = "你好，这是一个测试消息"
        
        # 记录详细信息
        logger.info(f"=== 开始测试Ollama连接 ===")
        logger.info(f"使用用户: {user_id}")
        logger.info(f"使用数据集ID: {dataset_id}")
        logger.info(f"使用LLM: {vn.llm_choice}")
        if vn.llm_choice == 'ollama':
            logger.info(f"Ollama模型: {vn.llm_config.get('ollama_model')}")
            logger.info(f"Ollama主机: {vn.llm_config.get('ollama_host')}")
        
        # 尝试调用Ollama
        logger.info(f"尝试直接调用Ollama, 提示词格式: {type(test_prompt)}")
        # 先尝试直接调用，如果失败则尝试包装成消息格式
        try:
            response = vn.submit_prompt(test_prompt)
        except Exception as e:
            logger.warning(f"直接调用失败，尝试包装成消息格式: {str(e)}")
            # 尝试包装成标准的消息格式
            messages = [{"role": "user", "content": test_prompt}]
            logger.info(f"尝试使用消息格式: {type(messages)}, 长度: {len(messages)}")
            response = vn.submit_prompt(messages)
        
        logger.info(f"=== Ollama测试成功 ===")
        logger.info(f"响应类型: {type(response)}")
        logger.info(f"响应长度: {len(str(response))} 字符")
        
        return jsonify({
            'status': 'success',
            'message': 'Ollama连接测试成功',
            'response': str(response)[:200]  # 只返回前200个字符
        })
    except Exception as e:
        logger.error(f"=== Ollama测试失败 ===")
        logger.error(f"错误类型: {type(e).__name__}")
        logger.error(f"错误消息: {str(e)}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500