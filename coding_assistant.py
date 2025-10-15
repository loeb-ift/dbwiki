from flask import Flask, request, jsonify, render_template
import ollama
import os

app = Flask(__name__, template_folder='templates')

OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3')

def build_suggestion_prompt(rules, requirements, prefixes):
    """
    建構一個強大的 Prompt 來生成編碼建議。
    """
    # This prompt is now more detailed based on user feedback
    prompt = f"""
# 角色：系統架構師與編碼規範專家

你是一位經驗豐富的系統架構師，專精於為大型企業設計可擴展、語意清晰的編碼與識別碼（Identifier）系統。

## 任務

根據使用者提供的現有規範、新模組需求和前綴列表，為新模組設計一套新的編碼規則。你的建議需要結構清晰、易於理解，並包含實際的程式碼範例。

## 輸入資料

### 1. 企業現有編碼規範
{rules or "使用者未提供現有規範。"}

### 2. 新模組業務需求描述
{requirements}

### 3. 已有模組的前綴列表
{prefixes}

## 輸出要求

請嚴格按照以下 Markdown 格式輸出你的建議，包含三個主要部分：

### 一、建議的編碼格式

*   **選項 1: [建議的格式，例如：PRJ-YYYYMM-NNNN]**
    *   **前綴 (Prefix):** `PRJ` (Project 的縮寫，與現有列表中的前綴不衝突)。
    *   **日期組件 (Date Component):** `YYYYMM` (年月，提供時間上下文，便於歸檔)。
    *   **流水號 (Serial Number):** `NNNN` (4 位數字，每年可容納 9999 個項目)。
    *   **設計理念:** 此格式平衡了可讀性與資訊密度，適用於項目管理類模組。

*   **選項 2: [另一個建議的格式，例如：PJT-YY-NNNNN]**
    *   **前綴 (Prefix):** `PJT` (Project 的另一種縮寫，更短)。
    *   **日期組件 (Date Component):** `YY` (年份的後兩位，更緊湊)。
    *   **流水號 (Serial Number):** `NNNNN` (5 位數字，每年可容納 99999 個項目)。
    *   **設計理念:** 此格式更為緊湊，適用於需要大量生成編碼的場景。

### 二、與現有規則的衝突檢查報告

*   **前綴衝突分析:** 根據您提供的「已有模組的前綴列表」，我建議的前綴 (`PRJ`, `PJT`) 均未出現在列表中，因此直接衝突的風險很低。
*   **潛在風險:** 請注意，如果現有編碼規則中有未明確列出的「隱含規則」（例如，不允許使用三個字母的縮寫），則可能存在間接衝突。建議與團隊確認。

### 三、SQL/程式碼範例 (以選項 1 為例)

#### SQL 查詢範例 (PostgreSQL)
```sql
-- 生成下一個可用的編碼
SELECT 'PRJ-' || TO_CHAR(NOW(), 'YYYYMM') || '-' || LPAD((COUNT(*) + 1)::TEXT, 4, '0')
FROM projects
WHERE project_code LIKE 'PRJ-' || TO_CHAR(NOW(), 'YYYYMM') || '-%';
```

#### Python 程式碼範例
```python
import datetime

def generate_project_code(existing_count: int) -> str:
    \"\"\"
    生成一個新的專案編碼。
    :param existing_count: 當前月份已有的專案數量。
    \"\"\"
    now = datetime.datetime.now()
    prefix = "PRJ"
    date_component = now.strftime("%Y%m")
    serial_number = existing_count + 1
    return f"{{prefix}}-{{date_component}}-{{serial_number:04d}}"

# 範例使用
# 假設資料庫查詢得知本月已有 15 個專案
next_code = generate_project_code(15)
print(f"下一個可用的編碼是: {{next_code}}")
```
"""
    return prompt

def build_follow_up_prompt(history, question):
    """
    建構一個用於後續提問的 Prompt。
    """
    history_str = "\n\n".join([f"**{msg['role'].capitalize()}:**\n{msg['content']}" for msg in history])
    
    prompt = f"""
# 角色：系統架構師與編碼規範專家

你正在與一位使用者進行對話。以下是到目前為止的對話歷史：

--- BEGIN CONVERSATION HISTORY ---
{history_str}
--- END CONVERSATION HISTORY ---

## 新問題

使用者提出了以下新問題：
"{question}"

## 你的任務

請根據完整的對話歷史上下文，簡潔且準確地回答使用者的新問題。
"""
    return prompt

@app.route('/')
def index():
    return render_template('assistant.html')

@app.route('/api/suggest_code', methods=['POST'])
def suggest_code():
    try:
        data = request.get_json()
        if not data or 'requirements' not in data or 'prefixes' not in data:
            return jsonify({'error': '缺少必要的參數: requirements 和 prefixes'}), 400

        prompt = build_suggestion_prompt(data.get('rules',''), data['requirements'], data['prefixes'])
        
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.3}
        )
        suggestion = response['message']['content']
        return jsonify({'suggestion': suggestion})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/follow_up', methods=['POST'])
def follow_up():
    try:
        data = request.get_json()
        if not data or 'history' not in data or 'question' not in data:
            return jsonify({'error': '缺少必要的參數: history 和 question'}), 400

        prompt = build_follow_up_prompt(data['history'], data['question'])
        
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.5}
        )
        answer = response['message']['content']
        return jsonify({'answer': answer})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)