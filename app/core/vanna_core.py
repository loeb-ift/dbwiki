import os
import logging
from sqlalchemy import create_engine, inspect
import pandas as pd
from queue import Queue

# Add 'src' to Python path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))

from vanna.ollama import Ollama
from vanna.chromadb import ChromaDB_VectorStore
from app.core.db_utils import get_user_db_connection

# Configure logger
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class MyVanna(Ollama, ChromaDB_VectorStore):
    def __init__(self, user_id: str, config=None):
        self.user_id = user_id
        self.log_queue = Queue() # 初始化 log_queue
        
        # 1. Completely separate configs for each parent class
        chroma_config = {
            'path': os.path.join(os.getcwd(), 'user_data', 'chroma_db', user_id),
        }
        
        ollama_config = {
            'model': os.getenv('OLLAMA_MODEL', 'llama3'),
            'ollama_host': os.getenv('OLLAMA_HOST', 'http://localhost:11434'),
            'ollama_timeout': 240.0,
            'options': {
                'num_ctx': int(os.getenv('OLLAMA_NUM_CTX', 4096))
            }
        }

        # 2. 确保初始化self.config，修复AttributeError: 'MyVanna' object has no attribute 'config'
        self.config = config if config is not None else {}
        
        # 3. Call parent __init__ methods with their own, isolated configs
        ChromaDB_VectorStore.__init__(self, config=chroma_config)
        Ollama.__init__(self, config=ollama_config)

_vanna_instances = {}

def get_vanna_instance(user_id: str) -> MyVanna:
    if user_id not in _vanna_instances:
        logger.info(f"Creating new MyVanna instance for user: {user_id}")
        _vanna_instances[user_id] = MyVanna(user_id=user_id)
    return _vanna_instances[user_id]

def configure_vanna_for_request(vn: MyVanna, user_id: str, dataset_id: int):
    if not dataset_id:
        raise Exception("No active dataset selected.")
    
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
    
    if not row:
        raise Exception("Active dataset not found.")
    
    db_path = row[0]
    engine = create_engine(f"sqlite:///{db_path}")
    
    def run_sql_with_logging(sql: str) -> pd.DataFrame:
        try:
            logger.info(f"Executing SQL for user {user_id}: {sql[:150]}...")
            df = pd.read_sql_query(sql, engine)
            logger.info(f"SQL query returned {len(df)} rows.")
            return df
        except Exception as e:
            logger.error(f"SQL execution error for user {user_id}: {e}")
            return pd.DataFrame()

    vn.run_sql = run_sql_with_logging
    vn.run_sql_is_set = True
    
    return vn