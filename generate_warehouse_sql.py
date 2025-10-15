import json
import os
import pandas as pd
import random

def load_mock_data(data_dir):
    """Loads product data to be used in queries."""
    try:
        products_df = pd.read_csv(os.path.join(data_dir, 'products.csv'))
        return products_df
    except FileNotFoundError:
        print(f"Error: Mock data not found in '{data_dir}'. Please run generate_mock_data.py first.")
        return None

def generate_sql_queries(products_df, num_queries=100):
    """Generates a list of realistic SQL queries."""
    
    if products_df is None or products_df.empty:
        return []

    queries = []
    part_numbers = products_df['part_number'].tolist()
    categories = products_df['category'].unique().tolist()

    query_templates = [
        # --- Simple Queries (1-2 tables) ---
        "SELECT * FROM products WHERE part_number = '{pn}';",
        "SELECT quantity, location FROM inventory WHERE part_number = '{pn}';",
        "SELECT product_name, category FROM products WHERE category = '{cat}';",
        "SELECT COUNT(*) FROM shipments WHERE part_number = '{pn}';",
        "SELECT AVG(shipped_quantity) FROM shipments WHERE part_number = '{pn}';",
        
        # --- Medium Queries (2 tables JOIN) ---
        "SELECT p.product_name, i.quantity, i.location FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number = '{pn}';",
        "SELECT p.product_name, SUM(s.shipped_quantity) AS total_shipped FROM products p JOIN shipments s ON p.part_number = s.part_number WHERE p.category = '{cat}' GROUP BY p.product_name ORDER BY total_shipped DESC LIMIT 10;",
        "SELECT p.part_number, p.product_name FROM products p LEFT JOIN inventory i ON p.part_number = i.part_number WHERE i.quantity IS NULL OR i.quantity = 0;",
        "SELECT i.location, COUNT(p.product_id) AS num_products FROM products p JOIN inventory i ON p.part_number = i.part_number GROUP BY i.location;",
        
        # --- Complex Queries (3 tables JOIN, Subqueries, CTEs) ---
        "SELECT p.product_name, i.quantity, SUM(s.shipped_quantity) AS total_shipped FROM products p JOIN inventory i ON p.part_number = i.part_number JOIN shipments s ON p.part_number = s.part_number WHERE p.category = '{cat}' GROUP BY p.product_name, i.quantity HAVING i.quantity < 50;",
        "WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;",
        "SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);",
        "SELECT p.part_number, p.product_name, i.quantity, (SELECT COUNT(*) FROM shipments s WHERE s.part_number = p.part_number) AS shipment_count FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.category = 'Electronics' ORDER BY shipment_count DESC;",
        "SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);"
    ]

    for _ in range(num_queries):
        template = random.choice(query_templates)
        pn = random.choice(part_numbers)
        cat = random.choice(categories)
        
        query = template.format(pn=pn, cat=cat)
        queries.append(query)
        
    return queries

def main():
    """Main function to generate and save the SQL queries."""
    output_dir = 'mock_training_data'
    os.makedirs(output_dir, exist_ok=True)
    
    products_df = load_mock_data(output_dir)
    if products_df is None:
        return
        
    sql_queries = generate_sql_queries(products_df, 100)
    
    file_path = os.path.join(output_dir, 'warehouse_queries.sql')
    with open(file_path, 'w', encoding='utf-8') as f:
        for query in sql_queries:
            f.write(query + "\n\n")
        
    print(f"Successfully generated {len(sql_queries)} SQL queries.")
    print(f"SQL file is saved at: {file_path}")

if __name__ == '__main__':
    main()