import argparse
import os
from dotenv import load_dotenv
from vanna.ollama import Ollama
from vanna.chromadb import ChromaDB_VectorStore

load_dotenv()

# This class composes the Vanna instance with a specific LLM (Ollama) and Vector Database (ChromaDB).
class VannaQuerier(Ollama, ChromaDB_VectorStore):
    def __init__(self, config=None):
        # Initialize both parent classes
        ChromaDB_VectorStore.__init__(self, config={'collection_name': os.getenv('CHROMA_COLLECTION_NAME')})
        Ollama.__init__(self, config=config)

# Main execution block
if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Ask a question to the trained Vanna model and get a SQL query.")
    parser.add_argument("question", type=str, help="The natural language question to convert to SQL.")
    args = parser.parse_args()

    # Configuration for the local Ollama instance provided by the user
    config = {
        'model': 'gpt-oss:20b',
        'ollama_host': 'http://10.227.135.97:11434'
    }

    # Instantiate the Vanna object with the Ollama configuration
    vn = VannaQuerier(config=config)

    # The ask method returns a tuple (sql, dataframe, fig) when print_results=False.
    # We only need the SQL.
    sql_query, df, fig = vn.ask(question=args.question, print_results=False)

    # Print the SQL query to stdout
    if sql_query:
        print(sql_query)
    else:
        print("Could not generate SQL for the given question. The LLM returned an empty response.")