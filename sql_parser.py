# sql_parser.py
# This script requires the sqlparse library.
# You can install it using: pip install sqlparse

import sqlparse
from sqlparse.tokens import String, Number

def process_tokens(tokens):
    """
    Recursively traverses tokens and replaces literals with '?'.
    """
    for token in tokens:
        # If the token is a group (like a parenthesis group), recurse into it
        if token.is_group:
            process_tokens(token.tokens)
        # Replace literal tokens (strings and numbers) with a placeholder
        elif token.ttype in String or token.ttype in Number:
            token.value = '?'

def main():
    """
    Reads SQL queries from a file, standardizes and parameterizes them,
    filters for unique queries, and writes them to an output file.
    """
    input_filename = 'collected_sql.txt'
    output_filename = 'unique_sql.txt'
    separator = '---SQL_SEPARATOR---\n'

    try:
        with open(input_filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: Input file '{input_filename}' not found. Please create it and populate it with SQL queries.")
        return

    # Split queries by the separator and filter out any empty strings resulting from the split
    sql_queries = [q.strip() for q in content.split(separator) if q.strip()]
    
    unique_queries = set()

    for query in sql_queries:
        # Standardize formatting, such as keyword casing and indentation
        formatted_sql = sqlparse.format(query, reindent=True, keyword_case='upper')
        
        # Parse the standardized SQL statement
        parsed = sqlparse.parse(formatted_sql)[0]
        
        # Process its tokens to replace literals with placeholders
        process_tokens(parsed.tokens)
        
        # Add the resulting parameterized SQL string to a set to ensure uniqueness
        unique_queries.add(str(parsed))

    # Write the unique, processed queries to the output file, sorted for consistent output
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(separator.join(sorted(list(unique_queries))))

    print(f"Successfully processed {len(sql_queries)} queries.")
    print(f"Found {len(unique_queries)} unique queries, which have been saved to '{output_filename}'.")

if __name__ == '__main__':
    main()