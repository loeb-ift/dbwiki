from typing import Any, Dict, List
from datetime import datetime, timezone

def analyze_schema(raw_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyzes the raw schema and enriches it with semantic information.
    This corresponds to Phase 2 of our schema extraction plan.

    :param raw_schema: The raw schema dictionary from a DBConnector.
    :return: An enriched schema dictionary.
    """
    print("Starting schema analysis...")
    
    enriched_schema = {
        "database_name": "UnknownDB", # Placeholder
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_source": "db_adapter", # Placeholder
        "tables": []
    }

    for table in raw_schema.get("tables", []):
        enriched_table = {
            "table_name": table["name"],
            "description": f"Auto-generated description for table {table['name']}.",
            "row_count": -1, # Placeholder, to be filled by profiling
            "columns": [],
            "relationships": [] # Placeholder
        }

        for column in table.get("columns", []):
            col_name = column["name"]
            col_type = column["type"]
            
            inferred_type, tags = _infer_semantics(col_name, col_type, column.get("pk", False))
            
            enriched_column = {
                "column_name": col_name,
                "technical_type": col_type,
                "inferred_semantic_type": inferred_type,
                "description": f"Auto-generated description for column {col_name}.",
                "tags": tags,
                "stats": {} # Placeholder for profiling stats
            }
            enriched_table["columns"].append(enriched_column)
        
        enriched_schema["tables"].append(enriched_table)

    print("Schema analysis completed.")
    return enriched_schema

def _infer_semantics(name: str, tech_type: str, is_pk: bool) -> (str, List[str]):
    """
    Infers semantic type and tags based on column name, type, and constraints.
    """
    name_lower = name.lower()
    tags = []
    inferred_type = "Unknown"

    # Rule-based inference
    if is_pk or "id" in name_lower:
        inferred_type = "Identifier"
        if is_pk:
            tags.append("Primary Key")

    elif "date" in name_lower or "time" in name_lower:
        inferred_type = "Temporal"
        tags.append("Dimension")

    elif tech_type in ["INTEGER", "REAL", "FLOAT", "DOUBLE", "NUMERIC"]:
        inferred_type = "Numeric"
        # Simple metric/dimension guess
        if "id" not in name_lower and "key" not in name_lower:
            tags.append("Metric")
        else:
            tags.append("Dimension")
            
    elif tech_type in ["TEXT", "VARCHAR", "CHAR"]:
        inferred_type = "Categorical"
        tags.append("Dimension")
        if "city" in name_lower or "country" in name_lower or "branch" in name_lower:
            tags.append("Geography")

    else:
        inferred_type = "Categorical"
        tags.append("Dimension")

    return inferred_type, tags