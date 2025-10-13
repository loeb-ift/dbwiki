import os
import sys
import logging
import time
import json
import requests
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test_ollama_direct_streaming')

def main():
    """专门测试Ollama的流式输出功能"""
    logger.info("=== 开始Ollama流式输出直接测试 ===")
    
    # 从环境变量获取Ollama配置
    ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
    ollama_model = os.getenv('OLLAMA_MODEL', 'gpt-oss:20b')
    logger.info(f"使用Ollama配置: 主机={ollama_host}, 模型={ollama_model}")
    
    try:
        # 测试直接使用Ollama API的流式输出
        test_ollama_api_streaming(ollama_host, ollama_model)
        
        # 测试通过Python生成器消费流式响应
        test_generator_handling(ollama_host, ollama_model)
        
        logger.info("=== Ollama流式输出直接测试完成 ===")
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")

def test_ollama_api_streaming(ollama_host, ollama_model):
    """直接测试Ollama API的流式输出功能"""
    logger.info("\n=== 直接测试Ollama API的流式输出 ===")
    try:
        url = f"{ollama_host}/api/chat"
        payload = {
            "model": ollama_model,
            "messages": [
                {"role": "user", "content": "请简要介绍流式输出的工作原理。"}
            ],
            "stream": True
        }
        
        logger.info(f"发送流式请求到: {url}")
        start_time = time.time()
        
        # 使用stream=True来获取流式响应
        with requests.post(url, json=payload, stream=True, timeout=30) as response:
            if response.status_code == 200:
                logger.info(f"成功连接到Ollama API，开始接收流式响应...")
                
                # 逐块处理响应
                full_response = ""
                chunk_count = 0
                
                for chunk in response.iter_lines():
                    if chunk:
                        chunk_count += 1
                        # 解码块内容
                        try:
                            chunk_data = json.loads(chunk.decode('utf-8'))
                            if 'message' in chunk_data and 'content' in chunk_data['message']:
                                content = chunk_data['message']['content']
                                full_response += content
                                logger.info(f"收到块 {chunk_count}: {content[:50]}...")
                        except json.JSONDecodeError as e:
                            logger.error(f"无法解析块 {chunk_count} 为JSON格式: {e}")
                            logger.error(f"原始块内容: {chunk}")
                
                end_time = time.time()
                logger.info(f"流式响应接收完成，共收到 {chunk_count} 个块")
                logger.info(f"总响应长度: {len(full_response)} 字符")
                logger.info(f"总耗时: {end_time - start_time:.2f} 秒")
                logger.info(f"完整响应示例: {full_response[:100]}...")
            else:
                logger.error(f"Ollama API返回错误状态码: {response.status_code}")
                logger.error(f"响应内容: {response.text}")
    except Exception as e:
        logger.error(f"测试Ollama API流式输出时发生错误: {e}")

def test_generator_handling(ollama_host, ollama_model):
    """测试通过Python生成器消费Ollama的流式响应"""
    logger.info("\n=== 测试通过Python生成器消费流式响应 ===")
    
    def stream_generator():
        """模拟Ollama.submit_prompt中返回的生成器函数"""
        url = f"{ollama_host}/api/chat"
        payload = {
            "model": ollama_model,
            "messages": [
                {"role": "user", "content": "什么是数据库索引？请简单解释。"}
            ],
            "stream": True
        }
        
        try:
            with requests.post(url, json=payload, stream=True, timeout=30) as response:
                if response.status_code == 200:
                    for chunk in response.iter_lines():
                        if chunk:
                            try:
                                chunk_data = json.loads(chunk.decode('utf-8'))
                                if 'message' in chunk_data and 'content' in chunk_data['message']:
                                    yield chunk_data['message']['content']
                            except Exception as e:
                                logger.error(f"处理块时出错: {e}")
                else:
                    logger.error(f"Ollama API返回错误状态码: {response.status_code}")
        except Exception as e:
            logger.error(f"生成器中发生错误: {e}")
    
    # 获取生成器对象
    logger.info("获取生成器对象...")
    generator = stream_generator()
    logger.info(f"生成器对象类型: {type(generator)}")
    logger.info(f"这是与用户看到的类似的生成器对象: <generator object stream_generator at {hex(id(generator))}>")
    
    # 消费生成器（限制为5个块）
    logger.info("开始消费生成器...")
    chunk_count = 0
    max_chunks = 5
    full_content = ""
    
    try:
        for chunk in generator:
            chunk_count += 1
            full_content += chunk
            logger.info(f"生成器块 {chunk_count}: {chunk[:50]}...")
            
            if chunk_count >= max_chunks:
                logger.info(f"已达到最大块数 ({max_chunks})，停止消费")
                break
    except Exception as e:
        logger.error(f"消费生成器时发生错误: {e}")
    
    logger.info(f"生成器消费完成，收到 {chunk_count} 个块")
    logger.info(f"累计内容长度: {len(full_content)} 字符")
    logger.info(f"生成器对象在消费后仍然有效，可以继续迭代获取更多内容")

if __name__ == '__main__':
    main()