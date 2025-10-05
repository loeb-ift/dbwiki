import json

def generate_qa_pairs():
    """
    為 SuperMarketAnalysis 數據集生成問題-SQL 對列表。
    """
    qa_pairs = [
        {
            "question": "哪個城市的總銷售額最高？",
            "sql": 'SELECT "City", SUM("Sales") AS "TotalSales" FROM "SuperMarketAnalysis" GROUP BY "City" ORDER BY "TotalSales" DESC LIMIT 1;'
        },
        {
            "question": "不同客戶類型的平均評分是多少？",
            "sql": 'SELECT "Customer type", AVG("Rating") AS "AverageRating" FROM "SuperMarketAnalysis" GROUP BY "Customer type";'
        },
        {
            "question": "哪個產品線的總收入最高？",
            "sql": 'SELECT "Product line", SUM("gross income") AS "TotalGrossIncome" FROM "SuperMarketAnalysis" GROUP BY "Product line" ORDER BY "TotalGrossIncome" DESC LIMIT 1;'
        },
        {
            "question": "男性和女性顧客的平均銷貨成本（cogs）有何不同？",
            "sql": 'SELECT "Gender", AVG("cogs") AS "AverageCOGS" FROM "SuperMarketAnalysis" GROUP BY "Gender";'
        },
        {
            "question": "哪種付款方式最受歡迎？",
            "sql": 'SELECT "Payment", COUNT(*) AS "PaymentCount" FROM "SuperMarketAnalysis" GROUP BY "Payment" ORDER BY "PaymentCount" DESC LIMIT 1;'
        },
        {
            "question": "顯示每個分店的總銷售額。",
            "sql": 'SELECT "Branch", SUM("Sales") AS "TotalSales" FROM "SuperMarketAnalysis" GROUP BY "Branch";'
        }
    ]
    return qa_pairs

def main():
    """
    主函數，用於生成問答對並將其寫入 JSON 檔案。
    """
    qa_data = generate_qa_pairs()
    with open('supermarket_qa.json', 'w', encoding='utf-8') as f:
        json.dump(qa_data, f, indent=4, ensure_ascii=False)
    print("已成功生成 supermarket_qa.json")

if __name__ == "__main__":
    main()