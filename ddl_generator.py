import json
from collections import defaultdict
import ast

def generate_ddl_from_knowledge_base():
    """
    從知識庫 JSON 檔案中讀取資料，推斷資料表結構，
    並生成 DDL (Data Definition Language) 語句。
    """
    try:
        with open('knowledge_base.json', 'r', encoding='utf-8') as f:
            knowledge_base = json.load(f)
    except FileNotFoundError:
        print("錯誤：找不到 knowledge_base.json 檔案。")
        return
    except json.JSONDecodeError:
        print("錯誤：無法解析 knowledge_base.json 檔案。")
        return

    table_columns = defaultdict(set)

    # 匯總資料表和欄位資訊
    for item in knowledge_base:
        tables = item.get('tables', [])
        columns = item.get('columns', [])

        if not tables or not columns:
            continue

        # 處理 columns 列表中的異常字串，例如 "['id', 'document', 'type']"
        processed_columns = []
        for col in columns:
            if isinstance(col, str) and col.startswith('[') and col.endswith(']'):
                try:
                    # 嘗試將字串解析為列表
                    parsed_cols = ast.literal_eval(col)
                    if isinstance(parsed_cols, list):
                        processed_columns.extend(parsed_cols)
                    else:
                        processed_columns.append(col)
                except (ValueError, SyntaxError):
                    # 如果解析失敗，則將其視為普通欄位名
                    processed_columns.append(col)
            else:
                processed_columns.append(col)

        for table_name in tables:
            # 過濾掉無效的或佔位符式的表名
            if '{' in table_name or '}' in table_name:
                continue
            for column_name in processed_columns:
                # 過濾掉無效的欄位名
                if column_name and isinstance(column_name, str):
                    table_columns[table_name].add(column_name.strip())


    if not table_columns:
        print("在知識庫中未找到有效的資料表和欄位資訊。")
        return

    ddl_statements = []
    # 按照資料表名稱排序，以確保輸出的順序一致
    for table, columns in sorted(table_columns.items()):
        # 過濾掉一些可能是解析錯誤的短表名
        if len(table.strip()) <= 2 and table.lower() not in ['db', 'go']:
             continue

        # 開始建立 CREATE TABLE 語句
        statement = f"CREATE TABLE {table} (\n"
        
        # 添加欄位定義
        column_definitions = []
        # 按照欄位名稱排序
        for column in sorted(list(columns)):
            # 為所有欄位使用 TEXT 作為佔位符資料類型
            column_definitions.append(f"    {column} TEXT")
        
        statement += ",\n".join(column_definitions)
        statement += "\n);"
        ddl_statements.append(statement)

    # 將生成的 DDL 語句寫入檔案
    try:
        with open('training_data_ddl.sql', 'w', encoding='utf-8') as f:
            f.write(";\n\n".join(ddl_statements))
        print(f"成功生成 DDL 並儲存至 training_data_ddl.sql，共包含 {len(ddl_statements)} 個資料表。")
    except IOError as e:
        print(f"寫入檔案時發生錯誤: {e}")

if __name__ == '__main__':
    generate_ddl_from_knowledge_base()