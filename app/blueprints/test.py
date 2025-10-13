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

@test_bp.route('/api/debug/fix-prompts', methods=['GET'])
def fix_prompts():
    """
    One-time endpoint to force-initialize and update all default prompts in the database.
    """
    from flask import session, current_app
    from app.core.db_utils import get_user_db_connection
    from app.core.helpers import load_prompt_template
    import sqlite3

    user_id = session.get('username')
    if not user_id:
        return jsonify({'status': 'error', 'message': '用戶未登入'}), 401

    logger.info(f"--- Starting manual prompt fix for user: {user_id} ---")

    default_prompts = {
        'ask_analysis_prompt': 'analysis',
        'qa_generation_system_prompt': 'qa_generation',
        'documentation_prompt': 'documentation',
        'sql_generation_prompt': 'sql_generation',
        'followup_question_generation_prompt': 'followup_question_generation',
        'summary_generation_prompt': 'summary_generation',
        'question_rewriting_prompt': 'question_rewriting',
        'question_generation_from_sql_prompt': 'question_generation_from_sql',
        'plotly_generation_prompt': 'plotly_generation'
    }
    
    updated_count = 0
    inserted_count = 0
    
    try:
        with get_user_db_connection(user_id) as conn:
            cursor = conn.cursor()

            # First, ensure the table exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS training_prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_name TEXT NOT NULL,
                    prompt_content TEXT NOT NULL,
                    prompt_type TEXT,
                    is_global INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_id TEXT,
                    UNIQUE(prompt_name, user_id)
                );
            """)
            logger.info("Ensured 'training_prompts' table exists.")

            for prompt_name, prompt_type in default_prompts.items():
                try:
                    prompt_content = load_prompt_template(prompt_type)
                    
                    # Try to UPDATE first (for existing prompts missing a type)
                    cursor.execute(
                        "UPDATE training_prompts SET prompt_type = ? WHERE prompt_name = ? AND is_global = 1 AND (prompt_type IS NULL OR prompt_type = '')",
                        (prompt_type, prompt_name)
                    )
                    if cursor.rowcount > 0:
                        logger.info(f"Updated existing prompt '{prompt_name}' with type '{prompt_type}'.")
                        updated_count += 1

                    # Check if the global prompt exists
                    cursor.execute("SELECT id FROM training_prompts WHERE prompt_name = ? AND is_global = 1", (prompt_name,))
                    exists = cursor.fetchone()

                    if not exists:
                        # If not, INSERT it
                        cursor.execute(
                            "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, is_global) VALUES (?, ?, ?, ?)",
                            (prompt_name, prompt_content, prompt_type, 1)
                        )
                        logger.info(f"Inserted new default prompt: {prompt_name}")
                        inserted_count += 1

                except Exception as e:
                    logger.error(f"Failed to process prompt '{prompt_name}': {e}")

            conn.commit()
            
        message = f"Prompt fix completed. Updated: {updated_count}, Inserted: {inserted_count}."
        logger.info(f"--- {message} ---")
        return jsonify({'status': 'success', 'message': message})

    except sqlite3.Error as e:
        logger.error(f"Database error during prompt fix: {e}")
        return jsonify({'status': 'error', 'message': f"資料庫錯誤: {e}"}), 500