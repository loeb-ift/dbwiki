import os
import sys
import logging
import time

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 设置环境变量
os.environ['OLLAMA_HOST'] = 'http://localhost:11434'
os.environ['OLLAMA_MODEL'] = os.getenv('OLLAMA_MODEL', 'llama3')

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

if __name__ == "__main__":
    try:
        logger.info("=== 开始测试Ollama流式输出修复 ===")
        
        # 导入必要的模块
        import sys
        from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request
        from app.core.helpers import load_prompt_template
        
        # 获取Vanna实例
        user_id = "test_user"
        vn = get_vanna_instance(user_id)
        logger.info(f"成功创建Vanna实例，用户ID: {user_id}")
        logger.info(f"Ollama配置: {vn.llm_config}")
        
        # 创建一个简单的测试提示
        test_prompt = [
            {'role': 'system', 'content': '你是一个帮助用户回答问题的助手。请用中文回复。'},
            {'role': 'user', 'content': '请简要介绍一下Ollama是什么？'}
        ]
        
        # 测试非流式输出
        logger.info("\n=== 测试1: 非流式输出 ===")
        start_time = time.time()
        response = vn.submit_prompt(test_prompt, stream=False)
        elapsed_time = time.time() - start_time
        logger.info(f"非流式响应时间: {elapsed_time:.2f}秒")
        logger.info(f"非流式响应内容: {response[:200]}...")
        
        # 测试流式输出
        logger.info("\n=== 测试2: 流式输出 ===")
        start_time = time.time()
        stream = vn.submit_prompt(test_prompt, stream=True)
        logger.info("开始接收流式响应...")
        
        full_response = ""
        chunk_count = 0
        
        try:
            for chunk in stream:
                chunk_count += 1
                logger.info(f"接收到响应块 #{chunk_count}: {chunk[:50]}...")
                full_response += chunk
        except Exception as e:
            logger.error(f"流式处理过程中出错: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
        
        elapsed_time = time.time() - start_time
        logger.info(f"流式响应总时间: {elapsed_time:.2f}秒")
        logger.info(f"接收到 {chunk_count} 个响应块")
        logger.info(f"流式响应完整内容: {full_response[:200]}...")
        
        # 测试真实场景 - 使用documentation模板
        logger.info("\n=== 测试3: 使用documentation模板的流式输出 ===")
        
        # 尝试加载documentation模板
        try:
            doc_template = load_prompt_template('documentation')
            logger.info(f"成功加载documentation模板，前100个字符: {doc_template[:100]}...")
        except Exception as e:
            logger.error(f"加载documentation模板失败: {e}")
            doc_template = "你是一个数据库架构分析专家，可以分析数据库结构并生成技术文档。"
            logger.info(f"使用备用模板: {doc_template}")
        
        # 使用documentation模板进行流式生成
        question = "请简要介绍一下如何分析数据库结构。"
        
        logger.info(f"使用问题: {question}")
        start_time = time.time()
        
        try:
            # 如果vanna_wrapper支持通过generate_sql使用流式输出
            stream = vn.generate_sql(question, initial_prompt=doc_template, stream=True)
            logger.info("开始接收generate_sql的流式响应...")
            
            full_response = ""
            chunk_count = 0
            
            try:
                for chunk in stream:
                    chunk_count += 1
                    logger.info(f"接收到generate_sql响应块 #{chunk_count}: {chunk[:50]}...")
                    full_response += chunk
            except Exception as e:
                logger.error(f"generate_sql流式处理过程中出错: {e}")
                import traceback
                logger.error(f"错误堆栈: {traceback.format_exc()}")
            
            logger.info(f"generate_sql接收到 {chunk_count} 个响应块")
            logger.info(f"generate_sql响应完整内容: {full_response[:200]}...")
            
        except Exception as e:
            logger.error(f"调用generate_sql失败: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            
        elapsed_time = time.time() - start_time
        logger.info(f"generate_sql流式响应总时间: {elapsed_time:.2f}秒")
        
        logger.info("\n=== 测试完成 ===")
        logger.info("修复总结：")
        logger.info("1. 添加了缺少的json模块导入")
        logger.info("2. 删除了干扰流式输出的调试打印代码")
        logger.info("3. 移除了重复的import语句")
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        sys.exit(1)
    
    sys.exit(0)