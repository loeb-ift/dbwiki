import sqlite3
import os
import logging

# 配置日志记录器
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def get_user_db_path(user_id: str) -> str:
    db_dir = os.path.join(os.getcwd(), 'user_data')
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, f'training_data_{user_id}.sqlite')

def get_user_db_connection(user_id: str) -> sqlite3.Connection:
    db_path = get_user_db_path(user_id)
    conn = sqlite3.connect(db_path)
    
    # Check if the database is initialized by checking for a key table.
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='datasets';")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        logger.info(f"Table 'datasets' not found for user '{user_id}'. Initializing database.")
        _init_db_tables_and_prompts(conn, user_id)
        logger.info(f"Database initialization finished for user '{user_id}'.")
    
    return conn

def get_db_connection() -> sqlite3.Connection:
    """Gets the global database connection."""
    return sqlite3.connect('vanna.db')

def init_training_db(user_id: str):
    """
    Initializes the training database for a given user.
    This function is safe to call multiple times.
    """
    try:
        with get_user_db_connection(user_id) as conn:
             # get_user_db_connection now handles the initialization
             pass
    except sqlite3.Error as e:
        logger.error(f"Could not initialize/update training database for user '{user_id}': {e}")
        raise

def _init_db_tables_and_prompts(conn: sqlite3.Connection, user_id: str):
    try:
        cursor = conn.cursor()
        tables = {
            "training_ddl": "(id INTEGER PRIMARY KEY AUTOINCREMENT, ddl_statement TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "training_documentation": "(id INTEGER PRIMARY KEY AUTOINCREMENT, documentation_text TEXT NOT NULL, table_name TEXT, dataset_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(dataset_id, table_name))",
            "training_qa": "(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, sql_query TEXT NOT NULL, table_name TEXT, dataset_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "datasets": "(id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_name TEXT NOT NULL, db_path TEXT NOT NULL UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "correction_rules": "(id INTEGER PRIMARY KEY AUTOINCREMENT, incorrect_name TEXT NOT NULL UNIQUE, correct_name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "training_prompts": "(id INTEGER PRIMARY KEY AUTOINCREMENT, prompt_name TEXT NOT NULL, prompt_content TEXT NOT NULL, prompt_type TEXT, is_global INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(prompt_name, prompt_type))"
        }
        for table_name, schema in tables.items():
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} {schema};")
        
        def add_column_if_not_exists(table, column, col_type):
            cursor.execute(f"PRAGMA table_info({table})")
            if column not in [info[1] for info in cursor.fetchall()]:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        
        add_column_if_not_exists('training_documentation', 'dataset_id', 'TEXT')
        add_column_if_not_exists('training_qa', 'dataset_id', 'TEXT')
        
        # Initialize default prompts
        try:
            # Default prompts are now hardcoded to avoid dependency on external files.
            default_prompts_content = {
                'sql_generation': ("You are a {dialect} expert. Please help to generate a SQL query to answer the question. Your response should ONLY be based on the given context and follow the response guidelines and format instructions. \n===Response Guidelines \n1. If the provided context is sufficient, please generate a valid SQL query without any explanations for the question. \n2. If the provided context is almost sufficient but requires knowledge of a specific string in a particular column, please generate an intermediate SQL query to find the distinct strings in that column. Prepend the query with a comment saying intermediate_sql \n3. If the provided context is insufficient, please explain why it can't be generated. \n4. Please use the most relevant table(s). \n5. If the question has been asked and answered before, please repeat the answer exactly as it was given before. \n6. Ensure that the output SQL is {dialect}-compliant and executable, and free of syntax errors. "),
                'followup_question_generation': ("You are a helpful data assistant. The user asked the question: '{question}'\n\nThe SQL query for this question was: {sql}\n\nThe following is a pandas DataFrame with the results of the query: \n{df_head}\n\nGenerate a list of {n_questions} followup questions that the user might ask about this data. Respond with a list of questions, one per line. Do not answer with any explanations -- just the questions. Remember that there should be an unambiguous SQL query that can be generated from the question. Prefer questions that are answerable outside of the context of this conversation. Prefer questions that are slight modifications of the SQL query that was generated that allow digging deeper into the data. Each question will be turned into a button that the user can click to generate a new SQL query so don't use 'example' type questions. Each question must have a one-to-one correspondence with an instantiated SQL query."),
                'summary_generation': ("You are a helpful data assistant. The user asked the question: '{question}'\n\nThe following is a pandas DataFrame with the results of the query: \n{df_markdown}\n\nBriefly summarize the data based on the question that was asked. Do not respond with any additional explanation beyond the summary."),
                'question_rewriting': ("Your goal is to combine a sequence of questions into a singular question if they are related. If the second question does not relate to the first question and is fully self-contained, return the second question. Return just the new combined question with no additional explanations. The question should theoretically be answerable with a single SQL statement."),
                'qa_generation_system': ("You are an expert in SQL. Your task is to generate a business question for a given SQL query. The question should be in Traditional Chinese and should be a natural language question that a business user would ask."),
                'documentation': ("You are a data architect. Your task is to generate a comprehensive documentation for a given database schema. The documentation should be in Markdown format and should include a description of each table and column."),
                'analysis': ("You are a senior data analyst. Your task is to provide a detailed analysis of the user's question, the retrieved context, and the generated SQL query. The analysis should be in Markdown format and should follow the structure provided in the 'ask_analysis_prompt' template."),
                'plotly_generation': ("Can you generate the Python plotly code to chart the results of the dataframe? Assume the data is in a pandas dataframe called 'df'. If there is only one value in the dataframe, use an Indicator. Respond with only Python code. Do not answer with any explanations -- just the code."),
            }

            for prompt_type, prompt_content in default_prompts_content.items():
                prompt_name = f"{prompt_type}_prompt"
                # Check if a global prompt of this TYPE already exists
                cursor.execute("SELECT COUNT(*) FROM training_prompts WHERE prompt_type = ? AND is_global = 1", (prompt_type,))
                if cursor.fetchone()[0] == 0:
                    try:
                        cursor.execute(
                            "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, is_global) VALUES (?, ?, ?, ?)",
                            (prompt_name, prompt_content, prompt_type, 1)
                        )
                        logger.info(f"Initialized default prompt: {prompt_name}")
                    except Exception as e:
                        logger.warning(f"Failed to insert default prompt {prompt_name}: {e}")
        except Exception as e:
            logger.warning(f"Failed to initialize default prompts: {e}")

        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Could not initialize/update training database for user '{user_id}': {e}")
        raise