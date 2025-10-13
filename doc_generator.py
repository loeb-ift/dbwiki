import json
import re

def generate_simple_doc_from_knowledge_base(input_filename='knowledge_base.json'):
    """
    A simple utility to generate basic documentation from a knowledge base file.
    This is a fallback and not the main documentation generation logic.
    """
    output_filename = 'generated_simple_docs.md'
    
    try:
        with open(input_filename, 'r', encoding='utf-8') as f:
            knowledge_base = json.load(f)
    except FileNotFoundError:
        print(f"Info: Knowledge base file '{input_filename}' not found. Cannot generate simple docs.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not parse JSON from '{input_filename}'.")
        return

    doc_lines = set()

    for entry in knowledge_base:
        table_name = entry.get('table_name', 'Unknown Table')
        if 'filters' in entry and entry['filters']:
            for f in entry['filters']:
                doc_lines.add(f"- A filter often used is: `{f}` on table `{table_name}`.")
        
        if 'columns' in entry and entry['columns']:
            for c in entry['columns']:
                doc_lines.add(f"- A calculated column or alias used is: `{c}` on table `{table_name}`.")

    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write("# Basic Business Logic Docs\n\n")
        if doc_lines:
            f.write("\n".join(sorted(list(doc_lines))))
        else:
            f.write("No business rules or logic extracted from the knowledge base.\n")

    print(f"Successfully generated simple documentation file '{output_filename}'.")

if __name__ == '__main__':
    generate_simple_doc_from_knowledge_base()
