# 編碼規則設計助手 - 架構規劃

這份文件描述了「編碼規則設計助手」新功能的技術架構和開發計畫。

## 1. 整體架構

我們將採用一個獨立、輕量級的 Web 應用架構，將此功能與現有的 `run.py` 應用完全分離，以確保模組化和未來的可擴展性。

```mermaid
graph TD
    A[使用者 Browser] -->|1. 輸入資料| B(前端 assistant.html);
    B -->|2. 發送 Fetch API 請求 (JSON)| C{後端 coding_assistant.py};
    C -->|3. 呼叫| D[Prompt 建構器];
    D -->|4. 組合 Prompt| E[LLM 服務];
    E -->|5. 生成建議| C;
    C -->|6. 回傳 JSON 結果| B;
    B -->|7. 顯示結果| A;
```

**組件說明：**

*   **前端 (`assistant.html`)**: 一個單獨的 HTML 檔案，包含必要的 CSS 和 JavaScript。它提供使用者介面，用於輸入現有規範、新業務需求和前綴列表。
*   **後端 (`coding_assistant.py`)**: 一個獨立的 Python Flask 應用。它只負責一件事：提供一個 API 端點來接收請求，與 LLM 互動，然後回傳結果。
*   **Prompt 建構器**: 這是後端應用內部的一個核心邏輯，負責將零散的輸入資訊整合成一個結構化、高效的 Prompt，以引導 LLM 產出高質量的編碼建議。
*   **LLM 服務**: 我們將繼續使用現有的 Ollama 服務作為語言模型後端。

## 2. 檔案結構

新的功能將包含以下檔案：

```
/
|-- coding_assistant.py         # 主要的後端 Flask 應用
|-- templates/
|   |-- assistant.html          # 前端介面
|-- ASSISTANT_PLAN.md           # 本規劃文件
... (現有專案檔案)
```

## 3. 開發待辦清單

- [x] 規劃「編碼規則設計助手」的整體架構。
- [ ] 設計前端介面 (`assistant.html`)。
- [ ] 設計後端 Flask 應用 (`coding_assistant.py`)。
- [ ] 設計核心的 Prompt Engineering 邏輯。
- [ ] 將新依賴（若有）合併到現有 `requirements.txt`。

---

這個架構確保了新舊功能的解耦，讓開發和維護都更加清晰。

## 5. 後端應用與 Prompt 設計

### `coding_assistant.py`
```python
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
```

## 4. 前端介面設計 (`templates/assistant.html`)

```html
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <title>編碼規則設計助手</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; background-color: #f8f9fa; color: #212529; margin: 0; padding: 2em; }
        .container { max-width: 800px; margin: auto; background: white; padding: 2em; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h1, h2 { color: #007bff; }
        textarea, input[type="text"] { width: 98%; padding: 10px; border: 1px solid #ced4da; border-radius: 4px; font-size: 1rem; margin-bottom: 1em; }
        button { padding: 0.8em 1.5em; background-color: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; transition: background-color 0.2s; }
        button:hover { background-color: #0056b3; }
        button:disabled { background-color: #6c757d; cursor: not-allowed; }
        .label { font-weight: bold; margin-bottom: 0.5em; display: block; }
        #chat-history { margin-top: 2em; padding: 1.5em; background-color: #e9ecef; border: 1px solid #dee2e6; border-radius: 4px; }
        .message { margin-bottom: 1em; padding-bottom: 1em; border-bottom: 1px solid #ced4da; }
        .message.user { text-align: right; }
        .message .content { white-space: pre-wrap; font-family: monospace; }
        #follow-up-form { margin-top: 1.5em; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>編碼規則設計助手</h1>
        <p>請提供以下資訊，AI 將根據您的輸入，建議新的編碼前綴與規則。之後您可以針對建議結果進行提問。</p>
        
        <div id="input-form">
            <label for="existing-rules" class="label">1. 企業現有編碼規範文檔 (可選)</label>
            <textarea id="existing-rules" placeholder="貼上您公司現有的編碼規則、原則或範例..."></textarea>

            <label for="new-requirements" class="label">2. 新模組業務需求描述</label>
            <textarea id="new-requirements" placeholder="詳細描述這個新模組的功能、目標和主要業務流程..."></textarea>

            <label for="existing-prefixes" class="label">3. 已有模組的前綴列表 (一行一個)</label>
            <textarea id="existing-prefixes" placeholder="例如：\nPO (採購訂單)\nSO (銷售訂單)\nINV (庫存)"></textarea>

            <button id="generate-btn" onclick="generateSuggestion()">生成編碼建議</button>
        </div>

        <div id="chat-container" style="display: none;">
            <h2>對話式知識庫</h2>
            <div id="chat-history"></div>
            <div id="follow-up-form">
                <label for="follow-up-question" class="label">針對以上建議進行提問：</label>
                <input type="text" id="follow-up-question" placeholder="例如：如果流水號需要到 8 位數，格式應該怎麼調整？">
                <button id="ask-follow-up-btn" onclick="askFollowUp()">提問</button>
            </div>
        </div>
        <div id="loading-indicator" style="display: none;">正在處理，請稍候...</div>
    </div>

    <script>
        let conversationHistory = [];

        async function handleRequest(endpoint, payload) {
            const generateBtn = document.getElementById('generate-btn');
            const askBtn = document.getElementById('ask-follow-up-btn');
            const loadingIndicator = document.getElementById('loading-indicator');

            generateBtn.disabled = true;
            askBtn.disabled = true;
            loadingIndicator.style.display = 'block';

            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });

                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                
                return await response.json();

            } catch (error) {
                alert('請求時發生錯誤：' + error.message);
                return null;
            } finally {
                generateBtn.disabled = false;
                askBtn.disabled = false;
                loadingIndicator.style.display = 'none';
            }
        }

        function renderHistory() {
            const historyContainer = document.getElementById('chat-history');
            historyContainer.innerHTML = '';
            conversationHistory.forEach(msg => {
                const messageDiv = document.createElement('div');
                messageDiv.classList.add('message', msg.role);
                
                const contentDiv = document.createElement('div');
                contentDiv.classList.add('content');
                contentDiv.textContent = msg.content;
                
                messageDiv.appendChild(contentDiv);
                historyContainer.appendChild(messageDiv);
            });
        }

        async function generateSuggestion() {
            const payload = {
                rules: document.getElementById('existing-rules').value,
                requirements: document.getElementById('new-requirements').value,
                prefixes: document.getElementById('existing-prefixes').value,
            };

            if (!payload.requirements.trim() || !payload.prefixes.trim()) {
                alert('請務必填寫「新模組業務需求描述」和「已有模組的前綴列表」。');
                return;
            }

            const data = await handleRequest('/api/suggest_code', payload);
            if (data && data.suggestion) {
                conversationHistory = [{ role: 'assistant', content: data.suggestion }];
                renderHistory();
                document.getElementById('chat-container').style.display = 'block';
                document.getElementById('follow-up-form').style.display = 'block';
            }
        }

        async function askFollowUp() {
            const questionInput = document.getElementById('follow-up-question');
            const question = questionInput.value;
            if (!question.trim()) return;

            conversationHistory.push({ role: 'user', content: question });
            renderHistory();
            questionInput.value = '';

            const payload = {
                history: conversationHistory,
                question: question,
            };

            const data = await handleRequest('/api/follow_up', payload);
            if (data && data.answer) {
                conversationHistory.push({ role: 'assistant', content: data.answer });
                renderHistory();
            }
        }
    </script>
</body>
</html>
```
