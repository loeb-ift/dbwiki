import os
from dotenv import load_dotenv
import json
import dataclasses
import requests
import pandas as pd

load_dotenv()

from src.vanna.chromadb.chromadb_vector import ChromaDB_VectorStore
from vanna.types import StringData
from src.vanna.base import VannaBase
from chromadb.config import Settings
import chromadb
from chromadb.utils import embedding_functions

default_ef = embedding_functions.DefaultEmbeddingFunction()

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

print("Initializing Vanna instance...")
# Instantiate the Vanna object.
# A real API key would be required for VannaRemote to function.
# We are using a dummy API key here as we only need to verify data loading from ChromaDB.
vn = VannaTrainer(config={'api_key': 'YOUR_API_KEY', 'model': 'vanna-default', 'path': os.getenv('CHROMA_COLLECTION_NAME')})

print(f"Retrieving training data from ChromaDB collection: {os.getenv('CHROMA_COLLECTION_NAME')}")
training_data = vn.get_training_data()

print("\nRetrieved Training Data:")
print(training_data)

if not training_data.empty:
    print("\nVanna instance successfully loaded training data.")
else:
    print("\nNo training data found or Vanna instance failed to load data.")
