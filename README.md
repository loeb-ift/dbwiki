# DB-GPT-WEBUI: 您的智能資料庫問答夥伴

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.x-green)
![Vanna.ai](https://img.shields.io/badge/Vanna.ai-0.3.x-purple)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

這是一個基於 Vanna.ai 和 Flask 的智能資料庫問答系統，提供直觀的圖形介面，讓使用者可以透過自然語言與資料庫進行互動。系統支援多使用者管理、資料集上傳、AI 模型訓練以及智能 SQL 生成，為資料分析提供強大支援。

![DB-GPT-WEBUI Demo](./img/vanna-readme-diagram.png)
*(您可以在此替換為專案的 GIF 動態圖或介面截圖)*

---

## ✨ 功能亮點 (Features)

- **🤖 自然語言轉 SQL**：透過大型語言模型 (LLM) 將使用者的自然語言問題轉換為可執行的 SQL 查詢。
- **👥 多使用者隔離**：每個使用者擁有獨立的訓練資料和資料集，確保資料隔離和安全。
- **📂 靈活的資料集管理**：支援上傳 CSV 檔案建立資料集，並對多個資料集進行增刪改查。
- **🧠 AI 驅動的模型訓練**：透過提供 DDL、業務文件和 SQL 問答配對來訓練自定義模型，讓 AI 更懂您的資料。
- **🔬 資料庫自動分析**：一鍵對整個資料庫進行元分析，生成關於「如何查詢這個資料庫」的 AI 思考過程總結。
- **📊 智能資料視覺化**：自動將查詢結果生成為 Plotly 互動式圖表，直觀展示資料洞察。
- **🔌 多 LLM 相容**：支援多種 LLM 供應商，包括本地運行的 **Ollama** 和雲端的 **OpenAI** 等。
- **🔐 安全的使用者認證**：內建基於密碼雜湊的使用者認證系統，保障系統安全。

## 🚀 快速開始 (Quick Start)

### 1. 環境準備
- 確保您已安裝 Python 3.8 或更高版本。
- 複製本倉庫到您的本地機器。

### 2. 安裝依賴
在專案根目錄下，執行以下命令安裝所有必需的 Python 套件：
```bash
pip install -r requirements.txt
```

### 3. 配置環境
複製 `.env.example` 檔案為 `.env`，然後根據您的需求編輯配置。
```bash
cp .env.example .env
```
您需要**至少選擇一種** LLM 供應商並填入對應的設定：

- **本地 Ollama (推薦)**
  ```
  OLLAMA_HOST=http://localhost:11434
  OLLAMA_MODEL=your-model-name:latest
  ```

- **OpenAI**
  ```
  OPENAI_API_KEY="sk-..."
  OPENAI_MODEL="gpt-4-turbo"
  ```

您也可以在 `.env` 檔案中自定義使用者和埠號等設定：
```
# Flask 會話金鑰，留空則自動生成
SECRET_KEY=

# 會話超時時間 (分鐘)
SESSION_TIMEOUT_MINUTES=30

# JSON 格式的使用者配置
# 簡單格式: {"username": "password"}
# 完整格式: {"username": {"password": "...", "is_admin": true/false}}
APP_USERS={"testuser": "password"}

# 應用程式埠號
PORT=5004
```

### 4. 啟動應用
```bash
python run.py
```
應用啟動後，您可以在瀏覽器中存取 `http://localhost:5004`。

---

## 📖 使用指南 (Usage Guide)

1.  **使用者登入**
    使用您在 `.env` 檔案中配置的使用者名稱和密碼登入。

2.  **資料集管理**
    - **建立**：點擊「+ 新增」按鈕，輸入資料集名稱並上傳您的 CSV 檔案。
    - **選擇**：從頂部下拉選單中選擇要操作的資料集。
    - **管理**：支援重新命名和刪除已存在的資料集。

3.  **模型訓練**
    - 在訓練頁面，系統會自動載入資料集的 DDL（資料表結構）。
    - 您可以添加**業務文件**（如欄位定義、業務規則）和 **SQL 問答配對**來豐富訓練材料。
    - 點擊「重新訓練整個模型」開始訓練。系統會將這些材料向量化，供 AI 在後續提問時參考。

4.  **提問與分析**
    - 模型訓練完成後，在“智能提問”頁面輸入您的問題。
    - 系統將自動完成**檢索上下文 -> 生成 SQL -> 執行查詢 -> 渲染圖表 -> 生成文字解釋**的全過程。

---

## 🔬 特色功能：AI 驅動的流水號分析

本系統提供一個由 AI 驅動的自動化分析流程，旨在從您的資料庫中識別、分析並範本化唯一識別碼（如訂單號、產品編號等）。

### 分析流程

```mermaid
graph TD
    A[開始分析] --> B{階段一：候選欄位識別};
    B --> C{階段二：資料特徵提取};
    C --> D{階段三 & 四：模式識別與模板生成};
    D --> E{階段五：生成總結報告}
    E --> F[產出綜合分析報告];

    subgraph B [LLM 驅動]
        B1[1. 準備上下文]
        B2[2. 呼叫 'serial_number_candidate_generation' 提示詞]
        B3[3. LLM 回傳 JSON 格式的候選欄位列表]
    end

    subgraph C [Python 腳本]
        C1[1. 針對每個候選欄位]
        C2[2. 從 QA 範例的 WHERE 條件中提取樣本值]
        C3[3. 計算資料特徵(長度、唯一性、字元類型等)]
    end
    
    subgraph D [LLM 驅動]
        D1[1. 準備包含特徵的候選欄位 JSON]
        D2[2. 呼叫 'pattern_and_template_generation' 提示詞]
        D3[3. LLM 回傳包含模式、正則表達式和建議的完整報告]
    end

    subgraph E [LLM 驅動]
        E1[1. 準備階段四的 JSON 報告]
        E2[2. 呼叫 'serial_number_summary_generation' 提示詞]
        E3[3. LLM 回傳人類可讀的 Markdown 總結]
    end

    style A fill:#e1f5fe,stroke:#333,stroke-width:2px
    style F fill:#e8f5e9,stroke:#333,stroke-width:2px
```
最終，系統會輸出一份**人類可讀的總結報告**，並在一個可摺疊區域內附上完整的 **JSON 技術細節**，兼顧了易用性與深度分析的需求。

---

## 🔧 技術棧 (Tech Stack)

- **後端**: Flask, Vanna.ai, SQLAlchemy
- **前端**: Vanilla JavaScript, HTML5, CSS3
- **資料庫**: SQLite
- **AI 模型**: 相容 Ollama, OpenAI GPT 等
- **資料處理**: Pandas
- **視覺化**: Plotly.js

## 📁 專案結構 (Project Structure)

```
dbwiki/
├── app/                  # 主應用程式目錄
│   ├── blueprints/       # Flask 藍圖模組 (API 端點)
│   ├── core/             # 核心業務邏輯
│   ├── utils/            # 工具函式和裝飾器
│   ├── __init__.py       # 應用程式初始化
│   └── vanna_wrapper.py  # Vanna AI 核心封裝
├── templates/            # HTML 範本
├── static/               # 靜態資源 (JS, CSS)
├── prompts/              # 提示詞範本 (JSON 格式)
├── tests/                # 測試檔案
├── run.py                # 應用程式入口
├── requirements.txt      # 專案依賴
└── .env.example          # 環境變數範例檔案
```

## 🤝 貢獻 (Contributing)

歡迎提交問題（Issues）和拉取請求（Pull Requests）。如果您有任何改進建議，請隨時提出。

在提交程式碼前，請確保執行測試：
```bash
python -m pytest tests/
```

## 📄 授權 (License)

本專案採用 MIT 授權。詳情請見 `LICENSE` 檔案。
