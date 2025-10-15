from app.core.vanna_core import MyVanna as BaseMyVanna
import os
import logging
import traceback
from app.core.helpers import load_prompt_template, write_ask_log
from app.core.db_utils import validate_user_id
import pandas as pd
from queue import Queue

# 配置日志记录器
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)  # 设置为DEBUG级别以记录更多详细信息

class MyVanna(BaseMyVanna):
    def __init__(self, user_id=None, model=None, api_key=None, config=None):
        """
        初始化 MyVanna 类。这个构造子设置了 Vanna 实例，
        并处理使用者 ID、聊天历史、数据库路径和 LLM 配置。
        
        参数:
            user_id (str, optional): 使用者 ID。默认值为 None。
            model (str, optional): 模型名称。默认值为 None。
            api_key (str, optional): API 金钥。默认值为 None。
            config (dict, optional): 配置字典。默认值为 None。
        """
        # 调用父类构造函数
        super().__init__(user_id=user_id, config=config)
        self.user_id = user_id
        self.log_queue = Queue() # 初始化 log_queue 属性
        self.chat_history = []
        self.current_dataset = None
        self.db_path = None
        # 添加缺失的属性，防止父类方法调用时出错
        self.max_tokens = 4096  # 设置一个合理的默认值
        self.static_documentation = ""  # 空字符串作为默认值
        
        # 确保config属性存在
        if not hasattr(self, 'config'):
            self.config = config or {}
            logger.info(f"Created config attribute: {self.config}")
        else:
            logger.info(f"Config attribute already exists: {self.config}")
        
        self.llm_config = {
            'ollama_model': os.getenv('OLLAMA_MODEL'),
            'ollama_host': os.getenv('OLLAMA_HOST', 'http://localhost:11434'),
        }

    def log_debug_info(self, event_type, details):
        """
        將除錯資訊記錄到佇列中。

        參數:
            event_type (str): 事件類型。
            details (dict): 包含除錯資訊的字典。
        """
        logger.debug(f"Queueing debug info: {event_type} - {details}")
        self.log_queue.put({'event_type': event_type, 'details': details})

    def get_sql_prompt(self, prompt_type='sql_generation', **kwargs):
        """
        获取指定类型的 SQL 提示。此方法会从数据库载入提示模板，并使用提供的参数进行格式化。

        参数:
            prompt_type (str): 提示的类型，默认值为 'sql_generation'。
            **kwargs: 用于格式化提示模板的额外参数。

        返回:
            str: 格式化后的提示字符串。
        
        引發:
            FileNotFoundError: 如果找不到指定类型的提示。
        """
        try:
            # 确保在请求上下文之外也能工作，例如在测试中
            # 因为load_prompt_template可能依赖与请求上下文，这里我们直接调用它
            prompt_template = load_prompt_template(prompt_type)
            return prompt_template.format(**kwargs)
        except FileNotFoundError as e:
            logger.error(f"Failed to load prompt of type '{prompt_type}' from database: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting SQL prompt: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise

    def get_sql_prompt_with_dialect(self, prompt_type='sql_generation', dialect=None, **kwargs):
        """
        获取带有方言的 SQL 提示。

        参数:
            prompt_type (str): 提示的类型，默认值为 'sql_generation'。
            dialect (str, optional): 数据库方言。默认值为 None。
            **kwargs: 用于格式化提示模板的额外参数。

        返回:
            str: 格式化后的提示字符串。
        """
        try:
            prompt = self.get_sql_prompt(prompt_type, dialect=dialect, **kwargs)
            return prompt
        except Exception as e:
            logger.error(f"Error getting SQL prompt with dialect: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return ""

    def set_db_path(self, db_path):
        self.db_path = db_path
        
    def set_dataset(self, dataset_name):
        self.current_dataset = dataset_name
        
    def get_training_data(self, dataset_id: str) -> tuple[list, list, list]:
        """
        從資料庫中獲取指定資料集的所有訓練資料。
        """
        from app.core.db_utils import get_user_db_connection
        
        ddl_list, doc_list, qa_list = [], [], []
        with get_user_db_connection(self.user_id) as conn:
            cursor = conn.cursor()
            
            # 獲取 DDL
            cursor.execute("SELECT ddl_statement FROM training_ddl WHERE dataset_id = ?", (dataset_id,))
            ddl_list = [row[0] for row in cursor.fetchall()]
            
            # 獲取文件
            cursor.execute("SELECT documentation_text FROM training_documentation WHERE dataset_id = ?", (dataset_id,))
            doc_list = [row[0] for row in cursor.fetchall() if row[0]]
            
            # 獲取 QA 配對
            cursor.execute("SELECT question, sql_query FROM training_qa WHERE dataset_id = ?", (dataset_id,))
            qa_list = [{'question': row[0], 'sql': row[1]} for row in cursor.fetchall()]
            
        return ddl_list, doc_list, qa_list

    # This method signature is intentionally designed to accept ANY keyword arguments
    # and ignore them to prevent TypeError when unexpected parameters like 'initial_prompt' are passed
    def get_similar_question_sql(self, question, n=5, *args, **kwargs):
        try:
            logger.info(f"Getting similar question SQL for: {question[:100]}...")
            logger.debug(f"get_similar_question_sql called with n={n}, args count: {len(args)}, kwargs keys: {list(kwargs.keys())}")
            
            # 创建一个安全的kwargs副本，移除任何可能导致问题的参数
            safe_kwargs = {}  # 完全清空，不传递任何额外参数给父类
            
            # 调用父类方法，但只传递必要的参数
            # Explicitly pass only known arguments to the parent method to avoid unexpected behavior.
            similar_questions = super().get_similar_question_sql(question=question, top_n=n)
            write_ask_log(self.user_id, "get_similar_question_sql_results", str(similar_questions))
            logger.debug(f"Successfully retrieved {len(similar_questions) if similar_questions else 0} similar question SQL items")
            return similar_questions
        except Exception as e:
            logger.error(f"Error in get_similar_question_sql: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            # 返回空列表作为默认值
            return []

    def get_related_ddl(self, question, n=5, **kwargs):
        try:
            related_ddl = super().get_related_ddl(question, top_n=n, **kwargs)
            write_ask_log(self.user_id, "get_related_ddl_results", str(related_ddl))
            return related_ddl
        except Exception as e:
            logger.error(f"Error getting related DDL: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return []

    def get_related_documentation(self, question, n=5, **kwargs):
        try:
            related_docs = super().get_related_documentation(question, top_n=n, **kwargs)
            write_ask_log(self.user_id, "get_related_documentation_results", str(related_docs))
            return related_docs
        except Exception as e:
            logger.error(f"Error getting related documentation: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return []

    def get_sql_hints(self, question, **kwargs):
        return []
    
    def generate_sql(self, question: str, ddl_list: list = None, doc_list: list = None, question_sql_list: list = None, **kwargs) -> str:
        """
        Generates SQL for a given question using the provided context.
        This is a pure function that only constructs a prompt and calls the LLM.
        """
        logger.info("Constructing SQL prompt with provided context...")

        # Construct the prompt using the provided context.
        prompt_parts = []
        
        if ddl_list:
            ddl_str = "\n\n".join(ddl_list)
            prompt_parts.append(f"Here are the DDL statements for the database tables:\n```sql\n{ddl_str}\n```")

        if doc_list:
            doc_str = "\n\n".join(doc_list)
            prompt_parts.append(f"Here is some additional documentation about the database:\n{doc_str}")

        if question_sql_list:
            qa_str = "\n".join([f"Question: {qa['question']}\nSQL: {qa['sql']}" for qa in question_sql_list])
            prompt_parts.append(f"Here are some similar questions and their corresponding SQL queries:\n{qa_str}")

        prompt_parts.append(f"Based on the context above, please generate a SQL query that answers the following question: {question}")
        prompt_parts.append("\nIMPORTANT: When using Common Table Expressions (CTEs), ensure that columns from one CTE are not referenced in the WHERE clause of another CTE if they are not in scope. Use JOINs correctly to bring all necessary columns into the final SELECT statement's scope before filtering.")
        
        final_prompt = "\n\n".join(prompt_parts)
        
        # Call the LLM with the final prompt.
        logger.info("Submitting final prompt to LLM for SQL generation.")
        self.log_debug_info('final_sql_generation_prompt', {'prompt': final_prompt})

        try:
            response = self.submit_prompt([self.user_message(final_prompt)])
            # Assuming extract_sql is a method in the parent class or defined elsewhere
            sql = self.extract_sql(response)
            logger.info(f"Successfully generated SQL: {sql[:200]}...")
            self.log_debug_info('generate_sql_complete', {'sql': sql})
            return sql
        except Exception as e:
            logger.error(f"Error during final SQL generation call: {e}", exc_info=True)
            self.log_debug_info('error_generate_sql', {'error': str(e), 'traceback': traceback.format_exc()})
            return f"-- Error generating SQL: {e}"

    def get_sql_result_prompt(self, question, sql, results, **kwargs):
        try:
            logger.info(f"Getting SQL prompt for: {question[:100]}...")
            logger.debug(f"Get SQL prompt kwargs before processing: {kwargs}")
            
            # 确保config属性存在
            if not hasattr(self, 'config'):
                self.config = {}
                logger.info("Added default config dictionary to MyVanna instance")
            
            # 单独处理initial_prompt参数
            initial_prompt = kwargs.pop('initial_prompt', None)
            allow_llm_to_see_data = kwargs.pop('allow_llm_to_see_data', False)
            stream = kwargs.pop('stream', False)
            kwargs.pop('allow_gpt_oss_to_see_logs', None)
            
            self.log_debug_info('generate_sql_params', {'question': question, 'kwargs_after_pop': kwargs})

            logger.debug(f"Extracted initial_prompt: {initial_prompt is not None}, stream: {stream}")
            
            # 将initial_prompt添加到config中
            if initial_prompt:
                logger.info(f"Using custom initial prompt")
                logger.debug(f"Initial prompt preview: {initial_prompt[:100]}...")
                self.config['initial_prompt'] = initial_prompt
            
            # 完全绕过base类的generate_sql实现，直接调用必要的方法
            logger.debug(f"Bypassing base class generate_sql to avoid kwargs issue")
            
            # 1. 获取相似问题的SQL列表
            question_sql_list = []
            try:
                question_sql_list = self.get_similar_question_sql(question, n=5)
                self.log_debug_info('similar_question_sql_results', {'count': len(question_sql_list)})
                logger.info(f"Retrieved {len(question_sql_list)} similar question SQL items")
            except Exception as e:
                logger.error(f"Error getting similar question SQL: {e}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                self.log_debug_info('error_similar_question_sql', {'error': str(e), 'traceback': traceback.format_exc()})
            
            # 2. 获取相关的DDL
            ddl_list = []
            try:
                ddl_list = self.get_related_ddl(question)
                self.log_debug_info('related_ddl_results', {'count': len(ddl_list)})
                logger.info(f"Retrieved {len(ddl_list)} DDL items")
            except Exception as e:
                logger.error(f"Error getting related DDL: {e}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                self.log_debug_info('error_related_ddl', {'error': str(e), 'traceback': traceback.format_exc()})
            
            # 3. 获取相关文档
            doc_list = []
            try:
                doc_list = self.get_related_documentation(question)
                self.log_debug_info('related_documentation_results', {'count': len(doc_list)})
                logger.info(f"Retrieved {len(doc_list)} documentation items")
            except Exception as e:
                logger.error(f"Error getting related documentation: {e}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                self.log_debug_info('error_related_documentation', {'error': str(e), 'traceback': traceback.format_exc()})
            
            # 4. 获取SQL提示
            sql_hint_list = []
            try:
                sql_hint_list = self.get_sql_hints(question)
                self.log_debug_info('sql_hint_results', {'count': len(sql_hint_list)})
                logger.info(f"Retrieved {len(sql_hint_list)} SQL hint items")
            except Exception as e:
                logger.error(f"Error getting SQL hints: {e}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                self.log_debug_info('error_sql_hint', {'error': str(e), 'traceback': traceback.format_exc()})

            # 5. 生成SQL
            try:
                # 记录所有输入参数用于调试
                debug_input_params = {
                    'question': question,
                    'question_sql_list': [s['sql'] for s in question_sql_list], # 只记录SQL语句
                    'ddl_list': ddl_list,
                    'doc_list': doc_list,
                    'sql_hint_list': sql_hint_list,
                    'kwargs': kwargs
                }
                self.log_debug_info('generate_sql_inputs', debug_input_params)

                # 直接调用vanna.ask以生成SQL
                # 注意: 这里的ask方法可能会根据Vanna的内部实现调用LLM
                # 假设vanna.ask会处理LLM的调用逻辑
                # 在这里，我们传递所有收集到的信息给ask方法
                # 如果原始的generate_sql有其他参数，也需要在此处传递
                # 为了简化，我们只传递核心参数
                
                # 构建一个类似Vanna.ask期望的prompt
                # 这是一个简化的构建方式，实际可能需要更复杂的prompt工程
                # 假设Vanna.ask能智能处理这些列表
                
                # 使用一个生成器来处理流式输出
                if stream:
                    logger.info("Generating SQL with streaming")
                    full_sql_response = ""
                    for chunk in self.ask(
                        question=question,
                        sql=question_sql_list,
                        ddl=ddl_list,
                        documentation=doc_list,
                        # 其他可能的参数如initial_prompt等
                        # 需要从self.config中获取，因为kwargs已经被pop处理
                        initial_prompt=self.config.get('initial_prompt'),
                        stream=True,
                        **kwargs
                    ):
                        full_sql_response += chunk
                        yield chunk # 将每个块传回给调用者
                    self.log_debug_info('generate_sql_streaming_complete', {'sql': full_sql_response})
                    logger.info("SQL streaming complete")
                else:
                    logger.info("Generating SQL without streaming")
                    sql_result = self.ask(
                        question=question,
                        sql=question_sql_list,
                        ddl=ddl_list,
                        documentation=doc_list,
                        # 其他可能的参数如initial_prompt等
                        initial_prompt=self.config.get('initial_prompt'),
                        stream=False,
                        **kwargs
                    )
                    self.log_debug_info('generate_sql_complete', {'sql': sql_result})
                    logger.info("SQL generation complete")
                    yield sql_result # 返回非流式结果

            except Exception as e:
                logger.error(f"Error generating SQL: {e}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                self.log_debug_info('error_generate_sql', {'error': str(e), 'traceback': traceback.format_exc()})
                raise  # 重新抛出异常以便上层捕获
        except Exception as e:
            logger.error(f"An unexpected error occurred in get_sql_result_prompt: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise

    def generate_explanatory_sql(self, question: str, sql: str, df: pd.DataFrame, plotly_code: str, user_id: str) -> str:
        """
        Generates an explanation for the given SQL query.
        """
        try:
            from app.core.helpers import load_prompt_template
            # Pass the user_id to load_prompt_template
            prompt = load_prompt_template('sql_explanation', user_id=user_id).format(
                question=question,
                sql=sql,
                df_head=df.head(5).to_markdown(),
                plotly_code=plotly_code
            )
            return self.submit_prompt([self.user_message(prompt)])
        except Exception as e:
            logger.error(f"Error generating explanatory SQL: {e}")
            return ""

    def run_sql(self, sql: str):
        """
        Executes the given SQL statement.
        For SELECT statements, it returns a Pandas DataFrame.
        For DDL/DML statements or empty queries, it returns an empty DataFrame.
        """
        if not sql or not sql.strip():
            logger.warning("run_sql called with empty SQL string.")
            return pd.DataFrame()

        try:
            logger.debug(f"Executing SQL: {sql[:1000]}")
            # Use the configured engine to execute the query
            if self.run_sql_is_set:
                # The lambda set in configure_vanna_for_request handles connection management
                return pd.read_sql_query(sql, self.engine)
            else:
                # Fallback for when the engine is not configured via the request context
                return super().run_sql(sql)
        except Exception as e:
            # Catching ResourceClosedError specifically for non-returning statements
            if "does not return rows" in str(e):
                logger.info(f"SQL statement did not return rows: {sql[:100]}")
                return pd.DataFrame()
            logger.error(f"Error executing SQL: {e}")
            # Re-raise the exception to be handled by the caller
            raise e
    
    def generate_followup_questions(self, question: str, sql: str, df: pd.DataFrame, user_id: str) -> list:
        """
        根據原始問題和查詢結果, 生成後續問題列表。
        """
        try:
            from app.core.helpers import load_prompt_template
            prompt = load_prompt_template('followup_question_generation', user_id=user_id).format(
                question=question,
                sql=sql,
                df_head=df.head(5).to_markdown(),
                n_questions=3  # 添加缺失的参数
            )
            response = self.submit_prompt([self.user_message(prompt)])
            # 清理並返回問題列表
            return [q.strip() for q in response.split('\n') if q.strip()]
        except Exception as e:
            logger.error(f"生成後續問題時出錯: {e}")
            return []

    def add_system_message(self, message):
        self.chat_history.append({'role': 'system', 'content': message})
    
    def add_user_message(self, message):
        self.chat_history.append({'role': 'user', 'content': message})
    
    def add_assistant_message(self, message):
        self.chat_history.append({'role': 'assistant', 'content': message})
    
    def submit_prompt(self, prompt, **kwargs):
        try:
            logger.info("=== Starting submit_prompt in wrapper ===")
            
            if kwargs.get('stream', False):
                logger.info("Streaming mode detected in wrapper. Passing call up and returning generator.")
                return super().submit_prompt(prompt, **kwargs)

            # Non-streaming logic
            logger.info("Non-streaming mode detected in wrapper.")
            logger.info(f"Using Ollama model: {self.llm_config.get('ollama_model')}")
            response = super().submit_prompt(prompt, **kwargs)
            
            if isinstance(response, str):
                logger.info(f"Received non-streaming response. Length: {len(response)} chars.")
            else:
                logger.warning(f"Received non-string response in non-streaming mode: {type(response)}")

            logger.info("=== submit_prompt in wrapper completed successfully ===")
            return response
        except Exception as e:
            logger.error(f"=== submit_prompt in wrapper failed: {e} ===", exc_info=True)
            raise

# 全局Vanna实例缓存
_vanna_instances = {}

def get_vanna_instance(user_id, config=None):
    logger.debug(f"Attempting to get Vanna instance for user_id: '{user_id}'")
    
    # 验证用户ID格式
    is_valid, message = validate_user_id(user_id)
    if not is_valid:
        logger.error(f"Invalid user ID: {message}")
        raise ValueError(message)
    
    cache_key = f"{user_id}"
    if cache_key not in _vanna_instances:
        logger.info(f"Creating new Vanna instance for user: {user_id}")
        vn = MyVanna(user_id=user_id, config=config)
        _vanna_instances[cache_key] = vn
        logger.debug(f"Successfully created new Vanna instance for user: '{user_id}'")
    else:
        logger.debug(f"Found existing Vanna instance for user: '{user_id}' in cache")
    
    return _vanna_instances[cache_key]

def configure_vanna_for_request(vn, user_id, dataset_id=None):
    import flask
    if dataset_id is None:
        dataset_id = flask.session.get('active_dataset')
    if not dataset_id:
        raise Exception("未选择活跃的数据集，请先选择一个数据集。")
    
    from app.core.db_utils import get_user_db_connection
    from sqlalchemy import create_engine
    import pandas as pd
    
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
    if not row:
        raise Exception("Active dataset not found.")
    
    engine = create_engine(f"sqlite:///{row[0]}")
    vn.engine = engine
    # Replace the lambda with a direct assignment to the robust method
    vn.run_sql = vn.run_sql
    vn.run_sql_is_set = True
    
    llm_choice = os.getenv('LLM_CHOICE', 'ollama')
    vn.llm_choice = llm_choice
    
    if vn.llm_choice == 'ollama':
        vn.llm_config['ollama_model'] = os.getenv('OLLAMA_MODEL')
        vn.llm_config['ollama_host'] = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
    
    return vn