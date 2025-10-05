import json
import os

# List of paths to the questions.json files
file_paths = [
    "training_data/cybersyn-data-commons/questions.json",
    "training_data/cybersyn-financial-data/questions.json",
    "training_data/cybersyn-us-global-public/questions.json",
    "training_data/fivetran-ads-snowflake/questions.json",
    "training_data/sample-fraud/questions.json",
    "training_data/sample-imdb/questions.json",
    "training_data/sample-retention/questions.json",
    "training_data/sample-salaries/questions.json",
    "training_data/similarweb/questions.json",
    "training_data/snowflake-cost/questions.json",
    "training_data/tpc-h/questions.json",
]

sql_queries = []

# Iterate over each file path
for file_path in file_paths:
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                for item in data:
                    if 'answer' in item and item['answer']:
                        sql_queries.append(item['answer'])
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON from {file_path}")
    else:
        print(f"Warning: File not found at {file_path}")

# Define the separator
separator = "---VANNA_SQL_SEPARATOR---"

# Print the collected SQL queries separated by the separator
if sql_queries:
    print(separator.join(sql_queries))
