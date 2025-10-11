from app.core.vanna_core import MyVanna as BaseMyVanna
import os
import logging
from app.utils.utils import load_prompt_template

# 配置日志记录器
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Ollama patch is now applied in vanna_core.py with improved logic
# This file no longer needs to apply the patch separately

class MyVanna(BaseMyVanna):
    def __init__(self, user_id=None, model=None, api_key=None, config=None):
        # 调用父类构造函数
        super().__init__(user_id=user_id, config=config)
        self.user_id = user_id  # 保存user_id作为实例属性
        self.chat_history = []
        self.current_dataset = None
        self.db_path = None
        
        # Store LLM configuration
        self.llm_config = {
            'ollama_model': os.getenv('OLLAMA_MODEL'),
            'ollama_host': os.getenv('OLLAMA_HOST', 'http://localhost:11434'),
        }
        
    def set_db_path(self, db_path):
        self.db_path = db_path
        
    def set_dataset(self, dataset_name):
        self.current_dataset = dataset_name
        
    def get_similar_question_sql(self, question, n=5):
        try:
            # 调用父类方法获取相似问题
            similar_questions = super().get_similar_question_sql(question, top_n=n)
            logger.info(f"Found {len(similar_questions)} similar questions")
            # 确保结果被写入日志
            from app.core.helpers import write_ask_log
            write_ask_log(self.user_id, "get_similar_question_sql_results", str(similar_questions))
            return similar_questions
        except Exception as e:
            logger.error(f"Error getting similar questions: {e}")
            return []
    
    def get_related_ddl(self, question, n=5):
        try:
            related_ddl = super().get_related_ddl(question, top_n=n)
            logger.info(f"Found {len(related_ddl)} related DDL statements")
            # 确保结果被写入日志
            from app.core.helpers import write_ask_log
            write_ask_log(self.user_id, "get_related_ddl_results", str(related_ddl))
            return related_ddl
        except Exception as e:
            logger.error(f"Error getting related DDL: {e}")
            return []
    
    def get_related_documentation(self, question, n=5):
        try:
            related_docs = super().get_related_documentation(question, top_n=n)
            logger.info(f"Found {len(related_docs)} related documentation entries")
            # 确保结果被写入日志
            from app.core.helpers import write_ask_log
            write_ask_log(self.user_id, "get_related_documentation_results", str(related_docs))
            return related_docs
        except Exception as e:
            logger.error(f"Error getting related documentation: {e}")
            return []
    
    def generate_sql(self, question, **kwargs):
        try:
            logger.info(f"Generating SQL for question: {question}")
            sql = super().generate_sql(question, **kwargs)
            logger.info(f"Generated SQL: {sql}")
            return sql
        except Exception as e:
            logger.error(f"Error generating SQL: {e}")
            raise
    
    def run_sql(self, sql):
        try:
            logger.info(f"Running SQL: {sql}")
            df = super().run_sql(sql)
            logger.info(f"SQL execution completed, returned {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Error running SQL: {e}")
            raise
    
    def add_system_message(self, message):
        self.chat_history.append({
            'role': 'system',
            'content': message
        })
    
    def add_user_message(self, message):
        self.chat_history.append({
            'role': 'user',
            'content': message
        })
    
    def add_assistant_message(self, message):
        self.chat_history.append({
            'role': 'assistant',
            'content': message
        })
    
    def submit_prompt(self, prompt, **kwargs):
        try:
            logger.info(f"=== Starting submit_prompt ===" )
            logger.info(f"Using LLM: {self.llm_choice}")
            if self.llm_choice == 'ollama':
                logger.info(f"Ollama model: {self.llm_config.get('ollama_model')}")
                logger.info(f"Ollama host: {self.llm_config.get('ollama_host')}")
            
            logger.info(f"Prompt type: {type(prompt)}")
            
            # 根据prompt类型进行适当的日志记录
            if isinstance(prompt, str):
                logger.info(f"Prompt length: {len(prompt)} characters")
                prompt_preview = prompt[:100] if len(prompt) > 100 else prompt
                logger.info(f"Prompt preview: {prompt_preview}...")
            elif isinstance(prompt, list):
                logger.info(f"Prompt is a list with {len(prompt)} items")
                # 记录第一个项目的内容（如果是字典）
                if prompt and isinstance(prompt[0], dict):
                    first_item_preview = str(prompt[0])[:150] if len(str(prompt[0])) > 150 else str(prompt[0])
                    logger.info(f"First prompt item preview: {first_item_preview}...")
            else:
                logger.info(f"Prompt is of type {type(prompt)}")
            
            logger.info(f"Calling super().submit_prompt() with {len(kwargs)} additional arguments")
            response = super().submit_prompt(prompt, **kwargs)
            
            logger.info(f"Received response from LLM, type: {type(response)}")
            logger.info(f"Response length: {len(str(response))} characters")
            response_preview = str(response)[:100] if len(str(response)) > 100 else str(response)
            logger.info(f"Response preview: {response_preview}...")
            logger.info(f"=== submit_prompt completed successfully ===")
            
            return response
        except Exception as e:
            logger.error(f"=== submit_prompt failed ===")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            import traceback
            logger.error(f"Error stack trace: {traceback.format_exc()}")
            raise e

# 全局Vanna实例缓存
_vanna_instances = {}

# 获取或创建Vanna实例
def get_vanna_instance(user_id, config=None):
    # 使用用户ID作为缓存键
    cache_key = f"{user_id}"
    
    if cache_key not in _vanna_instances:
        # 创建新实例
        logger.info(f"Creating new Vanna instance for user: {user_id}")
        vn = MyVanna(user_id=user_id, config=config)
        _vanna_instances[cache_key] = vn
    
    return _vanna_instances[cache_key]

# 为请求配置Vanna实例
def configure_vanna_for_request(vn, user_id, dataset_id=None):
    """
    配置Vanna实例以用于请求处理
    
    支持两种调用方式：
    1. configure_vanna_for_request(vn, user_id, dataset_id) - 用于training.py
    2. configure_vanna_for_request(vn, user_id) - 用于ref.py
    
    在第二种情况下，从会话中获取dataset_id
    """
    import flask
    
    # 如果没有提供dataset_id，尝试从会话中获取
    if dataset_id is None:
        dataset_id = flask.session.get('active_dataset')
        if not dataset_id:
            raise Exception("未选择活跃的数据集，请先选择一个数据集。")
    elif not dataset_id:
        raise Exception("未选择活跃的数据集，请先选择一个数据集。")
    
    from app.models import get_user_db_connection
    from sqlalchemy import create_engine
    import pandas as pd
    import os
    
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
    if not row:
        raise Exception("Active dataset not found.")
    
    engine = create_engine(f"sqlite:///{row[0]}")
    vn.engine = engine
    vn.run_sql = lambda sql: pd.read_sql_query(sql, engine)
    vn.run_sql_is_set = True
    
    # 配置LLM选项
    # 首先尝试从环境变量中获取配置
    llm_choice = os.getenv('LLM_CHOICE', 'ollama')
    vn.llm_choice = llm_choice
    logger.info(f"Configured LLM choice: {vn.llm_choice}")
    
    # 如果是Ollama模型，配置相关参数
    if vn.llm_choice == 'ollama':
        ollama_model = os.getenv('OLLAMA_MODEL')
        ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        
        if ollama_model:
            vn.llm_config['ollama_model'] = ollama_model
        if ollama_host:
            vn.llm_config['ollama_host'] = ollama_host
        
        logger.info(f"Configured Ollama with model: {vn.llm_config['ollama_model']}, host: {vn.llm_config['ollama_host']}")
    
    return vn

# Ollama patch is now applied in vanna_core.py with improved logic
# This file no longer needs to apply the patch separately