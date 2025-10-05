import json
import sqlparse
from sqlparse.sql import Identifier, IdentifierList, Where, Comparison
from sqlparse.tokens import Keyword, DML

def is_subselect(parsed):
    """
    Checks if a parsed token is a subselect.
    """
    if not parsed.is_group:
        return False
    for item in parsed.tokens:
        if item.ttype is DML and item.value.upper() == 'SELECT':
            return True
    return False

def _extract_tables(tokens):
    """
    Extracts table names from a list of tokens.
    It looks for identifiers after FROM and JOIN clauses.
    """
    tables = set()
    from_or_join_seen = False
    for token in tokens:
        if token.is_whitespace:
            continue

        if from_or_join_seen:
            if isinstance(token, Identifier):
                if not is_subselect(token):
                    tables.add(token.get_real_name())
            elif isinstance(token, IdentifierList):
                for identifier in token.get_identifiers():
                    if not is_subselect(identifier):
                        tables.add(identifier.get_real_name())
            
            # After finding a table, the clause might end or continue with another join
            if token.ttype is not Keyword or token.value.upper() not in ['AS', 'ON', 'USING', ',']:
                 from_or_join_seen = False


        if token.ttype is Keyword and (token.value.upper() == 'FROM' or 'JOIN' in token.value.upper()):
            from_or_join_seen = True
            
    return list(tables)

def _extract_columns(tokens):
    """
    Extracts column names from various parts of the query.
    """
    columns = set()
    
    # Extract from SELECT clause
    in_select_clause = False
    for token in tokens:
        if token.is_whitespace:
            continue
        if token.ttype is DML and token.value.upper() == 'SELECT':
            in_select_clause = True
            continue
        if token.ttype is Keyword and token.value.upper() == 'FROM':
            in_select_clause = False
            break # End of select clause
        
        if in_select_clause:
            if isinstance(token, Identifier):
                columns.add(token.get_alias() or token.get_name())
            elif isinstance(token, IdentifierList):
                for identifier in token.get_identifiers():
                    if isinstance(identifier, Identifier):
                        columns.add(identifier.get_alias() or identifier.get_name())

    # Extract from WHERE clause
    where_clause = next((t for t in tokens if isinstance(t, Where)), None)
    if where_clause:
        for token in where_clause.tokens:
            if isinstance(token, Comparison):
                if isinstance(token.left, Identifier):
                    columns.add(token.left.get_name())
                if isinstance(token.right, Identifier):
                    columns.add(token.right.get_name())
            elif token.is_group: # Handle nested conditions
                 columns.update(_extract_columns(token.tokens))

    return list(columns)


def extract_joins(tokens):
    """
    Extracts join information from the query.
    """
    joins = []
    for i, token in enumerate(tokens):
        if token.ttype is Keyword and 'JOIN' in token.value.upper():
            join_type = token.value.upper().strip()
            table = None
            on_clause = []

            # Find the table being joined
            next_token_idx = i + 1
            while next_token_idx < len(tokens) and tokens[next_token_idx].is_whitespace:
                next_token_idx += 1
            if next_token_idx < len(tokens) and isinstance(tokens[next_token_idx], Identifier):
                table = tokens[next_token_idx].get_real_name()

            # Find the ON clause
            on_seen = False
            for j in range(next_token_idx + 1, len(tokens)):
                sub_token = tokens[j]
                if on_seen:
                    # Stop at the next major keyword
                    if sub_token.ttype is Keyword and (sub_token.value.upper() in ['WHERE', 'GROUP', 'ORDER', 'LIMIT'] or 'JOIN' in sub_token.value.upper()):
                        break
                    on_clause.append(str(sub_token))
                if sub_token.ttype is Keyword and sub_token.value.upper() == 'ON':
                    on_seen = True
            
            if table:
                joins.append({
                    "type": join_type,
                    "table": table,
                    "on": "".join(on_clause).strip()
                })
    return joins

def extract_filters(tokens):
    """
    Extracts filters from the WHERE clause.
    """
    where_clause = next((token for token in tokens if isinstance(token, Where)), None)
    if not where_clause:
        return []
    
    # Stringify conditions inside WHERE, excluding the 'WHERE' keyword
    conditions = [str(t).strip() for t in where_clause.tokens if not t.is_whitespace and t.value.upper() != 'WHERE']
    # A single string might be better for context
    return [' '.join(conditions)]


def _extract_clause_identifiers(tokens, clause_keyword):
    """Generic function to extract identifiers from a clause like GROUP BY or ORDER BY."""
    clause_seen = False
    for token in tokens:
        if clause_seen:
            if isinstance(token, (Identifier, IdentifierList)):
                return [str(t).strip() for t in (token.get_identifiers() if isinstance(token, IdentifierList) else [token])]
            elif token.ttype is Keyword: # Reached next clause
                return []
        if token.ttype is Keyword and token.value.upper() == clause_keyword:
            clause_seen = True
    return []

def analyze_sql(sql_query):
    """
    Analyzes a single SQL query to extract structured information.
    """
    parsed = sqlparse.parse(sql_query)[0]
    tokens = parsed.tokens

    tables = _extract_tables(tokens)
    all_columns = _extract_columns(tokens)
    
    # Clean up columns: remove table names and wildcards
    columns = sorted([col for col in all_columns if col and col not in tables and col != '*'])

    return {
        "tables": sorted(tables),
        "columns": columns,
        "joins": extract_joins(tokens),
        "filters": extract_filters(tokens),
        "group_by": _extract_clause_identifiers(tokens, 'GROUP BY'),
        "order_by": _extract_clause_identifiers(tokens, 'ORDER BY'),
    }

def main():
    """
    Main function to read SQL queries, analyze them, and save the knowledge base.
    """
    input_filename = 'unique_sql.txt'
    output_filename = 'knowledge_base.json'
    
    try:
        with open(input_filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: {input_filename} not found.")
        return

    sql_queries = [q.strip() for q in content.split('---SQL_SEPARATOR---\n') if q.strip()]
    knowledge_base = []

    for query in sql_queries:
        analysis = analyze_sql(query)
        analysis['sql'] = query
        knowledge_base.append(analysis)

    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(knowledge_base, f, indent=4, ensure_ascii=False)

    print(f"Successfully extracted knowledge from {len(knowledge_base)} SQL queries into {output_filename}")

if __name__ == '__main__':
    main()