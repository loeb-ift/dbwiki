import sqlite3
import os

def check_database(user_id='user1'): # Defaulting to 'user1' for testing
    """
    Connects to the user-specific database and prints all records from the
    training_prompts table.
    """
    db_dir = os.path.join(os.getcwd(), 'user_data')
    db_path = os.path.join(db_dir, f'training_data_{user_id}.sqlite')
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found for user '{user_id}' at '{db_path}'")
        print("Please ensure you have logged in with this user at least once to create the database.")
        return

    print(f"Connecting to database at: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        table_name = 'training_prompts'
        print(f"\nExecuting: SELECT * FROM {table_name};")
        cursor.execute(f"SELECT * FROM {table_name};")
        
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        
        print(f"\nFound {len(rows)} records in the '{table_name}' table.")
        print("-------------------------------------------------")
        print(f"Columns: {columns}")
        print("-------------------------------------------------")
        
        if not rows:
            print(f"The '{table_name}' table is empty.")
        else:
            for row in rows:
                print(row)
                
        print("-------------------------------------------------")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            print("\nDatabase connection closed.")

if __name__ == '__main__':
    # You can change the user_id here if needed
    check_database(user_id='user1')