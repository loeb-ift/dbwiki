# Vanna.AI Web 介面

這是一個基於 Vanna.AI 和 Flask 的互動式 Web 應用程式，旨在簡化資料庫的自然語言查詢。它允許使用者輕鬆連接到各種資料庫，透過自然語言訓練文本到 SQL 的模型，並自動生成和執行 SQL 查詢，從而實現資料的快速洞察和分析。

## 特性

- **多種資料庫支援**: 透過 SQLAlchemy 輕鬆連接到 PostgreSQL、MySQL、MS SQL Server、SQLite 等多種資料庫。
- **智慧型訓練資料管理**: 支援使用 DDL (資料定義語言)、資料庫文件和 SQL 問答對進行模型訓練，並自動管理訓練資料，避免重複。
- **自動問題生成**: 利用 Vanna 的強大功能自動生成訓練用的問答對，加速模型訓練過程。
- **知識圖譜視覺化**: 將資料庫 Schema 以直觀的知識圖譜形式展示，幫助使用者理解資料庫結構。
- **自然語言查詢**: 允許使用者以自然語言提出業務問題，應用程式將自動生成並執行相應的 SQL 查詢，並顯示結果。
- **Ollama 整合**: 支援使用 Ollama 進行本地大型語言模型 (LLM) 的整合，提供更靈活的部署選項。
- **可擴展性**: 模組化設計，易於擴展和整合其他 Vanna 向量儲存和 LLM 服務。

## 安裝

1.  **克隆倉庫**:
    ```bash
    git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
    cd YOUR_REPOSITORY
    ```
    請將 `YOUR_USERNAME` 和 `YOUR_REPOSITORY` 替換為您的實際 GitHub 用戶名和倉庫名稱。

2.  **創建並激活虛擬環境**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

3.  **安裝依賴**:
    ```bash
    pip install -r requirements.txt
    ```
    此命令將安裝所有必要的 Python 依賴項。

## 配置

1.  **複製 `.env.example` 文件並重命名為 `.env`**:
    ```bash
    cp .env.example .env
    ```
    然後編輯 `.env` 文件並填寫以下變量：

    ```
    # Ollama LLM 配置 (可選，如果使用本地 LLM)
    OLLAMA_HOST=http://localhost:11434
    OLLAMA_MODEL=llama3

    # ChromaDB 集合名稱 (Vanna 預設向量儲存)
    CHROMA_COLLECTION_NAME=my_vanna_collection

    # 訓練資料 SQLite 資料庫路徑
    TRAINING_DATA_DB_PATH=./training_data_qa.db
    ```
    請根據您的實際環境修改這些配置。如果您不使用 Ollama，可以將相關行註釋掉或留空。

2.  **確保 Ollama 正在運行** (如果使用)。

## 運行應用程式

```bash
python app.py
```

然後在您的瀏覽器中打開 `http://127.0.0.1:5001`。

## 使用指南

這個 Web 介面提供了一個直觀的方式來與 Vanna.AI 互動。以下是主要的操作流程：

1.  **連接資料庫**:
    *   在網頁介面的「1. 連接到資料庫」部分，您需要輸入您的資料庫連接資訊。這通常是一個連接字串，例如：
        *   SQLite: `sqlite:///./my_database.db`
        *   PostgreSQL: `postgresql://user:password@host:port/database`
        *   MySQL: `mysql+mysqlconnector://user:password@host:port/database`
        *   MS SQL Server: `mssql+pyodbc://user:password@host:port/database?driver=ODBC+Driver+17+for+SQL+Server`
    *   填寫完畢後，點擊「連接」按鈕。
    *   成功連接後，應用程式將會自動提取資料庫的 DDL (資料定義語言)，並顯示在「DDL 陳述式」文本框中。這些 DDL 將用於訓練 Vanna 模型，幫助它理解資料庫結構。

2.  **訓練模型**:
    Vanna 模型需要訓練資料來學習如何將自然語言問題轉換為 SQL 查詢。您可以透過以下幾種方式提供訓練資料：
    *   **手動添加 DDL**: 在「DDL 陳述式」文本框中輸入或修改 DDL 語句。
    *   **手動添加文件**: 在「文件」文本框中輸入與資料庫相關的說明或業務邏輯。
    *   **手動添加問答對 (QA)**: 在「問答對」部分，您可以輸入一個自然語言問題和對應的 SQL 查詢。
    *   **自動生成問題**: 點擊「自動生成問題」按鈕，Vanna 將利用其智慧功能，根據您的資料庫 Schema 自動創建新的問答對。這些問答對將自動提交給模型進行訓練，以豐富模型的知識庫。
    *   **提交訓練數據**: 在輸入或生成任何訓練數據後，點擊「訓練模型」按鈕。所有提供的訓練數據將被提交給 Vanna 模型進行學習。
    *   **避免重複訓練**: 應用程式會自動檢查並跳過已存在的 DDL 和文件訓練，確保訓練效率。

3.  **查看訓練資料**:
    *   您可以點擊「獲取訓練資料」按鈕來查看當前 Vanna 模型中已有的訓練數據。這將顯示所有已訓練的 DDL、文件和問答對。

4.  **提出問題**:
    *   在「提出問題」部分的文本框中，輸入您的自然語言業務問題。例如：「顯示每個城市的總銷售額」。
    *   點擊「提問」按鈕。
    *   應用程式將利用訓練好的 Vanna 模型生成相應的 SQL 查詢，並在下方顯示查詢結果。

5.  **管理問答對**:
    *   **更新問答對**: 如果您想修改已有的問答對，可以在「問答對」部分進行編輯，然後點擊「更新問答對」。
    *   **添加問答對**: 您也可以直接在「問答對」部分添加新的問題和 SQL 查詢，然後點擊「添加問答對」。
    *   **重新生成問題**: 如果您對自動生成的問題不滿意，可以點擊「重新生成問題」來獲取新的建議。

## 故障排除

- **Ollama 連接問題**: 確保 Ollama 服務正在運行，並且 `.env` 文件中的 `OLLAMA_HOST` 和 `OLLAMA_MODEL` 配置正確。
- **資料庫連接錯誤**: 檢查您在應用程式中輸入的資料庫連接字串是否正確，以及資料庫服務是否可訪問。
- **重複訓練訊息**: 應用程式已實作機制避免重複訓練 DDL 和文件。如果仍然看到重複訊息，請檢查 `training_data_qa.db` 檔案的完整性。
- **SQL 語法錯誤**: 如果生成的 SQL 查詢出現語法錯誤，請嘗試提供更清晰的自然語言問題，或手動修正 DDL 和文件中的錯誤。

## 貢獻

歡迎對此專案做出貢獻！請隨時提交問題或拉取請求。

## 許可證

此專案根據 MIT 許可證發布。詳情請參閱 `LICENSE` 文件。
