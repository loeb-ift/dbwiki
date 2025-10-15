SELECT * FROM products WHERE part_number = 'E-2025-000945';

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

SELECT product_name, category FROM products WHERE category = 'Electronics';

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

SELECT p.product_name, SUM(s.shipped_quantity) AS total_shipped FROM products p JOIN shipments s ON p.part_number = s.part_number WHERE p.category = 'Software' GROUP BY p.product_name ORDER BY total_shipped DESC LIMIT 10;

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000604';

SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);

SELECT p.part_number, p.product_name, i.quantity, (SELECT COUNT(*) FROM shipments s WHERE s.part_number = p.part_number) AS shipment_count FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.category = 'Electronics' ORDER BY shipment_count DESC;

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

SELECT AVG(shipped_quantity) FROM shipments WHERE part_number = 'E-2025-000217';

SELECT AVG(shipped_quantity) FROM shipments WHERE part_number = 'MEC-66849549';

SELECT p.part_number, p.product_name FROM products p LEFT JOIN inventory i ON p.part_number = i.part_number WHERE i.quantity IS NULL OR i.quantity = 0;

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000933';

SELECT i.location, COUNT(p.product_id) AS num_products FROM products p JOIN inventory i ON p.part_number = i.part_number GROUP BY i.location;

SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);

SELECT product_name, category FROM products WHERE category = 'Mechanical';

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000884';

SELECT i.location, COUNT(p.product_id) AS num_products FROM products p JOIN inventory i ON p.part_number = i.part_number GROUP BY i.location;

SELECT p.product_name, i.quantity, i.location FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number = 'MEC-41041731';

SELECT p.part_number, p.product_name, i.quantity, (SELECT COUNT(*) FROM shipments s WHERE s.part_number = p.part_number) AS shipment_count FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.category = 'Electronics' ORDER BY shipment_count DESC;

SELECT p.product_name, i.quantity, SUM(s.shipped_quantity) AS total_shipped FROM products p JOIN inventory i ON p.part_number = i.part_number JOIN shipments s ON p.part_number = s.part_number WHERE p.category = 'Electronics' GROUP BY p.product_name, i.quantity HAVING i.quantity < 50;

SELECT i.location, COUNT(p.product_id) AS num_products FROM products p JOIN inventory i ON p.part_number = i.part_number GROUP BY i.location;

SELECT p.part_number, p.product_name FROM products p LEFT JOIN inventory i ON p.part_number = i.part_number WHERE i.quantity IS NULL OR i.quantity = 0;

SELECT p.part_number, p.product_name, i.quantity, (SELECT COUNT(*) FROM shipments s WHERE s.part_number = p.part_number) AS shipment_count FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.category = 'Electronics' ORDER BY shipment_count DESC;

SELECT p.product_name, i.quantity, i.location FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number = 'ASM-63284924';

SELECT p.part_number, p.product_name, i.quantity, (SELECT COUNT(*) FROM shipments s WHERE s.part_number = p.part_number) AS shipment_count FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.category = 'Electronics' ORDER BY shipment_count DESC;

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000766';

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000223';

SELECT COUNT(*) FROM shipments WHERE part_number = 'SW-CS60-V4-OOFZV';

SELECT * FROM products WHERE part_number = 'SW-CS60-V1-Q96A1';

SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);

SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);

WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000740';

SELECT AVG(shipped_quantity) FROM shipments WHERE part_number = 'E-2025-000689';

SELECT p.product_name, SUM(s.shipped_quantity) AS total_shipped FROM products p JOIN shipments s ON p.part_number = s.part_number WHERE p.category = 'Mechanical' GROUP BY p.product_name ORDER BY total_shipped DESC LIMIT 10;

SELECT product_name, category FROM products WHERE category = 'Mechanical';

SELECT product_name, category FROM products WHERE category = 'Software';

WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000228';

SELECT p.product_name, i.quantity, i.location FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number = 'ASM-31573902';

WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;

SELECT * FROM products WHERE part_number = 'E-2025-000491';

WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;

SELECT p.part_number, p.product_name FROM products p LEFT JOIN inventory i ON p.part_number = i.part_number WHERE i.quantity IS NULL OR i.quantity = 0;

SELECT COUNT(*) FROM shipments WHERE part_number = 'E-2025-000422';

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000293';

SELECT p.product_name, SUM(s.shipped_quantity) AS total_shipped FROM products p JOIN shipments s ON p.part_number = s.part_number WHERE p.category = 'Electronics' GROUP BY p.product_name ORDER BY total_shipped DESC LIMIT 10;

WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;

SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);

SELECT p.product_name, i.quantity, i.location FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number = 'E-2025-000331';

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000954';

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000118';

SELECT AVG(shipped_quantity) FROM shipments WHERE part_number = 'ASM-34038277';

SELECT COUNT(*) FROM shipments WHERE part_number = 'E-2025-000773';

SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);

SELECT p.part_number, p.product_name FROM products p LEFT JOIN inventory i ON p.part_number = i.part_number WHERE i.quantity IS NULL OR i.quantity = 0;

SELECT p.product_name, i.quantity, SUM(s.shipped_quantity) AS total_shipped FROM products p JOIN inventory i ON p.part_number = i.part_number JOIN shipments s ON p.part_number = s.part_number WHERE p.category = 'Software' GROUP BY p.product_name, i.quantity HAVING i.quantity < 50;

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

SELECT i.location, COUNT(p.product_id) AS num_products FROM products p JOIN inventory i ON p.part_number = i.part_number GROUP BY i.location;

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

SELECT p.product_name, SUM(s.shipped_quantity) AS total_shipped FROM products p JOIN shipments s ON p.part_number = s.part_number WHERE p.category = 'Mechanical' GROUP BY p.product_name ORDER BY total_shipped DESC LIMIT 10;

SELECT i.location, COUNT(p.product_id) AS num_products FROM products p JOIN inventory i ON p.part_number = i.part_number GROUP BY i.location;

SELECT quantity, location FROM inventory WHERE part_number = 'SW-CS60-V3-IFADY';

SELECT p.product_name, i.quantity, SUM(s.shipped_quantity) AS total_shipped FROM products p JOIN inventory i ON p.part_number = i.part_number JOIN shipments s ON p.part_number = s.part_number WHERE p.category = 'Software' GROUP BY p.product_name, i.quantity HAVING i.quantity < 50;

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

SELECT * FROM products WHERE part_number = 'SW-CS60-V1-O33A0';

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

SELECT i.location, COUNT(p.product_id) AS num_products FROM products p JOIN inventory i ON p.part_number = i.part_number GROUP BY i.location;

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;

SELECT p.part_number, p.product_name, i.quantity, (SELECT COUNT(*) FROM shipments s WHERE s.part_number = p.part_number) AS shipment_count FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.category = 'Electronics' ORDER BY shipment_count DESC;

SELECT DISTINCT p.product_name FROM products p WHERE p.part_number LIKE 'E-%' AND p.part_number NOT IN (SELECT DISTINCT part_number FROM shipments);

SELECT * FROM products WHERE part_number = 'E-2025-000487';

WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;

SELECT * FROM products WHERE part_number = 'E-2025-000196';

WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000539';

SELECT AVG(shipped_quantity) FROM shipments WHERE part_number = 'ASM-29406294';

SELECT AVG(shipped_quantity) FROM shipments WHERE part_number = 'CNC-66919838';

SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);

SELECT quantity, location FROM inventory WHERE part_number = 'E-2025-000951';

SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);

SELECT p.product_name, i.quantity, i.location FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number = 'SW-VS22-V2-VUHJ5';

SELECT p.product_name, i.quantity, SUM(s.shipped_quantity) AS total_shipped FROM products p JOIN inventory i ON p.part_number = i.part_number JOIN shipments s ON p.part_number = s.part_number WHERE p.category = 'Mechanical' GROUP BY p.product_name, i.quantity HAVING i.quantity < 50;

WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;

SELECT product_name, category FROM products WHERE category = 'Software';

WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;

SELECT quantity, location FROM inventory WHERE part_number = 'SW-PH10-V5-7KYA5';

SELECT AVG(shipped_quantity) FROM shipments WHERE part_number = 'E-2025-000465';

SELECT p.product_name, p.category, i.quantity FROM products p JOIN inventory i ON p.part_number = i.part_number WHERE p.part_number IN (SELECT part_number FROM shipments WHERE shipped_quantity > 15);

WITH MonthlyShipments AS (SELECT part_number, SUM(shipped_quantity) AS monthly_total FROM shipments WHERE shipment_date >= date('now', '-30 days') GROUP BY part_number) SELECT p.product_name, ms.monthly_total FROM products p JOIN MonthlyShipments ms ON p.part_number = ms.part_number ORDER BY ms.monthly_total DESC LIMIT 5;

SELECT product_name, category FROM products WHERE category = 'Electronics';

SELECT i.location, COUNT(p.product_id) AS num_products FROM products p JOIN inventory i ON p.part_number = i.part_number GROUP BY i.location;

SELECT i.location, COUNT(p.product_id) AS num_products FROM products p JOIN inventory i ON p.part_number = i.part_number GROUP BY i.location;

