WITH CitySales AS (
    SELECT City, SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY City
),
AverageCitySales AS (
    SELECT AVG(total_sales) AS overall_avg_sales
    FROM CitySales
)
SELECT cs.City,
       cs.total_sales,
       acs.overall_avg_sales,
       (cs.total_sales - acs.overall_avg_sales) AS sales_difference,
       (cs.total_sales * 100.0 / acs.overall_avg_sales) AS percentage_of_avg
FROM CitySales cs, AverageCitySales acs
ORDER BY cs.total_sales DESC;

SELECT Branch,
       AVG(Rating) AS avg_rating,
       RANK() OVER (ORDER BY AVG(Rating) DESC) AS rating_rank
FROM SuperMarketAnalysis
GROUP BY Branch
ORDER BY avg_rating DESC;

WITH RankedInvoices AS (
    SELECT "Invoice ID",
           "Sales",
           NTILE(10) OVER (ORDER BY "Sales" DESC) as sales_percentile
    FROM SuperMarketAnalysis
)
SELECT "Invoice ID", "Sales"
FROM RankedInvoices
WHERE sales_percentile = 1
ORDER BY "Sales" DESC;

WITH GenderAvgQty AS (
    SELECT Gender, AVG(Quantity) AS avg_qty
    FROM SuperMarketAnalysis
    GROUP BY Gender
),
OverallAvgQty AS (
    SELECT AVG(Quantity) AS overall_avg_qty
    FROM SuperMarketAnalysis
)
SELECT gaq.Gender,
       gaq.avg_qty,
       oaq.overall_avg_qty,
       (gaq.avg_qty - oaq.overall_avg_qty) AS difference_from_overall_avg
FROM GenderAvgQty gaq, OverallAvgQty oaq
ORDER BY gaq.avg_qty DESC;

SELECT City, "Product line", SUM("Sales") AS total_sales
FROM SuperMarketAnalysis
GROUP BY City, "Product line";

WITH BranchProductLineProfit AS (
    SELECT Branch,
           "Product line",
           SUM("gross income") AS total_gross_income,
           SUM(SUM("gross income")) OVER (PARTITION BY Branch) AS branch_total_gross_income
    FROM SuperMarketAnalysis
    GROUP BY Branch, "Product line"
)
SELECT Branch,
       "Product line",
       total_gross_income,
       (total_gross_income * 100.0 / branch_total_gross_income) AS percentage_of_branch_gross_income
FROM BranchProductLineProfit
WHERE total_gross_income = (
    SELECT MAX(total_gross_income)
    FROM BranchProductLineProfit bplp2
    WHERE bplp2.Branch = BranchProductLineProfit.Branch
)
ORDER BY Branch, total_gross_income DESC;

SELECT "Invoice ID", City, "Sales",
       RANK() OVER (PARTITION BY City ORDER BY "Sales" DESC) AS rank_in_city
FROM SuperMarketAnalysis;

SELECT "Product line", AVG(Rating) AS avg_rating
FROM SuperMarketAnalysis
GROUP BY "Product line"
HAVING AVG(Rating) > 7.5;

SELECT sales_day,
       total_sales,
       SUM(total_sales) OVER (ORDER BY sales_day) AS running_total_sales,
       total_sales - LAG(total_sales, 1, 0) OVER (ORDER BY sales_day) AS daily_sales_difference
FROM (
    SELECT DATE("Date") AS sales_day, SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    WHERE "Date" LIKE '2025-01%'
    GROUP BY DATE("Date")
) AS daily_sales
ORDER BY sales_day;

WITH CustomerSpending AS (
    SELECT "Customer type",
           "Sales",
           CASE
               WHEN "Sales" >= (SELECT AVG("Sales") FROM SuperMarketAnalysis) THEN 'High Spender'
               ELSE 'Low Spender'
           END AS spending_category
    FROM SuperMarketAnalysis
)
SELECT "Customer type",
       SUM(CASE WHEN spending_category = 'High Spender' THEN 1 ELSE 0 END) AS high_spenders_count,
       SUM(CASE WHEN spending_category = 'Low Spender' THEN 1 ELSE 0 END) AS low_spenders_count,
       COUNT(*) AS total_customers,
       AVG("Sales") AS average_sales_per_customer_type
FROM SuperMarketAnalysis
GROUP BY "Customer type"
ORDER BY "Customer type";

WITH ProductLineSalesRank AS (
    SELECT "Product line",
           "Invoice ID",
           "Sales",
           RANK() OVER (PARTITION BY "Product line" ORDER BY "Sales" DESC) as sales_rank
    FROM SuperMarketAnalysis
)
SELECT "Product line", "Invoice ID", "Sales"
FROM ProductLineSalesRank
WHERE sales_rank <= 5
ORDER BY "Product line", sales_rank;

WITH CityProductLineSales AS (
    SELECT City,
           "Product line",
           SUM("Sales") AS product_line_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, "Product line"
)
SELECT City,
       "Product line",
       product_line_sales,
       (product_line_sales * 100.0 / city_total_sales) AS percentage_of_city_sales
FROM CityProductLineSales
ORDER BY City, product_line_sales DESC;

WITH BranchPaymentSales AS (
    SELECT Branch,
           Payment,
           AVG("Sales") AS avg_payment_sales,
           AVG(AVG("Sales")) OVER (PARTITION BY Branch) AS branch_overall_avg_sales
    FROM SuperMarketAnalysis
    GROUP BY Branch, Payment
)
SELECT Branch,
       Payment,
       avg_payment_sales,
       branch_overall_avg_sales,
       (avg_payment_sales - branch_overall_avg_sales) AS difference_from_branch_avg
FROM BranchPaymentSales
ORDER BY Branch, avg_payment_sales DESC;

WITH GenderProductLineRating AS (
    SELECT Gender,
           "Product line",
           AVG(Rating) AS avg_rating
    FROM SuperMarketAnalysis
    GROUP BY Gender, "Product line"
)
SELECT gplr.Gender,
       gplr."Product line",
       gplr.avg_rating
FROM GenderProductLineRating gplr
JOIN (
    SELECT Gender, MAX(avg_rating) AS max_avg_rating
    FROM GenderProductLineRating
    GROUP BY Gender
) AS max_ratings_per_gender
ON gplr.Gender = max_ratings_per_gender.Gender AND gplr.avg_rating = max_ratings_per_gender.max_avg_rating
ORDER BY gplr.Gender, gplr.avg_rating DESC;

WITH DailyBranchSales AS (
    SELECT Branch,
           DATE("Date") AS sales_day,
           SUM("Sales") AS daily_sales
    FROM SuperMarketAnalysis
    GROUP BY Branch, DATE("Date")
),
LaggedSales AS (
    SELECT Branch,
           sales_day,
           daily_sales,
           LAG(daily_sales, 1) OVER (PARTITION BY Branch ORDER BY sales_day) AS prev_day_sales,
           LAG(daily_sales, 2) OVER (PARTITION BY Branch ORDER BY sales_day) AS prev_2day_sales
    FROM DailyBranchSales
)
SELECT DISTINCT Branch
FROM LaggedSales
WHERE daily_sales > prev_day_sales
  AND prev_day_sales > prev_2day_sales
ORDER BY Branch;

SELECT City,
       CASE
           WHEN STRFTIME('%H', "Time") BETWEEN '06' AND '11' THEN 'Morning'
           WHEN STRFTIME('%H', "Time") BETWEEN '12' AND '17' THEN 'Afternoon'
           ELSE 'Evening'
       END AS time_of_day,
       AVG("Sales") AS avg_sales
FROM SuperMarketAnalysis
GROUP BY City, time_of_day
ORDER BY City, time_of_day;

WITH ProductLineAvgSales AS (
    SELECT "Product line", AVG("Sales") AS avg_sales_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT s."Product line",
       COUNT(s."Invoice ID") AS transactions_above_average
FROM SuperMarketAnalysis s
JOIN ProductLineAvgSales plas
ON s."Product line" = plas."Product line"
WHERE s."Sales" > plas.avg_sales_per_product_line
GROUP BY s."Product line"
ORDER BY transactions_above_average DESC;

SELECT City,
       "Customer type",
       Payment,
       SUM("Sales") AS total_sales
FROM SuperMarketAnalysis
GROUP BY City, "Customer type", Payment
ORDER BY City, "Customer type", Payment;

WITH BranchProductLineSales AS (
    SELECT Branch,
           "Product line",
           SUM("Sales") AS total_sales,
           RANK() OVER (PARTITION BY Branch ORDER BY SUM("Sales") DESC) AS rank_desc,
           RANK() OVER (PARTITION BY Branch ORDER BY SUM("Sales") ASC) AS rank_asc
    FROM SuperMarketAnalysis
    GROUP BY Branch, "Product line"
)
SELECT Branch,
       "Product line",
       total_sales,
       CASE
           WHEN rank_desc = 1 THEN 'Highest Sales'
           WHEN rank_asc = 1 THEN 'Lowest Sales'
           ELSE NULL
       END AS sales_category
FROM BranchProductLineSales
WHERE rank_desc = 1 OR rank_asc = 1
ORDER BY Branch, sales_category DESC;

SELECT "Product line",
       SUM("Sales") AS total_sales,
       SUM("gross income") AS total_gross_income,
       (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
FROM SuperMarketAnalysis
GROUP BY "Product line"
ORDER BY total_sales DESC;

WITH MonthlyCitySales AS (
    SELECT City,
           STRFTIME('%Y-%m', "Date") AS sales_month,
           SUM("Sales") AS monthly_sales
    FROM SuperMarketAnalysis
    GROUP BY City, sales_month
),
RankedMonthlyCitySales AS (
    SELECT City,
           sales_month,
           monthly_sales,
           RANK() OVER (PARTITION BY City ORDER BY monthly_sales DESC) AS month_rank
    FROM MonthlyCitySales
)
SELECT City, sales_month, monthly_sales
FROM RankedMonthlyCitySales
WHERE month_rank = 1
ORDER BY City;

SELECT "Customer type",
       Payment,
       AVG(Rating) AS avg_rating
FROM SuperMarketAnalysis
GROUP BY "Customer type", Payment
ORDER BY "Customer type", Payment;

WITH BranchProductLineSales AS (
    SELECT Branch,
           "Product line",
           SUM("Sales") AS product_line_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY Branch) AS branch_total_sales
    FROM SuperMarketAnalysis
    GROUP BY Branch, "Product line"
),
RankedBranchProductLineSales AS (
    SELECT Branch,
           "Product line",
           product_line_sales,
           branch_total_sales,
           RANK() OVER (PARTITION BY Branch ORDER BY product_line_sales DESC) AS sales_rank
    FROM BranchProductLineSales
)
SELECT Branch,
       "Product line",
       product_line_sales,
       (product_line_sales * 100.0 / branch_total_sales) AS percentage_of_branch_sales
FROM RankedBranchProductLineSales
WHERE sales_rank = 1
ORDER BY Branch;

SELECT "Product line",
       AVG("Unit price") AS avg_unit_price,
       AVG(Quantity) AS avg_quantity,
       AVG("Sales") AS avg_sales
FROM SuperMarketAnalysis
GROUP BY "Product line"
ORDER BY "Product line";

WITH CityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, "Customer type"
),
RankedCityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           total_sales,
           RANK() OVER (PARTITION BY City ORDER BY total_sales DESC) AS customer_type_rank
    FROM CityCustomerTypeSales
)
SELECT City, "Customer type", total_sales
FROM RankedCityCustomerTypeSales
WHERE customer_type_rank = 1
ORDER BY City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(total_gross_income) AS overall_avg_gross_income,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - om.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - om.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg
FROM ProductLineMetrics plm, OverallMetrics om
ORDER BY plm.total_sales DESC;

WITH CityGenderSales AS (
    SELECT City,
           Gender,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Gender
),
RankedCityGenderSales AS (
    SELECT City,
           Gender,
           total_sales,
           RANK() OVER (PARTITION BY City ORDER BY total_sales DESC) AS gender_rank
    FROM CityGenderSales
)
SELECT City, Gender, total_sales
FROM RankedCityGenderSales
WHERE gender_rank = 1
ORDER BY City;

SELECT "Product line",
       Payment,
       SUM("Sales") AS total_sales
FROM SuperMarketAnalysis
GROUP BY "Product line", Payment
ORDER BY "Product line", Payment;

WITH CityPaymentSales AS (
    SELECT City,
           Payment,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Payment
),
RankedCityPaymentSales AS (
    SELECT City,
           Payment,
           total_sales,
           RANK() OVER (PARTITION BY City ORDER BY total_sales DESC) AS payment_rank
    FROM CityPaymentSales
)
SELECT City, Payment, total_sales
FROM RankedCityPaymentSales
WHERE payment_rank = 1
ORDER BY City;

WITH ProductLineAvgRating AS (
    SELECT "Product line", AVG(Rating) AS avg_rating
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgRating AS (
    SELECT AVG(Rating) AS overall_avg_rating
    FROM SuperMarketAnalysis
)
SELECT plar."Product line",
       plar.avg_rating
FROM ProductLineAvgRating plar, OverallAvgRating oar
WHERE plar.avg_rating > oar.overall_avg_rating
ORDER BY plar.avg_rating DESC;

WITH DailyCitySales AS (
    SELECT City,
           DATE("Date") AS sales_date,
           SUM("Sales") AS daily_sales
    FROM SuperMarketAnalysis
    GROUP BY City, DATE("Date")
),
RankedDailyCitySales AS (
    SELECT City,
           sales_date,
           daily_sales,
           RANK() OVER (PARTITION BY City ORDER BY daily_sales DESC) AS date_rank
    FROM DailyCitySales
)
SELECT City, sales_date, daily_sales
FROM RankedDailyCitySales
WHERE date_rank = 1
ORDER BY City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT "Product line",
       total_sales,
       total_gross_income,
       gross_margin_percentage
FROM ProductLineMetrics
ORDER BY gross_margin_percentage DESC
LIMIT 1;

WITH CityProductLineSales AS (
    SELECT City,
           "Product line",
           SUM("Sales") AS product_line_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, "Product line"
),
RankedCityProductLineSales AS (
    SELECT City,
           "Product line",
           product_line_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY product_line_sales DESC) AS sales_rank
    FROM CityProductLineSales
)
SELECT City,
       "Product line",
       product_line_sales,
       (product_line_sales * 100.0 / city_total_sales) AS percentage_of_city_sales
FROM RankedCityProductLineSales
WHERE sales_rank = 1
ORDER BY City;

WITH ProductLineAvgRating AS (
    SELECT "Product line", AVG(Rating) AS avg_rating
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT "Product line",
       avg_rating
FROM ProductLineAvgRating
ORDER BY avg_rating ASC
LIMIT 1;

WITH MonthlyCitySales AS (
    SELECT City,
           STRFTIME('%Y-%m', "Date") AS sales_month,
           SUM("Sales") AS monthly_sales
    FROM SuperMarketAnalysis
    GROUP BY City, sales_month
),
RankedMonthlyCitySales AS (
    SELECT City,
           sales_month,
           monthly_sales,
           RANK() OVER (PARTITION BY City ORDER BY monthly_sales ASC) AS month_rank
    FROM MonthlyCitySales
)
SELECT City, sales_month, monthly_sales
FROM RankedMonthlyCitySales
WHERE month_rank = 1
ORDER BY City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT "Product line",
       total_sales,
       total_gross_income,
       gross_margin_percentage
FROM ProductLineMetrics
ORDER BY gross_margin_percentage ASC
LIMIT 1;

WITH CityProductLineSales AS (
    SELECT City,
           "Product line",
           SUM("Sales") AS product_line_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, "Product line"
),
RankedCityProductLineSales AS (
    SELECT City,
           "Product line",
           product_line_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY product_line_sales ASC) AS sales_rank
    FROM CityProductLineSales
)
SELECT City,
       "Product line",
       product_line_sales,
       (product_line_sales * 100.0 / city_total_sales) AS percentage_of_city_sales
FROM RankedCityProductLineSales
WHERE sales_rank = 1
ORDER BY City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales
FROM ProductLineAvgRatingSales plars, OverallAvgMetrics oam
WHERE plars.avg_rating > oam.overall_avg_rating
  AND plars.total_sales > oam.overall_avg_sales
ORDER BY plars.avg_rating DESC, plars.total_sales DESC;

WITH CityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           SUM("Sales") AS customer_type_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, "Customer type"
),
RankedCityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           customer_type_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY customer_type_sales DESC) AS sales_rank
    FROM CityCustomerTypeSales
)
SELECT City,
       "Customer type",
       customer_type_sales,
       (customer_type_sales * 100.0 / city_total_sales) AS percentage_of_city_sales
FROM RankedCityCustomerTypeSales
WHERE sales_rank = 1
ORDER BY City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgGrossMargin AS (
    SELECT AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage
FROM ProductLineMetrics plm, OverallAvgGrossMargin oagm
WHERE plm.gross_margin_percentage > oagm.overall_avg_gross_margin_percentage
ORDER BY plm.gross_margin_percentage DESC;

WITH CityGenderSales AS (
    SELECT City,
           Gender,
           SUM("Sales") AS gender_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Gender
),
RankedCityGenderSales AS (
    SELECT City,
           Gender,
           gender_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY gender_sales DESC) AS sales_rank
    FROM CityGenderSales
)
SELECT City,
       Gender,
       gender_sales,
       (gender_sales * 100.0 / city_total_sales) AS percentage_of_city_sales
FROM RankedCityGenderSales
WHERE sales_rank = 1
ORDER BY City;

WITH ProductLinePaymentSales AS (
    SELECT "Product line",
           Payment,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line", Payment
),
RankedProductLinePaymentSales AS (
    SELECT "Product line",
           Payment,
           total_sales,
           RANK() OVER (PARTITION BY "Product line" ORDER BY total_sales DESC) AS payment_rank
    FROM ProductLinePaymentSales
)
SELECT "Product line", Payment, total_sales
FROM RankedProductLinePaymentSales
WHERE payment_rank = 1
ORDER BY "Product line";

WITH CityPaymentSales AS (
    SELECT City,
           Payment,
           SUM("Sales") AS payment_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Payment
),
RankedCityPaymentSales AS (
    SELECT City,
           Payment,
           payment_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY payment_sales DESC) AS sales_rank
    FROM CityPaymentSales
)
SELECT City,
       Payment,
       payment_sales,
       (payment_sales * 100.0 / city_total_sales) AS percentage_of_city_sales
FROM RankedCityPaymentSales
WHERE sales_rank = 1
ORDER BY City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales
FROM ProductLineAvgRatingSales plars, OverallAvgMetrics oam
WHERE plars.avg_rating > oam.overall_avg_rating
  AND plars.total_sales < oam.overall_avg_sales
ORDER BY plars.avg_rating DESC, plars.total_sales ASC;

WITH DailyCitySales AS (
    SELECT City,
           DATE("Date") AS sales_date,
           SUM("Sales") AS daily_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, DATE("Date")
),
RankedDailyCitySales AS (
    SELECT City,
           sales_date,
           daily_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY daily_sales DESC) AS date_rank
    FROM DailyCitySales
)
SELECT City,
       sales_date,
       daily_sales,
       (daily_sales * 100.0 / city_total_sales) AS percentage_of_city_sales
FROM RankedDailyCitySales
WHERE date_rank = 1
ORDER BY City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage
FROM ProductLineMetrics plm, OverallAvgMetrics oam
WHERE plm.gross_margin_percentage > oam.overall_avg_gross_margin_percentage
  AND plm.total_sales > oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage DESC, plm.total_sales DESC;

WITH DailyCitySales AS (
    SELECT City,
           DATE("Date") AS sales_date,
           SUM("Sales") AS daily_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, DATE("Date")
),
RankedDailyCitySales AS (
    SELECT City,
           sales_date,
           daily_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY daily_sales ASC) AS date_rank
    FROM DailyCitySales
)
SELECT City,
       sales_date,
       daily_sales,
       (daily_sales * 100.0 / city_total_sales) AS percentage_of_city_sales
FROM RankedDailyCitySales
WHERE date_rank = 1
ORDER BY City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales
FROM ProductLineAvgRatingSales plars, OverallAvgMetrics oam
WHERE plars.avg_rating < oam.overall_avg_rating
  AND plars.total_sales > oam.overall_avg_sales
ORDER BY plars.avg_rating ASC, plars.total_sales DESC;

WITH MonthlyCitySales AS (
    SELECT City,
           STRFTIME('%Y-%m', "Date") AS sales_month,
           SUM("Sales") AS monthly_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, sales_month
),
RankedMonthlyCitySales AS (
    SELECT City,
           sales_month,
           monthly_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY monthly_sales DESC) AS month_rank
    FROM MonthlyCitySales
)
SELECT City,
       sales_month,
       monthly_sales,
       (monthly_sales * 100.0 / city_total_sales) AS percentage_of_city_sales
FROM RankedMonthlyCitySales
WHERE month_rank = 1
ORDER BY City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage
FROM ProductLineMetrics plm, OverallAvgMetrics oam
WHERE plm.gross_margin_percentage < oam.overall_avg_gross_margin_percentage
  AND plm.total_sales < oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage ASC, plm.total_sales ASC;

WITH MonthlyCitySales AS (
    SELECT City,
           STRFTIME('%Y-%m', "Date") AS sales_month,
           SUM("Sales") AS monthly_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, sales_month
),
RankedMonthlyCitySales AS (
    SELECT City,
           sales_month,
           monthly_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY monthly_sales ASC) AS month_rank
    FROM MonthlyCitySales
)
SELECT City,
       sales_month,
       monthly_sales,
       (monthly_sales * 100.0 / city_total_sales) AS percentage_of_city_sales
FROM RankedMonthlyCitySales
WHERE month_rank = 1
ORDER BY City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales
FROM ProductLineAvgRatingSales plars, OverallAvgMetrics oam
WHERE plars.avg_rating < oam.overall_avg_rating
  AND plars.total_sales < oam.overall_avg_sales
ORDER BY plars.avg_rating ASC, plars.total_sales ASC;

WITH CityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           SUM("Sales") AS customer_type_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, "Customer type"
),
RankedCityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           customer_type_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY customer_type_sales DESC) AS sales_rank
    FROM CityCustomerTypeSales
),
OverallCustomerTypeAvgSales AS (
    SELECT "Customer type",
           AVG("Sales") AS overall_avg_sales_per_customer_type
    FROM SuperMarketAnalysis
    GROUP BY "Customer type"
)
SELECT rccs.City,
       rccs."Customer type",
       rccs.customer_type_sales,
       (rccs.customer_type_sales * 100.0 / rccs.city_total_sales) AS percentage_of_city_sales,
       octas.overall_avg_sales_per_customer_type
FROM RankedCityCustomerTypeSales rccs
JOIN OverallCustomerTypeAvgSales octas
ON rccs."Customer type" = octas."Customer type"
WHERE rccs.sales_rank = 1
ORDER BY rccs.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage
FROM ProductLineMetrics plm, OverallAvgMetrics oam
WHERE plm.gross_margin_percentage > oam.overall_avg_gross_margin_percentage
  AND plm.total_sales < oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage DESC, plm.total_sales ASC;

WITH CityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           SUM("Sales") AS customer_type_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, "Customer type"
),
RankedCityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           customer_type_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY customer_type_sales ASC) AS sales_rank
    FROM CityCustomerTypeSales
),
OverallCustomerTypeAvgSales AS (
    SELECT "Customer type",
           AVG("Sales") AS overall_avg_sales_per_customer_type
    FROM SuperMarketAnalysis
    GROUP BY "Customer type"
)
SELECT rccs.City,
       rccs."Customer type",
       rccs.customer_type_sales,
       (rccs.customer_type_sales * 100.0 / rccs.city_total_sales) AS percentage_of_city_sales,
       octas.overall_avg_sales_per_customer_type
FROM RankedCityCustomerTypeSales rccs
JOIN OverallCustomerTypeAvgSales octas
ON rccs."Customer type" = octas."Customer type"
WHERE rccs.sales_rank = 1
ORDER BY rccs.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg
FROM ProductLineAvgRatingSales plars, OverallAvgMetrics oam
WHERE plars.avg_rating > oam.overall_avg_rating
  AND plars.total_sales > oam.overall_avg_sales
ORDER BY plars.avg_rating DESC, plars.total_sales DESC;

WITH CityGenderSales AS (
    SELECT City,
           Gender,
           SUM("Sales") AS gender_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Gender
),
RankedCityGenderSales AS (
    SELECT City,
           Gender,
           gender_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY gender_sales DESC) AS sales_rank
    FROM CityGenderSales
),
OverallGenderAvgSales AS (
    SELECT Gender,
           AVG("Sales") AS overall_avg_sales_per_gender
    FROM SuperMarketAnalysis
    GROUP BY Gender
)
SELECT rcgs.City,
       rcgs.Gender,
       rcgs.gender_sales,
       (rcgs.gender_sales * 100.0 / rcgs.city_total_sales) AS percentage_of_city_sales,
       ogas.overall_avg_sales_per_gender
FROM RankedCityGenderSales rcgs
JOIN OverallGenderAvgSales ogas
ON rcgs.Gender = ogas.Gender
WHERE rcgs.sales_rank = 1
ORDER BY rcgs.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - oam.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg
FROM ProductLineMetrics plm, OverallAvgMetrics oam
WHERE plm.gross_margin_percentage > oam.overall_avg_gross_margin_percentage
  AND plm.total_sales > oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage DESC, plm.total_sales DESC;

WITH CityGenderSales AS (
    SELECT City,
           Gender,
           SUM("Sales") AS gender_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Gender
),
RankedCityGenderSales AS (
    SELECT City,
           Gender,
           gender_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY gender_sales ASC) AS sales_rank
    FROM CityGenderSales
),
OverallGenderAvgSales AS (
    SELECT Gender,
           AVG("Sales") AS overall_avg_sales_per_gender
    FROM SuperMarketAnalysis
    GROUP BY Gender
)
SELECT rcgs.City,
       rcgs.Gender,
       rcgs.gender_sales,
       (rcgs.gender_sales * 100.0 / rcgs.city_total_sales) AS percentage_of_city_sales,
       ogas.overall_avg_sales_per_gender
FROM RankedCityGenderSales rcgs
JOIN OverallGenderAvgSales ogas
ON rcgs.Gender = ogas.Gender
WHERE rcgs.sales_rank = 1
ORDER BY rcgs.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg
FROM ProductLineAvgRatingSales plars, OverallAvgMetrics oam
WHERE plars.avg_rating < oam.overall_avg_rating
  AND plars.total_sales > oam.overall_avg_sales
ORDER BY plars.avg_rating ASC, plars.total_sales DESC;

WITH CityPaymentSales AS (
    SELECT City,
           Payment,
           SUM("Sales") AS payment_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Payment
),
RankedCityPaymentSales AS (
    SELECT City,
           Payment,
           payment_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY payment_sales DESC) AS sales_rank
    FROM CityPaymentSales
),
OverallPaymentAvgSales AS (
    SELECT Payment,
           AVG("Sales") AS overall_avg_sales_per_payment
    FROM SuperMarketAnalysis
    GROUP BY Payment
)
SELECT rcps.City,
       rcps.Payment,
       rcps.payment_sales,
       (rcps.payment_sales * 100.0 / rcps.city_total_sales) AS percentage_of_city_sales,
       opas.overall_avg_sales_per_payment
FROM RankedCityPaymentSales rcps
JOIN OverallPaymentAvgSales opas
ON rcps.Payment = opas.Payment
WHERE rcps.sales_rank = 1
ORDER BY rcps.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - oam.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg
FROM ProductLineMetrics plm, OverallAvgMetrics oam
WHERE plm.gross_margin_percentage < oam.overall_avg_gross_margin_percentage
  AND plm.total_sales > oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage ASC, plm.total_sales DESC;

WITH CityPaymentSales AS (
    SELECT City,
           Payment,
           SUM("Sales") AS payment_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Payment
),
RankedCityPaymentSales AS (
    SELECT City,
           Payment,
           payment_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY payment_sales ASC) AS sales_rank
    FROM CityPaymentSales
),
OverallPaymentAvgSales AS (
    SELECT Payment,
           AVG("Sales") AS overall_avg_sales_per_payment
    FROM SuperMarketAnalysis
    GROUP BY Payment
)
SELECT rcps.City,
       rcps.Payment,
       rcps.payment_sales,
       (rcps.payment_sales * 100.0 / rcps.city_total_sales) AS percentage_of_city_sales,
       opas.overall_avg_sales_per_payment
FROM RankedCityPaymentSales rcps
JOIN OverallPaymentAvgSales opas
ON rcps.Payment = opas.Payment
WHERE rcps.sales_rank = 1
ORDER BY rcps.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg
FROM ProductLineAvgRatingSales plars, OverallAvgMetrics oam
WHERE plars.avg_rating > oam.overall_avg_rating
  AND plars.total_sales < oam.overall_avg_sales
ORDER BY plars.avg_rating DESC, plars.total_sales ASC;

WITH DailyCitySales AS (
    SELECT City,
           DATE("Date") AS sales_date,
           SUM("Sales") AS daily_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, DATE("Date")
),
RankedDailyCitySales AS (
    SELECT City,
           sales_date,
           daily_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY daily_sales DESC) AS date_rank
    FROM DailyCitySales
),
OverallDailyAvgSales AS (
    SELECT DATE("Date") AS sales_date,
           AVG("Sales") AS overall_avg_sales_per_date
    FROM SuperMarketAnalysis
    GROUP BY DATE("Date")
)
SELECT rdcs.City,
       rdcs.sales_date,
       rdcs.daily_sales,
       (rdcs.daily_sales * 100.0 / rdcs.city_total_sales) AS percentage_of_city_sales,
       odas.overall_avg_sales_per_date
FROM RankedDailyCitySales rdcs
JOIN OverallDailyAvgSales odas
ON rdcs.sales_date = odas.sales_date
WHERE rdcs.date_rank = 1
ORDER BY rdcs.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - oam.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg
FROM ProductLineMetrics plm, OverallAvgMetrics oam
WHERE plm.gross_margin_percentage < oam.overall_avg_gross_margin_percentage
  AND plm.total_sales < oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage ASC, plm.total_sales ASC;

WITH DailyCitySales AS (
    SELECT City,
           DATE("Date") AS sales_date,
           SUM("Sales") AS daily_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, DATE("Date")
),
RankedDailyCitySales AS (
    SELECT City,
           sales_date,
           daily_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY daily_sales ASC) AS date_rank
    FROM DailyCitySales
),
OverallDailyAvgSales AS (
    SELECT DATE("Date") AS sales_date,
           AVG("Sales") AS overall_avg_sales_per_date
    FROM SuperMarketAnalysis
    GROUP BY DATE("Date")
)
SELECT rdcs.City,
       rdcs.sales_date,
       rdcs.daily_sales,
       (rdcs.daily_sales * 100.0 / rdcs.city_total_sales) AS percentage_of_city_sales,
       odas.overall_avg_sales_per_date
FROM RankedDailyCitySales rdcs
JOIN OverallDailyAvgSales odas
ON rdcs.sales_date = odas.sales_date
WHERE rdcs.date_rank = 1
ORDER BY rdcs.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg
FROM ProductLineAvgRatingSales plars, OverallAvgMetrics oam
WHERE plars.avg_rating < oam.overall_avg_rating
  AND plars.total_sales < oam.overall_avg_sales
ORDER BY plars.avg_rating ASC, plars.total_sales ASC;

WITH MonthlyCitySales AS (
    SELECT City,
           STRFTIME('%Y-%m', "Date") AS sales_month,
           SUM("Sales") AS monthly_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, sales_month
),
RankedMonthlyCitySales AS (
    SELECT City,
           sales_month,
           monthly_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY monthly_sales DESC) AS month_rank
    FROM MonthlyCitySales
),
OverallMonthlyAvgSales AS (
    SELECT STRFTIME('%Y-%m', "Date") AS sales_month,
           AVG("Sales") AS overall_avg_sales_per_month
    FROM SuperMarketAnalysis
    GROUP BY STRFTIME('%Y-%m', "Date")
)
SELECT rmcs.City,
       rmcs.sales_month,
       rmcs.monthly_sales,
       (rmcs.monthly_sales * 100.0 / rmcs.city_total_sales) AS percentage_of_city_sales,
       omas.overall_avg_sales_per_month
FROM RankedMonthlyCitySales rmcs
JOIN OverallMonthlyAvgSales omas
ON rmcs.sales_month = omas.sales_month
WHERE rmcs.month_rank = 1
ORDER BY rmcs.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - oam.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg
FROM ProductLineMetrics plm, OverallAvgMetrics oam
WHERE plm.gross_margin_percentage > oam.overall_avg_gross_margin_percentage
  AND plm.total_sales < oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage DESC, plm.total_sales ASC;

WITH MonthlyCitySales AS (
    SELECT City,
           STRFTIME('%Y-%m', "Date") AS sales_month,
           SUM("Sales") AS monthly_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, sales_month
),
RankedMonthlyCitySales AS (
    SELECT City,
           sales_month,
           monthly_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY monthly_sales ASC) AS month_rank
    FROM MonthlyCitySales
),
OverallMonthlyAvgSales AS (
    SELECT STRFTIME('%Y-%m', "Date") AS sales_month,
           AVG("Sales") AS overall_avg_sales_per_month
    FROM SuperMarketAnalysis
    GROUP BY STRFTIME('%Y-%m', "Date")
)
SELECT rmcs.City,
       rmcs.sales_month,
       rmcs.monthly_sales,
       (rmcs.monthly_sales * 100.0 / rmcs.city_total_sales) AS percentage_of_city_sales,
       omas.overall_avg_sales_per_month
FROM RankedMonthlyCitySales rmcs
JOIN OverallMonthlyAvgSales omas
ON rmcs.sales_month = omas.sales_month
WHERE rmcs.month_rank = 1
ORDER BY rmcs.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
),
ProductLineOverallAvgSales AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       ploas.overall_avg_sales_per_product_line
FROM ProductLineAvgRatingSales plars
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgSales ploas
ON plars."Product line" = ploas."Product line"
WHERE plars.avg_rating > oam.overall_avg_rating
  AND plars.total_sales > oam.overall_avg_sales
ORDER BY plars.avg_rating DESC, plars.total_sales DESC;

WITH CityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           SUM("Sales") AS customer_type_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, "Customer type"
),
RankedCityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           customer_type_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY customer_type_sales DESC) AS sales_rank
    FROM CityCustomerTypeSales
),
OverallCustomerTypeAvgSales AS (
    SELECT "Customer type",
           AVG("Sales") AS overall_avg_sales_per_customer_type,
           AVG(Rating) AS overall_avg_rating_per_customer_type
    FROM SuperMarketAnalysis
    GROUP BY "Customer type"
)
SELECT rccs.City,
       rccs."Customer type",
       rccs.customer_type_sales,
       (rccs.customer_type_sales * 100.0 / rccs.city_total_sales) AS percentage_of_city_sales,
       octas.overall_avg_sales_per_customer_type,
       octas.overall_avg_rating_per_customer_type
FROM RankedCityCustomerTypeSales rccs
JOIN OverallCustomerTypeAvgSales octas
ON rccs."Customer type" = octas."Customer type"
WHERE rccs.sales_rank = 1
ORDER BY rccs.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
),
ProductLineOverallAvgSales AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - oam.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg,
       ploas.overall_avg_sales_per_product_line
FROM ProductLineMetrics plm
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgSales ploas
ON plm."Product line" = ploas."Product line"
WHERE plm.gross_margin_percentage > oam.overall_avg_gross_margin_percentage
  AND plm.total_sales < oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage DESC, plm.total_sales ASC;

WITH CityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           SUM("Sales") AS customer_type_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, "Customer type"
),
RankedCityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           customer_type_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY customer_type_sales ASC) AS sales_rank
    FROM CityCustomerTypeSales
),
OverallCustomerTypeAvgSales AS (
    SELECT "Customer type",
           AVG("Sales") AS overall_avg_sales_per_customer_type,
           AVG(Rating) AS overall_avg_rating_per_customer_type
    FROM SuperMarketAnalysis
    GROUP BY "Customer type"
)
SELECT rccs.City,
       rccs."Customer type",
       rccs.customer_type_sales,
       (rccs.customer_type_sales * 100.0 / rccs.city_total_sales) AS percentage_of_city_sales,
       octas.overall_avg_sales_per_customer_type,
       octas.overall_avg_rating_per_customer_type
FROM RankedCityCustomerTypeSales rccs
JOIN OverallCustomerTypeAvgSales octas
ON rccs."Customer type" = octas."Customer type"
WHERE rccs.sales_rank = 1
ORDER BY rccs.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG(Rating) AS overall_avg_rating_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_rating_per_product_line
FROM ProductLineAvgRatingSales plars
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plars."Product line" = ploam."Product line"
WHERE plars.avg_rating > oam.overall_avg_rating
  AND plars.total_sales > oam.overall_avg_sales
ORDER BY plars.avg_rating DESC, plars.total_sales DESC;

WITH CityGenderSales AS (
    SELECT City,
           Gender,
           SUM("Sales") AS gender_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Gender
),
RankedCityGenderSales AS (
    SELECT City,
           Gender,
           gender_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY gender_sales DESC) AS sales_rank
    FROM CityGenderSales
),
OverallGenderAvgMetrics AS (
    SELECT Gender,
           AVG("Sales") AS overall_avg_sales_per_gender,
           AVG(Rating) AS overall_avg_rating_per_gender
    FROM SuperMarketAnalysis
    GROUP BY Gender
)
SELECT rcgs.City,
       rcgs.Gender,
       rcgs.gender_sales,
       (rcgs.gender_sales * 100.0 / rcgs.city_total_sales) AS percentage_of_city_sales,
       ogam.overall_avg_sales_per_gender,
       ogam.overall_avg_rating_per_gender
FROM RankedCityGenderSales rcgs
JOIN OverallGenderAvgMetrics ogam
ON rcgs.Gender = ogam.Gender
WHERE rcgs.sales_rank = 1
ORDER BY rcgs.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - oam.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_gross_margin_percentage_per_product_line
FROM ProductLineMetrics plm
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plm."Product line" = ploam."Product line"
WHERE plm.gross_margin_percentage > oam.overall_avg_gross_margin_percentage
  AND plm.total_sales > oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage DESC, plm.total_sales DESC;

WITH CityGenderSales AS (
    SELECT City,
           Gender,
           SUM("Sales") AS gender_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Gender
),
RankedCityGenderSales AS (
    SELECT City,
           Gender,
           gender_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY gender_sales ASC) AS sales_rank
    FROM CityGenderSales
),
OverallGenderAvgMetrics AS (
    SELECT Gender,
           AVG("Sales") AS overall_avg_sales_per_gender,
           AVG(Rating) AS overall_avg_rating_per_gender
    FROM SuperMarketAnalysis
    GROUP BY Gender
)
SELECT rcgs.City,
       rcgs.Gender,
       rcgs.gender_sales,
       (rcgs.gender_sales * 100.0 / rcgs.city_total_sales) AS percentage_of_city_sales,
       ogam.overall_avg_sales_per_gender,
       ogam.overall_avg_rating_per_gender
FROM RankedCityGenderSales rcgs
JOIN OverallGenderAvgMetrics ogam
ON rcgs.Gender = ogam.Gender
WHERE rcgs.sales_rank = 1
ORDER BY rcgs.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG(Rating) AS overall_avg_rating_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_rating_per_product_line
FROM ProductLineAvgRatingSales plars
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plars."Product line" = ploam."Product line"
WHERE plars.avg_rating < oam.overall_avg_rating
  AND plars.total_sales > oam.overall_avg_sales
ORDER BY plars.avg_rating ASC, plars.total_sales DESC;

WITH CityPaymentSales AS (
    SELECT City,
           Payment,
           SUM("Sales") AS payment_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Payment
),
RankedCityPaymentSales AS (
    SELECT City,
           Payment,
           payment_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY payment_sales DESC) AS sales_rank
    FROM CityPaymentSales
),
OverallPaymentAvgMetrics AS (
    SELECT Payment,
           AVG("Sales") AS overall_avg_sales_per_payment,
           AVG(Rating) AS overall_avg_rating_per_payment
    FROM SuperMarketAnalysis
    GROUP BY Payment
)
SELECT rcps.City,
       rcps.Payment,
       rcps.payment_sales,
       (rcps.payment_sales * 100.0 / rcps.city_total_sales) AS percentage_of_city_sales,
       opam.overall_avg_sales_per_payment,
       opam.overall_avg_rating_per_payment
FROM RankedCityPaymentSales rcps
JOIN OverallPaymentAvgMetrics opam
ON rcps.Payment = opam.Payment
WHERE rcps.sales_rank = 1
ORDER BY rcps.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - oam.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_gross_margin_percentage_per_product_line
FROM ProductLineMetrics plm
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plm."Product line" = ploam."Product line"
WHERE plm.gross_margin_percentage < oam.overall_avg_gross_margin_percentage
  AND plm.total_sales > oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage ASC, plm.total_sales DESC;

WITH CityPaymentSales AS (
    SELECT City,
           Payment,
           SUM("Sales") AS payment_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Payment
),
RankedCityPaymentSales AS (
    SELECT City,
           Payment,
           payment_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY payment_sales ASC) AS sales_rank
    FROM CityPaymentSales
),
OverallPaymentAvgMetrics AS (
    SELECT Payment,
           AVG("Sales") AS overall_avg_sales_per_payment,
           AVG(Rating) AS overall_avg_rating_per_payment
    FROM SuperMarketAnalysis
    GROUP BY Payment
)
SELECT rcps.City,
       rcps.Payment,
       rcps.payment_sales,
       (rcps.payment_sales * 100.0 / rcps.city_total_sales) AS percentage_of_city_sales,
       opam.overall_avg_sales_per_payment,
       opam.overall_avg_rating_per_payment
FROM RankedCityPaymentSales rcps
JOIN OverallPaymentAvgMetrics opam
ON rcps.Payment = opam.Payment
WHERE rcps.sales_rank = 1
ORDER BY rcps.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG(Rating) AS overall_avg_rating_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_rating_per_product_line
FROM ProductLineAvgRatingSales plars
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plars."Product line" = ploam."Product line"
WHERE plars.avg_rating > oam.overall_avg_rating
  AND plars.total_sales < oam.overall_avg_sales
ORDER BY plars.avg_rating DESC, plars.total_sales ASC;

WITH DailyCitySales AS (
    SELECT City,
           DATE("Date") AS sales_date,
           SUM("Sales") AS daily_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, DATE("Date")
),
RankedDailyCitySales AS (
    SELECT City,
           sales_date,
           daily_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY daily_sales DESC) AS date_rank
    FROM DailyCitySales
),
OverallDailyAvgMetrics AS (
    SELECT DATE("Date") AS sales_date,
           AVG("Sales") AS overall_avg_sales_per_date,
           AVG(Rating) AS overall_avg_rating_per_date
    FROM SuperMarketAnalysis
    GROUP BY DATE("Date")
)
SELECT rdcs.City,
       rdcs.sales_date,
       rdcs.daily_sales,
       (rdcs.daily_sales * 100.0 / rdcs.city_total_sales) AS percentage_of_city_sales,
       odam.overall_avg_sales_per_date,
       odam.overall_avg_rating_per_date
FROM RankedDailyCitySales rdcs
JOIN OverallDailyAvgMetrics odam
ON rdcs.sales_date = odam.sales_date
WHERE rdcs.date_rank = 1
ORDER BY rdcs.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - oam.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_gross_margin_percentage_per_product_line
FROM ProductLineMetrics plm
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plm."Product line" = ploam."Product line"
WHERE plm.gross_margin_percentage < oam.overall_avg_gross_margin_percentage
  AND plm.total_sales < oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage ASC, plm.total_sales ASC;

WITH DailyCitySales AS (
    SELECT City,
           DATE("Date") AS sales_date,
           SUM("Sales") AS daily_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, DATE("Date")
),
RankedDailyCitySales AS (
    SELECT City,
           sales_date,
           daily_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY daily_sales ASC) AS date_rank
    FROM DailyCitySales
),
OverallDailyAvgMetrics AS (
    SELECT DATE("Date") AS sales_date,
           AVG("Sales") AS overall_avg_sales_per_date,
           AVG(Rating) AS overall_avg_rating_per_date
    FROM SuperMarketAnalysis
    GROUP BY DATE("Date")
)
SELECT rdcs.City,
       rdcs.sales_date,
       rdcs.daily_sales,
       (rdcs.daily_sales * 100.0 / rdcs.city_total_sales) AS percentage_of_city_sales,
       odam.overall_avg_sales_per_date,
       odam.overall_avg_rating_per_date
FROM RankedDailyCitySales rdcs
JOIN OverallDailyAvgMetrics odam
ON rdcs.sales_date = odam.sales_date
WHERE rdcs.date_rank = 1
ORDER BY rdcs.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG(Rating) AS overall_avg_rating_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_rating_per_product_line
FROM ProductLineAvgRatingSales plars
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plars."Product line" = ploam."Product line"
WHERE plars.avg_rating < oam.overall_avg_rating
  AND plars.total_sales < oam.overall_avg_sales
ORDER BY plars.avg_rating ASC, plars.total_sales ASC;

WITH MonthlyCitySales AS (
    SELECT City,
           STRFTIME('%Y-%m', "Date") AS sales_month,
           SUM("Sales") AS monthly_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, sales_month
),
RankedMonthlyCitySales AS (
    SELECT City,
           sales_month,
           monthly_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY monthly_sales DESC) AS month_rank
    FROM MonthlyCitySales
),
OverallMonthlyAvgMetrics AS (
    SELECT STRFTIME('%Y-%m', "Date") AS sales_month,
           AVG("Sales") AS overall_avg_sales_per_month,
           AVG(Rating) AS overall_avg_rating_per_month
    FROM SuperMarketAnalysis
    GROUP BY STRFTIME('%Y-%m', "Date")
)
SELECT rmcs.City,
       rmcs.sales_month,
       rmcs.monthly_sales,
       (rmcs.monthly_sales * 100.0 / rmcs.city_total_sales) AS percentage_of_city_sales,
       omam.overall_avg_sales_per_month,
       omam.overall_avg_rating_per_month
FROM RankedMonthlyCitySales rmcs
JOIN OverallMonthlyAvgMetrics omam
ON rmcs.sales_month = omam.sales_month
WHERE rmcs.month_rank = 1
ORDER BY rmcs.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - oam.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_gross_margin_percentage_per_product_line
FROM ProductLineMetrics plm
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plm."Product line" = ploam."Product line"
WHERE plm.gross_margin_percentage > oam.overall_avg_gross_margin_percentage
  AND plm.total_sales < oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage DESC, plm.total_sales ASC;

WITH MonthlyCitySales AS (
    SELECT City,
           STRFTIME('%Y-%m', "Date") AS sales_month,
           SUM("Sales") AS monthly_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, sales_month
),
RankedMonthlyCitySales AS (
    SELECT City,
           sales_month,
           monthly_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY monthly_sales ASC) AS month_rank
    FROM MonthlyCitySales
),
OverallMonthlyAvgMetrics AS (
    SELECT STRFTIME('%Y-%m', "Date") AS sales_month,
           AVG("Sales") AS overall_avg_sales_per_month,
           AVG(Rating) AS overall_avg_rating_per_month
    FROM SuperMarketAnalysis
    GROUP BY STRFTIME('%Y-%m', "Date")
)
SELECT rmcs.City,
       rmcs.sales_month,
       rmcs.monthly_sales,
       (rmcs.monthly_sales * 100.0 / rmcs.city_total_sales) AS percentage_of_city_sales,
       omam.overall_avg_sales_per_month,
       omam.overall_avg_rating_per_month
FROM RankedMonthlyCitySales rmcs
JOIN OverallMonthlyAvgMetrics omam
ON rmcs.sales_month = omam.sales_month
WHERE rmcs.month_rank = 1
ORDER BY rmcs.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG(Rating) AS overall_avg_rating_per_product_line,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_rating_per_product_line,
       ploam.overall_avg_gross_margin_percentage_per_product_line
FROM ProductLineAvgRatingSales plars
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plars."Product line" = ploam."Product line"
WHERE plars.avg_rating > oam.overall_avg_rating
  AND plars.total_sales > oam.overall_avg_sales
ORDER BY plars.avg_rating DESC, plars.total_sales DESC;

WITH CityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           SUM("Sales") AS customer_type_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, "Customer type"
),
RankedCityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           customer_type_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY customer_type_sales DESC) AS sales_rank
    FROM CityCustomerTypeSales
),
OverallCustomerTypeAvgMetrics AS (
    SELECT "Customer type",
           AVG("Sales") AS overall_avg_sales_per_customer_type,
           AVG(Rating) AS overall_avg_rating_per_customer_type,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_customer_type
    FROM SuperMarketAnalysis
    GROUP BY "Customer type"
)
SELECT rccs.City,
       rccs."Customer type",
       rccs.customer_type_sales,
       (rccs.customer_type_sales * 100.0 / rccs.city_total_sales) AS percentage_of_city_sales,
       octam.overall_avg_sales_per_customer_type,
       octam.overall_avg_rating_per_customer_type,
       octam.overall_avg_gross_margin_percentage_per_customer_type
FROM RankedCityCustomerTypeSales rccs
JOIN OverallCustomerTypeAvgMetrics octam
ON rccs."Customer type" = octam."Customer type"
WHERE rccs.sales_rank = 1
ORDER BY rccs.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_product_line,
           AVG(Rating) AS overall_avg_rating_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - oam.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_gross_margin_percentage_per_product_line,
       ploam.overall_avg_rating_per_product_line
FROM ProductLineMetrics plm
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plm."Product line" = ploam."Product line"
WHERE plm.gross_margin_percentage > oam.overall_avg_gross_margin_percentage
  AND plm.total_sales < oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage DESC, plm.total_sales ASC;

WITH CityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           SUM("Sales") AS customer_type_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, "Customer type"
),
RankedCityCustomerTypeSales AS (
    SELECT City,
           "Customer type",
           customer_type_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY customer_type_sales ASC) AS sales_rank
    FROM CityCustomerTypeSales
),
OverallCustomerTypeAvgMetrics AS (
    SELECT "Customer type",
           AVG("Sales") AS overall_avg_sales_per_customer_type,
           AVG(Rating) AS overall_avg_rating_per_customer_type,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_customer_type
    FROM SuperMarketAnalysis
    GROUP BY "Customer type"
)
SELECT rccs.City,
       rccs."Customer type",
       rccs.customer_type_sales,
       (rccs.customer_type_sales * 100.0 / rccs.city_total_sales) AS percentage_of_city_sales,
       octam.overall_avg_sales_per_customer_type,
       octam.overall_avg_rating_per_customer_type,
       octam.overall_avg_gross_margin_percentage_per_customer_type
FROM RankedCityCustomerTypeSales rccs
JOIN OverallCustomerTypeAvgMetrics octam
ON rccs."Customer type" = octam."Customer type"
WHERE rccs.sales_rank = 1
ORDER BY rccs.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG(Rating) AS overall_avg_rating_per_product_line,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_product_line,
           AVG("Unit price") AS overall_avg_unit_price_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_rating_per_product_line,
       ploam.overall_avg_gross_margin_percentage_per_product_line,
       ploam.overall_avg_unit_price_per_product_line
FROM ProductLineAvgRatingSales plars
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plars."Product line" = ploam."Product line"
WHERE plars.avg_rating > oam.overall_avg_rating
  AND plars.total_sales > oam.overall_avg_sales
ORDER BY plars.avg_rating DESC, plars.total_sales DESC;

WITH CityGenderSales AS (
    SELECT City,
           Gender,
           SUM("Sales") AS gender_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Gender
),
RankedCityGenderSales AS (
    SELECT City,
           Gender,
           gender_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY gender_sales DESC) AS sales_rank
    FROM CityGenderSales
),
OverallGenderAvgMetrics AS (
    SELECT Gender,
           AVG("Sales") AS overall_avg_sales_per_gender,
           AVG(Rating) AS overall_avg_rating_per_gender,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_gender
    FROM SuperMarketAnalysis
    GROUP BY Gender
)
SELECT rcgs.City,
       rcgs.Gender,
       rcgs.gender_sales,
       (rcgs.gender_sales * 100.0 / rcgs.city_total_sales) AS percentage_of_city_sales,
       ogam.overall_avg_sales_per_gender,
       ogam.overall_avg_rating_per_gender,
       ogam.overall_avg_gross_margin_percentage_per_gender
FROM RankedCityGenderSales rcgs
JOIN OverallGenderAvgMetrics ogam
ON rcgs.Gender = ogam.Gender
WHERE rcgs.sales_rank = 1
ORDER BY rcgs.City;

WITH ProductLineMetrics AS (
    SELECT "Product line",
           SUM("Sales") AS total_sales,
           SUM("gross income") AS total_gross_income,
           (SUM("gross income") * 100.0 / SUM("Sales")) AS gross_margin_percentage
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(total_sales) AS overall_avg_sales,
           AVG(gross_margin_percentage) AS overall_avg_gross_margin_percentage
    FROM ProductLineMetrics
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_product_line,
           AVG(Rating) AS overall_avg_rating_per_product_line,
           AVG("Unit price") AS overall_avg_unit_price_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plm."Product line",
       plm.total_sales,
       plm.total_gross_income,
       plm.gross_margin_percentage,
       (plm.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       (plm.gross_margin_percentage - oam.overall_avg_gross_margin_percentage) AS gross_margin_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_gross_margin_percentage_per_product_line,
       ploam.overall_avg_rating_per_product_line,
       ploam.overall_avg_unit_price_per_product_line
FROM ProductLineMetrics plm
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plm."Product line" = ploam."Product line"
WHERE plm.gross_margin_percentage > oam.overall_avg_gross_margin_percentage
  AND plm.total_sales > oam.overall_avg_sales
ORDER BY plm.gross_margin_percentage DESC, plm.total_sales DESC;

WITH CityGenderSales AS (
    SELECT City,
           Gender,
           SUM("Sales") AS gender_sales,
           SUM(SUM("Sales")) OVER (PARTITION BY City) AS city_total_sales
    FROM SuperMarketAnalysis
    GROUP BY City, Gender
),
RankedCityGenderSales AS (
    SELECT City,
           Gender,
           gender_sales,
           city_total_sales,
           RANK() OVER (PARTITION BY City ORDER BY gender_sales ASC) AS sales_rank
    FROM CityGenderSales
),
OverallGenderAvgMetrics AS (
    SELECT Gender,
           AVG("Sales") AS overall_avg_sales_per_gender,
           AVG(Rating) AS overall_avg_rating_per_gender,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_gender
    FROM SuperMarketAnalysis
    GROUP BY Gender
)
SELECT rcgs.City,
       rcgs.Gender,
       rcgs.gender_sales,
       (rcgs.gender_sales * 100.0 / rcgs.city_total_sales) AS percentage_of_city_sales,
       ogam.overall_avg_sales_per_gender,
       ogam.overall_avg_rating_per_gender,
       ogam.overall_avg_gross_margin_percentage_per_gender
FROM RankedCityGenderSales rcgs
JOIN OverallGenderAvgMetrics ogam
ON rcgs.Gender = ogam.Gender
WHERE rcgs.sales_rank = 1
ORDER BY rcgs.City;

WITH ProductLineAvgRatingSales AS (
    SELECT "Product line",
           AVG(Rating) AS avg_rating,
           SUM("Sales") AS total_sales
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
),
OverallAvgMetrics AS (
    SELECT AVG(Rating) AS overall_avg_rating,
           AVG("Sales") AS overall_avg_sales
    FROM SuperMarketAnalysis
),
ProductLineOverallAvgMetrics AS (
    SELECT "Product line",
           AVG("Sales") AS overall_avg_sales_per_product_line,
           AVG(Rating) AS overall_avg_rating_per_product_line,
           AVG("gross margin percentage") AS overall_avg_gross_margin_percentage_per_product_line,
           AVG("Unit price") AS overall_avg_unit_price_per_product_line
    FROM SuperMarketAnalysis
    GROUP BY "Product line"
)
SELECT plars."Product line",
       plars.avg_rating,
       plars.total_sales,
       (plars.avg_rating - oam.overall_avg_rating) AS rating_difference_from_avg,
       (plars.total_sales - oam.overall_avg_sales) AS sales_difference_from_avg,
       ploam.overall_avg_sales_per_product_line,
       ploam.overall_avg_rating_per_product_line,
       ploam.overall_avg_gross_margin_percentage_per_product_line,
       ploam.overall_avg_unit_price_per_product_line
FROM ProductLineAvgRatingSales plars
JOIN OverallAvgMetrics oam
JOIN ProductLineOverallAvgMetrics ploam
ON plars."Product line" = ploam."Product line"
WHERE plars.avg_rating < oam.overall_avg_rating
  AND plars.total_sales > oam.overall_avg_sales
ORDER BY plars.avg_rating ASC, plars.total_sales DESC;