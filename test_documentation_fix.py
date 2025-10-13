import os
import logging
import json
import requests
import traceback
from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 设置环境变量
os.environ['OLLAMA_HOST'] = 'http://localhost:11434'
os.environ['OLLAMA_MODEL'] = 'gpt-oss:20b'

# 首先检查并修复default_prompts.json中的全角符号问题
def fix_documentation_prompt():
    """检查并修复default_prompts.json中的全角符号问题"""
    try:
        prompts_path = os.path.join(os.getcwd(), 'prompts', 'default_prompts.json')
        
        if not os.path.exists(prompts_path):
            logger.error(f"default_prompts.json文件未找到: {prompts_path}")
            return False
        
        # 读取文件
        with open(prompts_path, 'r', encoding='utf-8') as f:
            prompts = json.load(f)
        
        # 检查documentation模板
        if 'documentation' not in prompts:
            logger.warning("documentation模板未在default_prompts.json中找到")
            return False
        
        doc_template = prompts['documentation']
        full_width_at = '＠'  # 全角@符号
        
        # 检查是否存在全角符号
        if full_width_at in doc_template:
            logger.info(f"在documentation模板中发现全角符号 '{full_width_at}'")
            
            # 修复全角符号
            fixed_template = doc_template.replace(full_width_at, '@')
            
            # 写回文件
            prompts['documentation'] = fixed_template
            with open(prompts_path, 'w', encoding='utf-8') as f_out:
                json.dump(prompts, f_out, ensure_ascii=False, indent=2)
            
            logger.info(f"成功修复全角符号，已替换为半角符号 '@'")
            return True
        else:
            logger.info("documentation模板中未发现全角符号")
            return True
    except Exception as e:
        logger.error(f"修复documentation模板时出错: {e}")
        logger.error(traceback.format_exc())
        return False

# 测试Ollama连接
def test_ollama_connection():
    """测试Ollama连接是否正常"""
    try:
        ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        logger.info(f"正在测试Ollama连接: {ollama_host}")
        
        response = requests.get(f"{ollama_host}/api/tags", timeout=5)
        if response.status_code == 200:
            logger.info("成功连接到Ollama!")
            models = response.json()
            logger.info(f"可用模型: {[model['name'] for model in models.get('models', [])][:5]}")
            return True
        else:
            logger.error(f"Ollama连接失败，状态码: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Ollama连接测试出错: {e}")
        return False

# 主测试函数
def main():
    # 1. 修复documentation模板
    if not fix_documentation_prompt():
        logger.error("无法修复documentation模板，测试终止")
        return
    
    # 2. 测试Ollama连接
    if not test_ollama_connection():
        logger.error("Ollama连接失败，测试终止")
        return
    
    # 3. 获取Vanna实例，但不依赖于特定数据集
    try:
        user_id = 'user1'
        vn = get_vanna_instance(user_id)
        
        # 手动配置基本参数，不依赖于数据集
        vn.user_id = user_id
        vn.llm_config = {
            'ollama_model': os.getenv('OLLAMA_MODEL'),
            'ollama_host': os.getenv('OLLAMA_HOST', 'http://localhost:11434'),
        }
        
        logger.info("成功获取并配置Vanna实例（不依赖特定数据集）")
    except Exception as e:
        logger.error(f"获取Vanna实例失败: {e}")
        logger.error(traceback.format_exc())
        return
    
    # 4. 测试生成文档的功能
    try:
        logger.info("开始测试generate_sql功能，使用修复后的documentation模板...")
        
        # 尝试从修复后的default_prompts.json加载模板
        with open(os.path.join(os.getcwd(), 'prompts', 'default_prompts.json'), 'r', encoding='utf-8') as f:
            prompts = json.load(f)
        
        doc_template = prompts.get('documentation', '')
        logger.info(f"加载的模板内容前100个字符: {doc_template[:100] if len(doc_template)>=100 else doc_template}")
        
        # 生成文档
        question = "请根据您所知道的所有关于此数据库的上下文（DDL, 文件, 问答范例），生成一份全面的技术文件，详细描述其架构、业务逻辑和查询模式。"
        
        # 使用stream=True参数流式接收结果
        stream = vn.generate_sql(question, initial_prompt=doc_template, stream=True)
        
        logger.info("正在接收AI模型响应...")
        result = ""
        
        # 尝试接收至少一个响应块来验证修复是否成功
        for chunk in stream:
            logger.info(f"接收到响应块: {chunk[:50]}...")
            result += chunk
            # 为了避免生成过长内容，只接收前几个块
            if len(result) > 200:
                break
        
        if result:
            logger.info(f"测试成功完成! 成功接收到响应内容，长度: {len(result)} 字符")
            
            # 将结果保存到文件以便查看
            with open('test_documentation_result.txt', 'w', encoding='utf-8') as f:
                f.write(result)
            logger.info("生成的文档已保存到test_documentation_result.txt")
        else:
            logger.warning("未接收到响应内容")
            
    except Exception as e:
        logger.error(f"测试失败: {e}")
        logger.error(traceback.format_exc())
        # 特殊处理"The string did not match the expected pattern"错误
        if "The string did not match the expected pattern" in str(e):
            logger.error("检测到模式匹配错误，这可能表示Ollama API调用中存在格式问题")
            logger.error("请检查所有提示模板中是否还有其他全角符号或格式问题")

if __name__ == "__main__":
    main()