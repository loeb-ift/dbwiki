import json
import re

def generate_business_rules_doc():
    """
    從 knowledge_base.json 讀取資料，分析業務邏輯，
    並將結果生成為 Markdown 格式的文檔。
    """
    input_filename = 'knowledge_base.json'
    output_filename = 'training_data_docs.md'
    
    try:
        with open(input_filename, 'r', encoding='utf-8') as f:
            knowledge_base = json.load(f)
    except FileNotFoundError:
        print(f"錯誤: 找不到輸入檔案 '{input_filename}'。")
        return
    except json.JSONDecodeError:
        print(f"錯誤: 無法解析 '{input_filename}' 的 JSON 內容。")
        return

    doc_lines = set()

    for entry in knowledge_base:
        table_name = entry.get('table_name', '未知資料表')

        # 從 'filters' 提取常見業務規則
        if 'filters' in entry and entry['filters']:
            for f in entry['filters']:
                expression = f
                # 範例: status = 'ACTIVE'
                match = re.match(r"(\w+)\s*=\s*'([^']*)'", expression, re.IGNORECASE)
                if match:
                    column, value = match.groups()
                    # 根據範例，如果欄位名包含 'status'，生成特定規則
                    if 'status' in column.lower():
                        doc_lines.add(f"- 資料表 `{table_name}` 中的 `{column}` 欄位通常只篩選 `'{value}'` 的記錄，這代表一個有效的狀態。")

        # 從 'columns' 提取計算邏輯
        if 'columns' in entry and entry['columns']:
            for c in entry['columns']:
                expression = c.strip()
                # 範例: quantity * unit_price
                if any(op in expression for op in ['*', '+', '-', '/']):
                    # 排除不是計算的簡單別名 (e.g., "name as customer_name")
                    main_expression = expression.lower().split(' as ')[0]
                    if not any(op in main_expression for op in ['*', '+', '-', '/']):
                        continue
                    
                    # 根據範例，生成計算規則文檔
                    # 無法自動推斷 "銷售額"，因此使用通用格式
                    doc_lines.add(f"- 一個常見的計算邏輯是 `{expression}`。")

    # 將提取的文檔寫入檔案
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write("# 業務邏輯文檔\n\n")
        if doc_lines:
            # 排序以確保輸出穩定
            sorted_lines = sorted(list(doc_lines))
            f.write("\n".join(sorted_lines))
        else:
            f.write("未從知識庫中提取到可用的業務規則或計算邏輯。\n")

    print(f"已成功生成業務規則文檔 '{output_filename}'。")

if __name__ == '__main__':
    generate_business_rules_doc()