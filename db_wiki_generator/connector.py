import sqlite3
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class DBConnector(ABC):
    """
    Abstract base class for database connectors.
    Each connector for a specific database dialect should inherit from this class.
    """

    @abstractmethod
    def connect(self, connection_details: Dict[str, Any]):
        """Connect to the database."""
        pass

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """
        Extract the raw schema from the database.
        This corresponds to Phase 1 of our schema extraction plan.
        """
        pass

    @abstractmethod
    def close(self):
        """Close the database connection."""
        pass

class SQLiteConnector(DBConnector):
    """Connector for SQLite databases."""

    def __init__(self):
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self, connection_details: Dict[str, Any]):
        """
        Connects to an SQLite database.
        :param connection_details: A dictionary containing 'db_path'.
        """
        db_path = connection_details.get("db_path")
        if not db_path:
            raise ValueError("SQLite connection details must include 'db_path'.")
        
        try:
            self.conn = sqlite3.connect(db_path)
            print(f"Successfully connected to SQLite database at: {db_path}")
        except sqlite3.Error as e:
            print(f"Error connecting to SQLite database: {e}")
            raise

    def get_schema(self) -> Dict[str, Any]:
        """
        Extracts schema information from an SQLite database using sqlite_master.
        """
        if not self.conn:
            raise ConnectionError("Not connected to any database. Call connect() first.")

        cursor = self.conn.cursor()
        
        # Get table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        schema_info = {"tables": []}

        for table_name in tables:
            # Get column info for each table
            cursor.execute(f"PRAGMA table_info('{table_name}');")
            columns = []
            for row in cursor.fetchall():
                columns.append({
                    "name": row[1],
                    "type": row[2],
                    "notnull": bool(row[3]),
                    "default_value": row[4],
                    "pk": bool(row[5]),
                })
            
            schema_info["tables"].append({
                "name": table_name,
                "columns": columns
            })

        return schema_info

    def close(self):
        """Closes the SQLite connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            print("SQLite connection closed.")

def get_connector(dialect: str) -> DBConnector:
    """
    Factory function to get a database connector based on the dialect.
    """
    if dialect.lower() == "sqlite":
        return SQLiteConnector()
    # Add other dialects here in the future
    # elif dialect.lower() == "postgres":
    #     return PostgresConnector()
    else:
        raise NotImplementedError(f"Connector for dialect '{dialect}' is not implemented.")