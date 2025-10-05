import argparse
import os
import re

def find_sql_in_file(file_path):
    """
    使用正則表達式在給定檔案中查找 SQL 查詢。
    """
    # 這個正則表達式旨在查找常見的 SQL 關鍵字，
    # 並捕獲被單引號、雙引號或三引號包裹的多行字串。
    # 這是一個起點，對於複雜情況可能需要進一步優化。
    sql_regex = re.compile(
        r"""
        (?:
            # 三引號字串
            \"\"\"(.*?SELECT.*?|.*?INSERT.*?|.*?UPDATE.*?|.*?DELETE.*?|.*?WITH.*?) \"\"\" |
            '''(.*?(?:SELECT|INSERT|UPDATE|DELETE|WITH).*?)''' |

            # 單引號和雙引號字串
            "(.*?(?:SELECT|INSERT|UPDATE|DELETE|WITH).*?)" |
            '(.*?(?:SELECT|INSERT|UPDATE|DELETE|WITH).*?)'
        )
        """,
        re.VERBOSE | re.DOTALL | re.IGNORECASE
    )

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            # 對於 .sql 檔案，整個內容被視為一個查詢
            if file_path.endswith('.sql'):
                if content.strip():
                    return [content.strip()]
                else:
                    return []
            
            matches = sql_regex.finditer(content)
            queries = []
            for match in matches:
                # 獲取第一個非空的捕獲組
                query = next((g for g in match.groups() if g is not None), None)
                if query:
                    queries.append(query.strip())
            return queries
    except Exception as e:
        print(f"讀取檔案 {file_path} 時出錯: {e}")
        return []

def collect_sql_from_directory(directory, output_file):
    """
    遞歸遍歷目錄，在指定的檔案類型中查找 SQL 查詢，
    並將它們寫入輸出檔案。
    """
    supported_extensions = ('.py', '.java', '.cs', '.php', '.sql')
    all_queries = []

    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(supported_extensions):
                file_path = os.path.join(root, file)
                queries = find_sql_in_file(file_path)
                if queries:
                    all_queries.extend(queries)

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for i, query in enumerate(all_queries):
                f.write(query)
                if i < len(all_queries) - 1:
                    f.write("\n---SQL_SEPARATOR---\n")
        print(f"已成功將 {len(all_queries)} 個 SQL 查詢收集到 {output_file}")
    except Exception as e:
        print(f"寫入輸出檔案 {output_file} 時出錯: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="從原始碼目錄中收集 SQL 查詢。")
    parser.add_argument(
        "--directory",
        required=True,
        help="要掃描的目標程式碼目錄。"
    )
    parser.add_argument(
        "--output",
        default="collected_sql.txt",
        help="保存收集到的 SQL 查詢的輸出檔案 (預設: collected_sql.txt)。"
    )

    args = parser.parse_args()
    collect_sql_from_directory(args.directory, args.output)