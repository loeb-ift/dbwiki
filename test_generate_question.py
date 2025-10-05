import os
from dotenv import load_dotenv
from vanna.ollama import Ollama
from vanna.chromadb import ChromaDB_VectorStore

load_dotenv()

class MyVanna(Ollama, ChromaDB_VectorStore):
    def __init__(self, config=None):
        Ollama.__init__(self, config={'model': 'deepseek-coder:33b'})
        ChromaDB_VectorStore.__init__(self, config={'collection_name': os.getenv('CHROMA_COLLECTION_NAME', 'supermarket')})

vn = MyVanna()

# Train with DDL
ddl_path = 'supermarket_ddl.sql'
if os.path.exists(ddl_path):
    with open(ddl_path, 'r') as f:
        ddl = f.read()
        vn.train(ddl=ddl)
        print(f"Vanna has been trained with the DDL from {ddl_path}.")
else:
    print(f"Error: {ddl_path} not found.")
    exit()

# SQL to test
sql = 'SELECT "Product line", COUNT(*) AS "Count" FROM "SuperMarketAnalysis" GROUP BY "Product line" ORDER BY "Count" DESC'

# Generate question from SQL
generated_question = vn.generate_question(sql)

# Print results
print("\nOriginal SQL:")
print(sql)
print("\nVanna's Generated Question:")
print(generated_question)