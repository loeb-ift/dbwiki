import json
import os
import sqlite3
from dotenv import load_dotenv
from connector import get_connector
from analyzer import analyze_schema

def setup_test_database(db_path: str):
    """Creates a simple SQLite database for testing purposes."""
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create SuperMarketAnalysis table based on the DDL we've seen
    cursor.execute("""
    CREATE TABLE SuperMarketAnalysis (
        "Invoice ID" TEXT PRIMARY KEY,
        "Branch" TEXT,
        "City" TEXT,
        "Customer type" TEXT,
        "Gender" TEXT,
        "Product line" TEXT,
        "Unit price" REAL,
        "Quantity" INTEGER,
        "Tax 5%" REAL,
        "Sales" REAL,
        "Date" TEXT,
        "Time" TEXT,
        "Payment" TEXT,
        "cogs" REAL,
        "gross margin percentage" REAL,
        "gross income" REAL,
        "Rating" REAL
    );
    """)
    
    # Insert some sample data
    cursor.execute("""
    INSERT INTO SuperMarketAnalysis ("Invoice ID", "City", "Sales", "cogs") VALUES
    ('INV-001', 'Yangon', 150.75, 140.0),
    ('INV-002', 'Mandalay', 320.00, 300.0),
    ('INV-003', 'Yangon', 85.50, 80.0);
    """)
    
    conn.commit()
    conn.close()
    print(f"Test database '{db_path}' created successfully.")

def run_schema_extraction(dialect: str, connection_details: dict):
    """
    Connects to a database, extracts its schema, and prints it.
    """
    connector = None
    try:
        # Get the appropriate connector for the given dialect
        connector = get_connector(dialect)
        
        # Connect to the database
        connector.connect(connection_details)
        
        # Extract the raw schema
        print("\nExtracting raw schema...")
        raw_schema_data = connector.get_schema()
        
        # Analyze and enrich the schema
        enriched_schema_data = analyze_schema(raw_schema_data)
        
        # Print the enriched schema in a readable format
        print("\n--- Enriched Schema (Knowledge Base) ---")
        print(json.dumps(enriched_schema_data, indent=2, ensure_ascii=False))
        print("------------------------------------------")

        # Save the enriched schema to a file for persistence
        output_path = "knowledge_base.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(enriched_schema_data, f, indent=2, ensure_ascii=False)
        print(f"Enriched schema has been saved to '{output_path}'.")
        
    except (ValueError, ConnectionError, NotImplementedError) as e:
        print(f"An error occurred: {e}")
    finally:
        if connector:
            connector.close()

if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()

    # --- Demo for SQLite ---
    print("Running DB Wiki Generator...")
    
    # 1. Setup a temporary test database from .env or use a default
    test_db_path = os.getenv("TEST_DB_PATH", "default_test.db")
    setup_test_database(test_db_path)
    
    # 2. Define connection details
    sqlite_conn_details = {"db_path": test_db_path}
    
    # 3. Run the schema extraction process
    run_schema_extraction(dialect="sqlite", connection_details=sqlite_conn_details)
    
    # Clean up the test database
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
        print(f"\nCleaned up test database '{test_db_path}'.")