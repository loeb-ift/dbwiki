# 測試計畫：SQL 查詢思考過程分析表生成與顯示

## 1. 目標
驗證 `multi_user_app.py` 中動態提示詞的生成邏輯，以及「SQL 查詢思考過程分析表」的完整性、準確性和前端顯示的正確性。

## 2. 測試範圍
*   `MyVanna` 類中新增的日誌記錄功能。
*   `run_vanna_in_thread` 函數中動態提示詞的組裝邏輯。
*   `ask_analysis_prompt.txt` 模板的有效性。
*   `/api/ask` 端點返回的 `text/event-stream` 數據流。
*   前端 `/ask/ui-sync` 頁面中「SQL 查詢思考過程分析表」的解析與顯示。

## 3. 測試策略

### 3.1. 單元測試 (Unit Tests)

**3.1.1. `MyVanna` 類日誌記錄測試**
*   **目的**：驗證 `MyVanna` 類中覆寫的方法（`get_similar_question_sql`, `get_related_ddl`, `get_related_documentation`, `generate_sql`）是否正確地將其呼叫和結果記錄到 `self.log_queue` 中。
*   **測試步驟**：
    1.  實例化 `MyVanna` 對象。
    2.  呼叫上述方法，並傳入模擬的輸入。
    3.  檢查 `self.log_queue` 的內容，驗證日誌項目的 `type`、`step` 和 `details` 是否符合預期。

**3.1.2. `run_vanna_in_thread` 函數提示詞組裝測試**
*   **目的**：驗證 `run_vanna_in_thread` 函數是否正確地從模擬的 `log_queue` 中提取數據，並組裝成 `full_analysis_prompt`。
*   **測試步驟**：
    1.  模擬 `vn.log_queue`，預先填充包含 `similar_qa_details`、`ddl_details` 和 `doc_details` 的日誌項目。
    2.  模擬 `vn_thread.generate_sql` 返回一個 SQL 查詢。
    3.  呼叫 `run_vanna_in_thread` 函數（或其核心邏輯）。
    4.  檢查 `full_analysis_prompt` 的內容，驗證所有佔位符是否被正確替換，且格式（特別是表格和 SQL 程式碼塊）是否符合 `ask_analysis_prompt.txt` 的要求。
    5.  驗證 `vn_thread.submit_prompt` 是否被呼叫，且其參數為正確組裝的 `full_analysis_prompt`。
    6.  驗證 `analysis_result` 和 `data_result` 是否被正確地放入 `vn.log_queue`。

### 3.2. 整合測試 (Integration Tests)

*   **目的**：驗證整個 `/api/ask` 端點從接收請求到返回結果的流程是否正確，包括 LLM 的實際呼叫和結果處理。
*   **測試工具**：使用 Flask 內建的測試客戶端 (test client)。
*   **測試步驟**：
    1.  **環境準備**：
        *   啟動 Flask 應用。
        *   模擬用戶登入並激活一個測試數據集。
        *   確保 Vanna 實例已配置好模擬的 LLM 和向量資料庫，或者連接到實際的測試環境。
    2.  **發送請求**：
        *   向 `/api/ask` 端點發送一個 POST 請求，包含一個測試問題。
    3.  **驗證響應**：
        *   解析 `text/event-stream` 響應。
        *   驗證數據流中包含預期的 `thinking_step` 日誌，例如「開始相似問題檢索」、「相似問題檢索完成」、「開始 DDL 檢索」、「DDL 檢索完成」、「開始文件檢索」、「文件檢索完成」、「LLM 開始生成 SQL」、「LLM 完成生成 SQL」、「生成分析表」、「執行 SQL 查詢」、「獲取數據結果」等。
        *   特別檢查 `analysis_result` 項目，驗證其 `analysis` 內容是否包含「SQL 查詢思考過程分析表」的各個部分（原始問題、相似問題、DDL、文件、綜合分析、邏輯樹、最終 SQL），並且結構合理。
        *   驗證 `data_result` 項目，確保其 `data` 內容是有效的 SQL 查詢結果。

### 3.3. 前端測試 (Frontend Testing)

*   **目的**：驗證 `/ask/ui-sync` 頁面能夠正確解析和顯示 `/api/ask` 返回的數據流，特別是「SQL 查詢思考過程分析表」。
*   **測試方法**：手動測試或使用 Cypress/Selenium 等 E2E 測試工具。
*   **測試步驟**：
    1.  在瀏覽器中打開 `/ask/ui-sync` 頁面。
    2.  輸入一個測試問題並點擊「送出」。
    3.  觀察「思考過程」面板，驗證所有 `thinking_step` 和 `analysis_result` 項目是否按順序顯示。
    4.  檢查「SQL 查詢思考過程分析表」的顯示，確保其格式正確，內容完整，包括表格、程式碼塊和邏輯樹的視覺呈現。
    5.  驗證「結果」面板是否正確顯示 SQL 查詢的數據結果。

## 4. 測試數據
*   **測試問題**：使用日誌報告中提供的問題：「不同產品線的平均評分與總銷售額各是多少？」
*   **模擬數據**：為單元測試準備模擬的相似問題、DDL 和文件數據。
*   **實際數據**：為整合測試準備一個小型 SQLite 數據庫，包含 `SuperMarket_Analysis` 表，並填充少量測試數據。

## 5. 驗收標準
*   所有單元測試通過。
*   所有整合測試通過，`/api/ask` 返回的數據流符合預期。
*   前端 `/ask/ui-sync` 頁面能夠完整、準確、美觀地顯示「SQL 查詢思考過程分析表」和 SQL 查詢結果。