import csv
import os
from dotenv import load_dotenv

load_dotenv()

# Define file paths
csv_file_path = os.getenv('CSV_FILE_PATH')
sql_file_path = 'supermarket_ddl.sql'
table_name = 'SuperMarketAnalysis'

# Check if the CSV file exists before proceeding
if not csv_file_path or not os.path.exists(csv_file_path):
    print(f"Error: The file {csv_file_path} was not found or CSV_FILE_PATH is not set.")
else:
    # Read the header from the CSV file
    with open(csv_file_path, mode='r', encoding='utf-8') as infile:
        reader = csv.reader(infile)
        header = next(reader)

    # Sanitize column names and define them as TEXT type.
    # Handles spaces in column names by quoting them.
    columns = []
    for col in header:
        if ' ' in col or '-' in col or '(' in col or ')' in col:
            columns.append(f'"{col}" TEXT')
        else:
            columns.append(f'{col} TEXT')

    # Generate the CREATE TABLE DDL statement
    create_table_statement = f"CREATE TABLE {table_name} (\n  "
    create_table_statement += ",\n  ".join(columns)
    create_table_statement += "\n);"

    # Write the DDL statement to the output .sql file
    with open(sql_file_path, mode='w', encoding='utf-8') as outfile:
        outfile.write(create_table_statement)

    print(f"DDL has been successfully generated to {sql_file_path}")