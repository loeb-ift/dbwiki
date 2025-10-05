import json
import re

def generate_qa_pairs():
    """
    從 'training_data_queries.sql' 讀取 SQL 查詢，
    並為問答對生成一個 JSON 模板。
    """
    try:
        with open('training_data_queries.sql', 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print("錯誤：找不到 training_data_queries.sql。")
        return

    # 從 SQL 內容中移除註解
    content = re.sub(r'--.*', '', content)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

    # 按分號分割查詢，並過濾掉空字串
    queries = [q.strip() for q in content.split(';') if q.strip()]

    qa_pairs = []
    for sql in queries:
        qa_pairs.append({
            "question": "[請在此處輸入對應此 SQL 的自然語言問題]",
            "sql": sql
        })

    try:
        with open('training_data_qa.json', 'w', encoding='utf-8') as f:
            json.dump(qa_pairs, f, indent=4, ensure_ascii=False)
        print("成功生成 training_data_qa.json")
    except IOError as e:
        print(f"寫入檔案時出錯：{e}")

if __name__ == '__main__':
    generate_qa_pairs()