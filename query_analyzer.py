# query_analyzer.py
# This script requires the sqlparse library.
# You can install it using: pip install sqlparse

import sqlparse
from sqlparse.tokens import String, Number
from collections import Counter
import re

def parameterize_sql(sql):
    """
    Standardizes and parameterizes an SQL query by replacing literals with '?'.
    This logic is consistent with sql_parser.py.
    """
    # Standardize formatting
    formatted_sql = sqlparse.format(sql, reindent=False, keyword_case='upper')
    
    # Parse the standardized SQL statement
    parsed = sqlparse.parse(formatted_sql)[0]
    
    # Recursively process tokens to replace literals
    process_tokens(parsed.tokens)
    
    # Return the parameterized SQL string
    return str(parsed)

def process_tokens(tokens):
    """
    Recursively traverses tokens and replaces literals (strings and numbers) with '?'.
    """
    for token in tokens:
        if token.is_group:
            process_tokens(token.tokens)
        elif token.ttype in String or token.ttype in Number:
            # More robustly handle values within the token
            token.value = '?'

def analyze_queries():
    """
    Reads SQL queries, finds the most frequent ones after parameterization,
    and writes them to a training data file with a comment template.
    """
    input_filename = 'collected_sql.txt'
    output_filename = 'training_data_queries.sql'
    separator = '---SQL_SEPARATOR---\n'
    top_n = 100

    try:
        with open(input_filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: Input file '{input_filename}' not found. Please run the collector first.")
        return

    # Split queries and filter out empty strings
    sql_queries = [q.strip() for q in content.split(separator) if q.strip()]

    # Count frequencies of parameterized queries
    query_counter = Counter()
    # Map parameterized queries back to an original version
    parameterized_to_original = {}

    for query in sql_queries:
        parameterized = parameterize_sql(query)
        query_counter[parameterized] += 1
        # If not already stored, keep one of the original queries for output
        if parameterized not in parameterized_to_original:
            parameterized_to_original[parameterized] = query

    # Find the top N most common queries
    most_common_queries = query_counter.most_common(top_n)

    # Write the top queries to the output file
    with open(output_filename, 'w', encoding='utf-8') as f:
        for i, (param_query, freq) in enumerate(most_common_queries):
            original_query = parameterized_to_original[param_query]
            
            # Add the comment template
            f.write(f"-- 這個查詢用於：[請在此描述查詢的業務目的]\n")
            f.write(f"-- 頻率：{freq}\n")
            
            # Write the original SQL query, ensuring it ends with a semicolon
            if not original_query.strip().endswith(';'):
                f.write(original_query + ';')
            else:
                f.write(original_query)
            
            # Add separators between records, but not after the last one
            if i < len(most_common_queries) - 1:
                f.write("\n\n")

    print(f"Successfully processed {len(sql_queries)} queries.")
    print(f"Found {len(query_counter)} unique parameterized queries.")
    print(f"The top {len(most_common_queries)} queries have been saved to '{output_filename}'.")

if __name__ == '__main__':
    analyze_queries()