# 知識背景文件：基礎進銷存系統

## 系統總覽

本數據模型模擬一個基礎的產品進銷存（進貨、銷售、存貨）系統。整個系統圍繞著「產品(products)」這個核心實體展開，並透過「庫存(inventory)」和「出貨(shipments)」這兩個資料表來追蹤其狀態與流動。

- **`products` (產品表)**：是系統的主資料檔 (Master Data)，定義了所有獨一無二的產品。
- **`inventory` (庫存表)**：是產品的庫存狀態快照，記錄了每個產品目前的庫存水平。
- **`shipments` (出貨表)**：是產品的出貨流水帳 (Transactional Data)，記錄了每一次的出貨事件。

## 資料表詳解

### 1. `products` (產品表)

這是所有產品的目錄，每一行代表一個獨特的品項。

- **`product_id`**: 產品的唯一內部識別碼（主鍵）。
- **`part_number`**: **料號**。這是最重要的欄位，是產品在業務上的唯一識別碼，也是串聯所有資料表的關鍵。它可能包含多種不同的編碼規則。
- **`product_name`**: 產品的描述性名稱，例如 "Mounting Bracket 123"。
- **`category`**: 產品的分類，例如 "Electronics", "Mechanical", "Software"。

### 2. `inventory` (庫存表)

此資料表記錄了每個料號在特定庫位的庫存數量。

- **`inventory_id`**: 庫存記錄的唯一識別碼（主鍵）。
- **`part_number`**: 對應到 `products` 資料表的料號（外鍵）。一個料號在 `inventory` 中可能只會有一筆紀錄，代表其總庫存。
- **`quantity`**: 當前庫存數量。
- **`location`**: 該產品存放的庫位，例如 "A5-2"。

### 3. `shipments` (出貨表)

此資料表記錄了每一次的出貨歷史。

- **`shipment_id`**: 出貨記錄的唯一識別碼（主鍵）。
- **`part_number`**: 本次出貨的產品料號（外鍵），對應到 `products` 資料表。
- **`shipped_quantity`**: 本次出貨的數量。
- **`shipment_date`**: 出貨的日期。

## 核心業務邏輯與關聯

1.  **關聯性**:
    - `products.part_number` 與 `inventory.part_number` 是一對一的關聯。每個產品對應一筆庫存紀錄。
    - `products.part_number` 與 `shipments.part_number` 是一對多的關聯。一個產品可以有多筆出貨記錄。

2.  **查詢範例**:
    - **查詢庫存**: 要查詢某個產品的庫存，需要先從 `products` 表找到對應的 `part_number`，然後用這個 `part_number` 去 `inventory` 表中查找 `quantity`。
    - **計算總出貨量**: 要計算某個產品的總出貨量，需要使用其 `part_number` 在 `shipments` 表中篩選出所有相關記錄，然後對 `shipped_quantity` 進行加總（SUM）。
    - **庫存與出貨分析**: 要分析一個產品的庫存週轉情況，需要將 `inventory` 表的現有庫存與 `shipments` 表的歷史出貨記錄結合起來進行分析。