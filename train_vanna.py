import json
import sqlite3
import dataclasses
import requests
import os
from dotenv import load_dotenv
import argparse

load_dotenv()

from src.vanna.chromadb.chromadb_vector import ChromaDB_VectorStore
from vanna.types import StringData

# This is a custom VannaRemote class to replace the one that was removed from the library.
# It handles communication with the Vanna LLM backend.
class VannaRemote:
    def __init__(self, config=None):
        if config is None:
            config = {}
        
        # Extract API key and model from config for remote operations
        self._api_key = config.get('api_key')
        self._model = config.get('model')
        
        self._endpoint = config.get("endpoint", "https://ask.vanna.ai/rpc")

    def _dataclass_to_dict(self, obj):
        return dataclasses.asdict(obj)

    def _rpc_call(self, method, params):
        headers = {
            "Content-Type": "application/json",
            "Vanna-Key": self._api_key,
            "Vanna-Org": self._model,
        }

        data = {
            "method": method,
            "params": [self._dataclass_to_dict(obj) for obj in params],
        }

        response = requests.post(self._endpoint, headers=headers, data=json.dumps(data))
        
        # Raise an exception for bad status codes (4xx or 5xx)
        response.raise_for_status()
        
        return response.json()

    def system_message(self, message: str) -> any:
        return {"role": "system", "content": message}

    def user_message(self, message: str) -> any:
        return {"role": "user", "content": message}

    def assistant_message(self, message: str) -> any:
        return {"role": "assistant", "content": message}

    def submit_prompt(self, prompt, **kwargs) -> str:
        # JSON-ify the prompt
        json_prompt = json.dumps(prompt, ensure_ascii=False)

        params = [StringData(data=json_prompt)]

        d = self._rpc_call(method="submit_prompt", params=params)

        if "result" not in d:
            return None

        # Load the result into a dataclass
        results = StringData(**d["result"])

        return results.data

# This class composes the Vanna instance with a specific LLM and Vector Database.
class VannaTrainer(VannaRemote, ChromaDB_VectorStore):
    def __init__(self, config=None):
        # Initialize both parent classes
        ChromaDB_VectorStore.__init__(self, config=config)
        VannaRemote.__init__(self, config=config)

# Instantiate the Vanna object.
# A real API key would be required for VannaRemote to function.
        d = self._rpc_call(method="submit_prompt", params=params)

        if "result" not in d:
            return None

        # Load the result into a dataclass
        results = StringData(**d["result"])

        return results.data

# This class composes the Vanna instance with a specific LLM and Vector Database.
class VannaTrainer(VannaRemote, ChromaDB_VectorStore):
    def __init__(self, config=None):
        # Initialize both parent classes
        ChromaDB_VectorStore.__init__(self, config=config)
        VannaRemote.__init__(self, config=config)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Train Vanna instance with supermarket data.")
    parser.add_argument('--user_id', type=str, default='default_user', help='User ID for data isolation')
    args = parser.parse_args()

    user_id = args.user_id
    chroma_collection_name = f"vanna_training_data_{user_id}"

    # Instantiate the Vanna object.
    # A real API key would be required for VannaRemote to function.
    vn = VannaTrainer(config={'api_key': 'YOUR_API_KEY', 'model': 'vanna-default', 'collection_name': chroma_collection_name})

    # Clear the existing collection to ensure a fresh start
    try:
        vn.chroma_client.delete_collection(name=chroma_collection_name)
        print(f"Collection '{chroma_collection_name}' deleted.")
    except Exception as e:
        print(f"Could not delete collection '{chroma_collection_name}': {e}")

    vn.chroma_client.create_collection(name=chroma_collection_name)
    print(f"Collection '{chroma_collection_name}' created.")

    # Train the Vanna instance using all four layers of the training data.
    # 加載超市數據進行訓練
    vn.train(ddl=open('supermarket_ddl.sql').read())
    with open('supermarket_queries.sql', 'r') as f:
        sql_queries = f.read().split(';')
        for i, sql in enumerate(sql_queries):
            if sql.strip():
                # Since we don't have questions, we'll generate a placeholder
                vn.train(question=f"Placeholder question for query {i+1}", sql=sql)

    print(f"Vanna training process initiated with supermarket data for user: {user_id}.")

    # Create a dummy SQLite database with the correct schema and register it as a dataset
    try:
        db_dir = os.path.join('user_data', 'datasets')
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, f"{user_id}_supermarket.sqlite")

        # Create the database and the table
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        ddl_script = open('supermarket_ddl.sql').read()
        cursor.executescript(ddl_script)
        conn.commit()
        conn.close()
        print(f"Dummy database created at '{db_path}' with 'SuperMarketAnalysis' table.")

        # Register this new database as a dataset for the user
        training_db_path = os.path.join(os.getcwd(), 'user_data', f'training_data_{user_id}.sqlite')
        conn = sqlite3.connect(training_db_path)
        cursor = conn.cursor()
        # Ensure datasets table exists
        cursor.execute("CREATE TABLE IF NOT EXISTS datasets (id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_name TEXT NOT NULL, db_path TEXT NOT NULL UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
        # Use INSERT OR REPLACE to avoid duplicate errors on re-runs
        cursor.execute("INSERT OR REPLACE INTO datasets (dataset_name, db_path) VALUES (?, ?)", ('supermarket_default', db_path))
        conn.commit()
        conn.close()
        print(f"Dataset 'supermarket_default' registered for user '{user_id}'.")

    except Exception as e:
        print(f"Error creating or registering dummy database: {e}")