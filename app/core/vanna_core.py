import os
import re
import pandas as pd
from queue import Queue
import logging
from sqlalchemy import create_engine, inspect, text
import sqlite3
import ollama
from flask import current_app as app

import logging
# 配置日志记录器
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Add 'src' to Python path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))

from vanna.ollama import Ollama
from vanna.openai import OpenAI_Chat
from vanna.anthropic import Anthropic_Chat
from vanna.google import GoogleGeminiChat
from vanna.chromadb import ChromaDB_VectorStore

from ..core.db_utils import get_user_db_connection
from ..core.helpers import write_ask_log

class MyVanna(ChromaDB_VectorStore):
    def __init__(self, user_id: str, config=None):
        # 使用logger而不是app.logger，因为初始化可能在应用程序上下文外进行
        logger.info(f"Initializing MyVanna instance for user: {user_id}")
        self.log_queue = Queue()
        self.user_id = user_id
        self.config = config or {}
        self.llm_choice = None
        self.llm_instance = None
        self.db_schema_info = None  # 存储数据库结构信息
        self.run_sql_is_set = False

        # Determine which LLM to use based on environment variables
        self.llm_choice = self._get_llm_choice()
        
        # Store LLM configuration without instantiating abstract classes
        self.llm_config = {
            'ollama_model': os.getenv('OLLAMA_MODEL'),
            'ollama_host': os.getenv('OLLAMA_HOST', 'http://host.docker.internal:11434'),
            'openai_api_key': os.getenv('OPENAI_API_KEY'),
            'openai_model': os.getenv('OPENAI_MODEL', 'gpt-4-turbo'),
            'anthropic_api_key': os.getenv('ANTHROPIC_API_KEY'),
            'anthropic_model': os.getenv('ANTHROPIC_MODEL', 'claude-3-opus-20240229'),
            'google_api_key': os.getenv('GOOGLE_API_KEY'),
            'google_model': os.getenv('GOOGLE_MODEL', 'gemini-1.5-pro-latest'),
        }
        
        # Log LLM choice
        if self.llm_choice == 'openai':
            logger.info(f"Using OpenAI for user: {user_id} with model: {self.llm_config['openai_model']}")
        elif self.llm_choice == 'ollama':
            logger.info(f"Using Ollama for user: {user_id} with model: {self.llm_config['ollama_model']}, host: {self.llm_config['ollama_host']}")
        elif self.llm_choice == 'anthropic':
            logger.info(f"Using Anthropic for user: {user_id} with model: {self.llm_config['anthropic_model']}")
        elif self.llm_choice == 'google':
            logger.info(f"Using Google Gemini for user: {user_id} with model: {self.llm_config['google_model']}")
        else:
            logger.warning(f"Unknown LLM choice: {self.llm_choice}")

        collection_name = f"vanna_training_data_{user_id}"
        self.config['collection_name'] = collection_name
        
        # Initialize parent class
        logger.info(f"Initializing ChromaDB_VectorStore for user: {user_id} with collection: {collection_name}")
        ChromaDB_VectorStore.__init__(self, config=self.config)

        # Store original methods to call them and log their results
        self._original_get_similar_question_sql = super().get_similar_question_sql
        self._original_get_related_ddl = super().get_related_ddl
        self._original_get_related_documentation = super().get_related_documentation

    # Implement abstract methods required by VannaBase
    def system_message(self, message: str) -> any:
        return {'role': 'system', 'content': message}

    def user_message(self, message: str) -> any:
        return {'role': 'user', 'content': message}

    def assistant_message(self, message: str) -> any:
        return {'role': 'assistant', 'content': message}

    def submit_prompt(self, prompt, **kwargs) -> str:
        if self.llm_choice == 'openai':
            from vanna.openai import OpenAI_Chat
            self.config['api_key'] = self.llm_config['openai_api_key']
            self.config['model'] = self.llm_config['openai_model']
            try:
                openai_chat = OpenAI_Chat(config=self.config)
                return openai_chat.submit_prompt(prompt, **kwargs)
            except Exception as e:
                logger.error(f"Error with OpenAI_Chat: {e}")
                raise
        elif self.llm_choice == 'ollama':
            try:
                # 设置Ollama配置
                ollama_config = {
                    'model': self.llm_config['ollama_model'],
                    'ollama_host': self.llm_config['ollama_host'],
                    'ollama_timeout': 240.0,
                    'keep_alive': None,
                    'options': {
                        'num_ctx': int(os.getenv('OLLAMA_NUM_CTX', 16384))
                    }
                }
                
                # 合并原有的配置
                ollama_config.update(self.config)
                
                logger.info(f"Initializing Ollama with config: {ollama_config}")
                
                # Ollama类是抽象类，需要实现多个向量相关的抽象方法
                # 创建一个临时类，同时继承Ollama和ChromaDB_VectorStore
                # 这样就能同时获得Ollama的LLM功能和ChromaDB_VectorStore的向量存储功能
                from vanna.ollama import Ollama
                from vanna.chromadb import ChromaDB_VectorStore
                
                # 创建临时组合类
                class OllamaWithVectorStore(Ollama, ChromaDB_VectorStore):
                    def __init__(self, config=None):
                        ChromaDB_VectorStore.__init__(self, config=config)
                        Ollama.__init__(self, config=config)
                
                # 实例化这个临时组合类
                ollama_instance = OllamaWithVectorStore(config=ollama_config)
                
                logger.info(f"Ollama实例创建成功，准备提交提示词")
                logger.info(f"提交的提示词类型: {type(prompt)}")
                
                # 处理不同类型的提示词
                if isinstance(prompt, list) and all(isinstance(item, dict) for item in prompt):
                    logger.info(f"提示词是消息数组格式，包含 {len(prompt)} 条消息")
                    # 记录每条消息的角色和内容预览
                    for i, msg in enumerate(prompt):
                        role = msg.get('role', 'unknown')
                        content_preview = msg.get('content', '')[:50] if len(msg.get('content', '')) > 50 else msg.get('content', '')
                        logger.info(f"消息 {i+1}/{len(prompt)}: 角色={role}, 内容预览={content_preview}...")
                elif isinstance(prompt, str):
                    logger.info(f"提示词长度: {len(prompt)} 字符")
                    prompt_preview = prompt[:100] if len(prompt) > 100 else prompt
                    logger.info(f"提示词预览: {prompt_preview}...")
                else:
                    logger.info(f"提示词格式: {type(prompt)}")
                
                # 尝试提交提示词
                response = ollama_instance.submit_prompt(prompt, **kwargs)
                logger.info(f"Ollama response received (length: {len(response)} characters)")
                logger.info(f"Ollama response content preview: {response[:100] if len(response) > 100 else response}")
                return response
            except Exception as e:
                logger.error(f"Error with Ollama: {e}")
                # 记录详细的错误信息，包括堆栈跟踪
                import traceback
                logger.error(f"Stack trace: {traceback.format_exc()}")
                # 在控制台也打印错误信息，确保能看到
                print(f"[CRITICAL ERROR] Ollama connection failed: {e}")
                print(f"[TRACEBACK] {traceback.format_exc()}")
                raise
        elif self.llm_choice == 'anthropic':
            from vanna.anthropic import Anthropic_Chat
            self.config['api_key'] = self.llm_config['anthropic_api_key']
            self.config['model'] = self.llm_config['anthropic_model']
            try:
                anthropic_chat = Anthropic_Chat(config=self.config)
                return anthropic_chat.submit_prompt(prompt, **kwargs)
            except Exception as e:
                logger.error(f"Error with Anthropic_Chat: {e}")
                raise
        elif self.llm_choice == 'google':
            from vanna.google import GoogleGeminiChat
            self.config['api_key'] = self.llm_config['google_api_key']
            self.config['model'] = self.llm_config['google_model']
            try:
                google_chat = GoogleGeminiChat(config=self.config)
                return google_chat.submit_prompt(prompt, **kwargs)
            except Exception as e:
                logger.error(f"Error with GoogleGeminiChat: {e}")
                raise
        else:
            raise ValueError(f"Unsupported LLM choice: {self.llm_choice}")

    def add_ddl(self, ddl: str, **kwargs) -> str:
        log_message_calling = f"Calling add_ddl with ddl length: {len(ddl)} characters"
        logger.info(log_message_calling)
        write_ask_log(self.user_id, "add_ddl_calling", log_message_calling)
        self.log_queue.put({'type': 'training_step', 'step': '開始添加 DDL', 'details': {'ddl_length': len(ddl)}})
        result = super().add_ddl(ddl, **kwargs)
        log_message_results = f"add_ddl completed with result: {result}"
        logger.info(log_message_results)
        write_ask_log(self.user_id, "add_ddl_completed", log_message_results)
        self.log_queue.put({'type': 'training_step', 'step': 'DDL 添加完成', 'details': {'id': result}})
        return result

    def add_documentation(self, documentation: str, **kwargs) -> str:
        log_message_calling = f"Calling add_documentation with documentation length: {len(documentation)} characters"
        logger.info(log_message_calling)
        write_ask_log(self.user_id, "add_documentation_calling", log_message_calling)
        self.log_queue.put({'type': 'training_step', 'step': '開始添加文件', 'details': {'doc_length': len(documentation)}})
        result = super().add_documentation(documentation, **kwargs)
        log_message_results = f"add_documentation completed with result: {result}"
        logger.info(log_message_results)
        write_ask_log(self.user_id, "add_documentation_completed", log_message_results)
        self.log_queue.put({'type': 'training_step', 'step': '文件添加完成', 'details': {'id': result}})
        return result

    def add_question_sql(self, question: str, sql: str, **kwargs) -> str:
        log_message_calling = f"Calling add_question_sql with question: '{question[:50]}...', sql: '{sql[:50]}...'"
        logger.info(log_message_calling)
        write_ask_log(self.user_id, "add_question_sql_calling", log_message_calling)
        self.log_queue.put({'type': 'training_step', 'step': '開始添加問答配對', 'details': {'question_preview': question[:50], 'sql_preview': sql[:50]}})
        result = super().add_question_sql(question, sql, **kwargs)
        log_message_results = f"add_question_sql completed with result: {result}"
        logger.info(log_message_results)
        write_ask_log(self.user_id, "add_question_sql_completed", log_message_results)
        self.log_queue.put({'type': 'training_step', 'step': '問答配對添加完成', 'details': {'id': result}})
        return result
        
    def _get_original_generate_sql(self):
        if not hasattr(self, '_original_generate_sql'):
            self._original_generate_sql = super().generate_sql
        return self._original_generate_sql

    def get_similar_question_sql(self, question: str, **kwargs):
        top_n = kwargs.pop('top_n', 5)
        log_message_calling = f"Calling get_similar_question_sql with question: '{question}', top_n: {top_n}"
        logger.info(log_message_calling)
        write_ask_log(self.user_id, "get_similar_question_sql_calling", log_message_calling)
        self.log_queue.put({'type': 'thinking_step', 'step': '開始相似問題檢索', 'details': {'question': question, 'top_n': top_n}})
        results = self._original_get_similar_question_sql(question, top_n=top_n, **kwargs)
        log_message_results = f"get_similar_question_sql raw results: {results}"
        logger.info(log_message_results)
        write_ask_log(self.user_id, "get_similar_question_sql_results", log_message_results)
        self.log_queue.put({'type': 'thinking_step', 'step': '相似問題檢索完成', 'details': results})
        return results

    def get_related_ddl(self, question: str, **kwargs):
        top_n = kwargs.pop('top_n', 5)
        log_message_calling = f"Calling get_related_ddl with question: '{question}', top_n: {top_n}"
        logger.info(log_message_calling)
        write_ask_log(self.user_id, "get_related_ddl_calling", log_message_calling)
        self.log_queue.put({'type': 'thinking_step', 'step': '開始 DDL 檢索', 'details': {'question': question, 'top_n': top_n}})
        results = self._original_get_related_ddl(question, top_n=top_n, **kwargs)
        log_message_results = f"get_related_ddl raw results: {results}"
        logger.info(log_message_results)
        write_ask_log(self.user_id, "get_related_ddl_results", log_message_results)
        self.log_queue.put({'type': 'thinking_step', 'step': 'DDL 檢索完成', 'details': results})
        return results

    def get_related_documentation(self, question: str, **kwargs):
        top_n = kwargs.pop('top_n', 5)
        log_message_calling = f"Calling get_related_documentation with question: '{question}', top_n: {top_n}"
        logger.info(log_message_calling)
        write_ask_log(self.user_id, "get_related_documentation_calling", log_message_calling)
        self.log_queue.put({'type': 'thinking_step', 'step': '開始文件檢索', 'details': {'question': question, 'top_n': top_n}})
        results = self._original_get_related_documentation(question, top_n=top_n, **kwargs)
        log_message_results = f"get_related_documentation raw results: {results}"
        logger.info(log_message_results)
        write_ask_log(self.user_id, "get_related_documentation_results", log_message_results)
        self.log_queue.put({'type': 'thinking_step', 'step': '文件檢索完成', 'details': results})
        return results

    def generate_sql(self, question: str, **kwargs):
        # 增强的SQL生成逻辑，使用数据库结构信息
        try:
            logger.info(f"生成SQL查询 - 问题: {question}")
            self.log_queue.put({'type': 'thinking_step', 'step': 'LLM 開始生成 SQL', 'details': {'question': question}})
            
            # 检查是否有数据库结构信息
            if hasattr(self, 'db_schema_info') and self.db_schema_info:
                logger.info(f"使用数据库结构信息生成SQL，信息长度: {len(self.db_schema_info)} 字符")
                
                # 构建包含数据库结构信息的提示词
                prompt_text = f"""
你需要根据以下数据库结构信息，为用户的问题生成SQL查询语句：

{self.db_schema_info}

用户问题：{question}

请按照以下要求生成SQL：
1. 只返回纯SQL查询语句，不要包含任何解释或说明
2. SQL语句必须可以在SQLite数据库中执行
3. 确保查询逻辑与用户问题完全匹配
4. 不要返回任何Markdown格式或其他非SQL内容
"""
                
                # 格式化为Ollama期望的消息列表格式
                prompt_messages = [
                    {'role': 'system', 'content': '你是一个SQL查询生成助手，能够根据数据库结构和用户问题生成准确的SQL查询。'},
                    {'role': 'user', 'content': prompt_text}
                ]
                
                # 直接调用submit_prompt方法生成SQL
                sql_result = self.submit_prompt(prompt_messages)
                
                # 清理SQL响应，去除可能的格式标记
                if isinstance(sql_result, str):
                    # 移除Markdown代码块标记
                    sql_result = sql_result.replace('```sql', '').replace('```', '').strip()
                    # 移除可能的前缀文本
                    if sql_result.lower().startswith('sql:'):
                        sql_result = sql_result[4:].strip()
                    # 移除可能的开头和结尾空白字符
                    sql_result = sql_result.strip()
                    
                    # 确保返回的是纯SQL语句
                    if not sql_result.upper().startswith(('SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE')):
                        logger.warning(f"生成的内容不是有效的SQL: {sql_result[:50]}...")
                        # 如果不是有效的SQL，尝试从内容中提取SQL
                        sql_match = re.search(r'(SELECT|WITH|INSERT|UPDATE|DELETE)\b.*?(?=\n\n|$)', sql_result, re.DOTALL | re.IGNORECASE)
                        if sql_match:
                            sql_result = sql_match.group(0).strip()
                            logger.info(f"已提取SQL: {sql_result[:50]}...")
                        else:
                            logger.error("无法从生成内容中提取SQL")
                
                logger.info(f"成功生成SQL: {sql_result[:100]}...")
            else:
                logger.warning("没有可用的数据库结构信息，使用原始的SQL生成方法")
                # 获取原始的generate_sql方法
                self._get_original_generate_sql()
                # 直接调用原始方法
                sql_result = self._original_generate_sql(question, **kwargs)
                
            self.log_queue.put({'type': 'thinking_step', 'step': 'LLM 完成生成 SQL', 'details': {'sql_response': sql_result[:100] + '...' if len(sql_result) > 100 else sql_result}})
            return sql_result
        except Exception as e:
            logger.error(f"SQL生成失败: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            # 记录错误到log_queue
            self.log_queue.put({'type': 'error', 'step': 'SQL生成失败', 'details': {'error': str(e)}})
            # 返回一个明确的错误信息，而不是抛出异常
            return f"-- SQL生成失败: {str(e)}"

    def _get_llm_choice(self):
        if os.getenv('OLLAMA_MODEL'):
            return 'ollama'
        elif os.getenv('OPENAI_API_KEY'):
            return 'openai'
        elif os.getenv('ANTHROPIC_API_KEY'):
            return 'anthropic'
        elif os.getenv('GOOGLE_API_KEY'):
            return 'google'
        else:
            return 'openai'

    def log(self, message: str, title: str = "資訊"):
        self.log_queue.put({'type': 'thinking_step', 'step': title, 'details': {'message': message}})

_vanna_instances = {}
def get_vanna_instance(user_id: str) -> MyVanna:
    if user_id not in _vanna_instances:
        # 在请求处理中调用此函数时，app应该已经在上下文中
        logger.info(f"Creating new MyVanna instance for user: {user_id}")
        _vanna_instances[user_id] = MyVanna(user_id=user_id)
    else:
        logger.info(f"Reusing existing MyVanna instance for user: {user_id}")
    return _vanna_instances[user_id]

def configure_vanna_for_request(vn, user_id, dataset_id):
    if not dataset_id:
        raise Exception("No active dataset selected.")
    
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
    if not row:
        raise Exception("Active dataset not found.")
    
    engine = create_engine(f"sqlite:///{row[0]}")
    vn.engine = engine
    
    # 1. 获取数据库表结构信息
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    # 收集表结构信息和示例数据
    db_schema_info = []
    
    for table_name in table_names:
        # 获取表的列信息
        columns = inspector.get_columns(table_name)
        column_info = [f"{col['name']} {col['type']}" for col in columns]
        
        # 获取前几行数据作为示例
        try:
            with engine.connect() as connection:
                sample_query = text(f"SELECT * FROM {table_name} LIMIT 3")
                sample_result = connection.execute(sample_query)
                sample_rows = sample_result.fetchall()
                
                # 构建表信息字符串
                table_info = f"表名: {table_name}\n"
                table_info += f"列: {', '.join(column_info)}\n"
                
                if sample_rows:
                    table_info += "示例数据:\n"
                    for i, row_data in enumerate(sample_rows):
                        table_info += f"  行 {i+1}: {row_data}\n"
                else:
                    table_info += "示例数据: 暂无数据\n"
                
                db_schema_info.append(table_info)
        except Exception as e:
            logger.warning(f"无法获取表 {table_name} 的示例数据: {e}")
            # 即使获取示例数据失败，也添加表结构信息
            table_info = f"表名: {table_name}\n"
            table_info += f"列: {', '.join(column_info)}\n"
            table_info += "示例数据: 无法获取\n"
            db_schema_info.append(table_info)
    
    # 保存数据库结构信息到Vanna实例
    vn.db_schema_info = "\n\n".join(db_schema_info)
    logger.info(f"已收集数据库结构信息，包含 {len(table_names)} 个表")
    
    # 2. 增强run_sql函数，添加日志记录功能
    def enhanced_run_sql(sql):
        try:
            logger.info(f"Executing SQL query for user {user_id}: {sql[:100]}...")
            df = pd.read_sql_query(sql, engine)
            
            # 记录SQL执行结果信息
            if df.empty:
                empty_message = f"SQL query returned empty result: {sql}"
                logger.info(empty_message)
                vn.log(empty_message, "警告")
                vn.log_queue.put({'type': 'warning', 'message': empty_message, 'sql': sql})
                write_ask_log(user_id, "empty_sql_result", empty_message)
            else:
                logger.info(f"SQL query returned {len(df)} rows of data")
                vn.log(f"SQL 查询返回 {len(df)} 行数据", "資訊")
                
            return df
        except Exception as e:
            error_message = f"SQL execution error: {str(e)}"
            logger.error(error_message)
            vn.log(error_message, "錯誤")
            vn.log_queue.put({'type': 'error', 'message': error_message, 'sql': sql})
            write_ask_log(user_id, "sql_execution_error", error_message)
            # 返回空DataFrame而不是抛出异常，以便后续流程能继续进行
            return pd.DataFrame()
    
    vn.run_sql = enhanced_run_sql
    vn.run_sql_is_set = True
    
    return vn

def _noop_pull_model(self, client, model_name):
    logger.info(f"Patch: Skipping Ollama model pull for '{model_name}'")

# 修复Ollama补丁应用方式
try:
    # 检查Ollama类的属性和方法，找到正确的模型拉取方法
    if hasattr(Ollama, '_Ollama__pull_model_if_ne'):
        Ollama._Ollama__pull_model_if_ne = _noop_pull_model
        logger.info("Successfully applied Ollama pull skip patch using _Ollama__pull_model_if_ne")
    elif hasattr(Ollama, 'pull_model'):
        # 如果有其他命名的方法
        original_pull_model = Ollama.pull_model
        def patched_pull_model(self, model_name):
            logger.info(f"Patch: Skipping Ollama model pull for '{model_name}'")
        Ollama.pull_model = patched_pull_model
        logger.info("Successfully applied Ollama pull skip patch using pull_model")
    else:
        logger.warning(f"Ollama patch not applied: Could not find appropriate method to patch")
except Exception as e:
    logger.error(f"Could not apply Ollama pull skip patch: {str(e)}")