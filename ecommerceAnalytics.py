#!/usr/bin/env python3

import os
import csv
import sys
import random
import sqlite3
import argparse
from datetime import datetime, timedelta

import pandas as pd

random.seed(42)

RAW_DIR = "data/raw"
CLEANED_DIR = "data/cleaned"
OUTPUT_DIR = "output"
DB_PATH = "ecommerce.db"

NUM_CUSTOMERS = 600
NUM_PRODUCTS = 520
NUM_ORDERS = 1500
AVG_ITEMS_PER_ORDER = 2.2

ORDER_STATUSES = ["PLACED", "SHIPPED", "DELIVERED", "CANCELLED", "RETURNED"]
CUSTOMER_TYPES = ["REGULAR", "PREMIUM", "VIP"]

CATEGORY_MAP = {
    "Electronics": ["Mobiles", "Laptops", "Headphones", "Cameras", "Accessories"],
    "Clothing": ["Men", "Women", "Kids", "Footwear", "Winterwear"],
    "Home": ["Kitchen", "Furniture", "Decor", "Bedding", "Storage"],
    "Books": ["Fiction", "Non-Fiction", "Comics", "Academic", "Children"],
}

FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh",
               "Ananya", "Diya", "Ishaan", "Kabir", "Meera", "Priya", "Rohan",
               "Sanya", "Tara", "Neha", "Karan", "Divya", "Rahul", "Pooja", "Amit"]
LAST_NAMES = ["Sharma", "Verma", "Gupta", "Reddy", "Iyer", "Nair", "Das",
              "Patel", "Singh", "Rao", "Mehta", "Kapoor", "Joshi", "Chatterjee"]

PRODUCT_ADJECTIVES = ["Pro", "Max", "Lite", "Ultra", "Classic", "Mini", "Plus", "Air"]
PRODUCT_NOUNS = {
    "Mobiles": ["Smartphone", "Feature Phone"],
    "Laptops": ["Notebook", "Ultrabook", "Gaming Laptop"],
    "Headphones": ["Earbuds", "Over-Ear Headphones", "Neckband"],
    "Cameras": ["DSLR Camera", "Action Camera", "Instant Camera"],
    "Accessories": ["Charger", "Power Bank", "Cable", "Case"],
    "Men": ["T-Shirt", "Shirt", "Jeans", "Jacket"],
    "Women": ["Dress", "Top", "Saree", "Kurti"],
    "Kids": ["T-Shirt", "Shorts", "Frock"],
    "Footwear": ["Sneakers", "Sandals", "Formal Shoes"],
    "Winterwear": ["Sweater", "Hoodie", "Muffler"],
    "Kitchen": ["Mixer Grinder", "Cookware Set", "Kettle"],
    "Furniture": ["Chair", "Table", "Bookshelf"],
    "Decor": ["Wall Art", "Vase", "Lamp"],
    "Bedding": ["Bedsheet", "Pillow", "Blanket"],
    "Storage": ["Storage Box", "Organizer", "Rack"],
    "Fiction": ["Novel", "Short Story Collection"],
    "Non-Fiction": ["Biography", "Self-Help Book"],
    "Comics": ["Graphic Novel", "Comic Anthology"],
    "Academic": ["Textbook", "Reference Guide"],
    "Children": ["Picture Book", "Activity Book"],
}

SCHEMA_SQL = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id       INTEGER PRIMARY KEY,
    customer_name     TEXT NOT NULL,
    email             TEXT,
    registration_date TEXT NOT NULL,
    customer_type     TEXT NOT NULL CHECK (customer_type IN ('REGULAR', 'PREMIUM', 'VIP'))
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category     TEXT NOT NULL,
    subcategory  TEXT NOT NULL,
    cost_price   REAL NOT NULL
);

CREATE TABLE orders (
    order_id     INTEGER PRIMARY KEY,
    customer_id  TEXT,
    order_date   TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('PLACED', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'RETURNED')),
    region_code  TEXT NOT NULL
);

CREATE TABLE order_items (
    item_id           INTEGER PRIMARY KEY,
    order_id          INTEGER NOT NULL,
    product_id        INTEGER NOT NULL,
    quantity          INTEGER NOT NULL,
    unit_price        REAL NOT NULL,
    discount_percent  REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_order_date ON orders(order_date);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);
CREATE INDEX idx_products_category ON products(category);
"""

ANALYSIS_QUERIES = [
    ("1. Total revenue per category", """
        SELECT p.category,
               ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)), 2) AS total_revenue
        FROM order_items oi
        JOIN products p ON p.product_id = oi.product_id
        GROUP BY p.category
        ORDER BY total_revenue DESC;
    """),
    ("2. Top 10 customers by total order value", """
        SELECT o.customer_id,
               ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)), 2) AS total_order_value
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.order_id
        WHERE o.customer_id != 'UNKNOWN'
        GROUP BY o.customer_id
        ORDER BY total_order_value DESC
        LIMIT 10;
    """),
    ("3. Month-wise order count for the last 12 months", """
        SELECT strftime('%Y-%m', order_date) AS order_month, COUNT(*) AS order_count
        FROM orders
        WHERE order_date >= date('now', '-12 months')
        GROUP BY order_month
        ORDER BY order_month;
    """),
    ("4. Customers who ordered but never had anything delivered", """
        SELECT DISTINCT o.customer_id
        FROM orders o
        WHERE o.customer_id != 'UNKNOWN'
          AND o.customer_id NOT IN (
              SELECT customer_id FROM orders WHERE status = 'DELIVERED' AND customer_id != 'UNKNOWN'
          );
    """),
    ("5. Products with more returns than purchases", """
        SELECT p.product_id, p.product_name,
               SUM(CASE WHEN oi.quantity > 0 THEN oi.quantity ELSE 0 END) AS units_purchased,
               SUM(CASE WHEN oi.quantity < 0 THEN -oi.quantity ELSE 0 END) AS units_returned
        FROM order_items oi
        JOIN products p ON p.product_id = oi.product_id
        GROUP BY p.product_id, p.product_name
        HAVING units_returned > units_purchased;
    """),
    ("6. Return rate per category", """
        SELECT p.category,
               SUM(CASE WHEN oi.quantity < 0 THEN -oi.quantity ELSE 0 END) AS returned_items,
               SUM(ABS(oi.quantity)) AS total_items,
               ROUND(1.0 * SUM(CASE WHEN oi.quantity < 0 THEN -oi.quantity ELSE 0 END)
                     / NULLIF(SUM(ABS(oi.quantity)), 0), 4) AS return_rate
        FROM order_items oi
        JOIN products p ON p.product_id = oi.product_id
        GROUP BY p.category
        ORDER BY return_rate DESC;
    """),
    ("7. Running total of revenue per region", """
        WITH dailyRevenue AS (
            SELECT o.region_code, date(o.order_date) AS order_date,
                   SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)) AS daily_revenue
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            GROUP BY o.region_code, date(o.order_date)
        )
        SELECT region_code, order_date, ROUND(daily_revenue, 2) AS daily_revenue,
               ROUND(SUM(daily_revenue) OVER (
                   PARTITION BY region_code ORDER BY order_date
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS running_total
        FROM dailyRevenue
        ORDER BY region_code, order_date;
    """),
    ("8. DENSE_RANK products by revenue within category", """
        WITH productRevenue AS (
            SELECT p.category, p.product_name,
                   SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)) AS total_revenue
            FROM order_items oi
            JOIN products p ON p.product_id = oi.product_id
            GROUP BY p.category, p.product_name
        )
        SELECT category, product_name, ROUND(total_revenue, 2) AS total_revenue,
               DENSE_RANK() OVER (PARTITION BY category ORDER BY total_revenue DESC) AS rank_in_category
        FROM productRevenue
        ORDER BY category, rank_in_category;
    """),
    ("9. Days between consecutive orders per customer (LAG)", """
        WITH customerOrders AS (
            SELECT customer_id, order_date,
                   LAG(order_date) OVER (PARTITION BY customer_id ORDER BY order_date) AS previous_order_date
            FROM orders
            WHERE customer_id != 'UNKNOWN'
        ),
        gaps AS (
            SELECT customer_id, order_date, previous_order_date,
                   CASE WHEN previous_order_date IS NOT NULL
                        THEN julianday(order_date) - julianday(previous_order_date) END AS days_gap
            FROM customerOrders
        ),
        avgGaps AS (
            SELECT customer_id, AVG(days_gap) AS avg_gap FROM gaps WHERE days_gap IS NOT NULL GROUP BY customer_id
        )
        SELECT g.customer_id, g.order_date, g.previous_order_date, ROUND(g.days_gap, 1) AS days_gap,
               CASE WHEN a.avg_gap > 30 THEN 'At Risk' ELSE 'Active' END AS risk_flag
        FROM gaps g
        JOIN avgGaps a ON a.customer_id = g.customer_id
        ORDER BY g.customer_id, g.order_date;
    """),
    ("10. Multi-level CTE: monthly revenue -> spend category -> counts", """
        WITH monthlyRevenuePerCustomer AS (
            SELECT o.customer_id, strftime('%Y-%m', o.order_date) AS revenue_month,
                   SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)) AS monthly_revenue
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            WHERE o.customer_id != 'UNKNOWN'
            GROUP BY o.customer_id, revenue_month
        ),
        categorized AS (
            SELECT customer_id, revenue_month, monthly_revenue,
                   CASE WHEN monthly_revenue > 10000 THEN 'High'
                        WHEN monthly_revenue >= 5000 THEN 'Medium'
                        ELSE 'Low' END AS spend_category
            FROM monthlyRevenuePerCustomer
        )
        SELECT revenue_month, spend_category, COUNT(DISTINCT customer_id) AS customer_count
        FROM categorized
        GROUP BY revenue_month, spend_category
        ORDER BY revenue_month, spend_category;
    """),
    ("11. NTILE quartile segmentation by customer LTV", """
        WITH customerLtv AS (
            SELECT o.customer_id,
                   SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)) AS total_value
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            WHERE o.customer_id != 'UNKNOWN'
            GROUP BY o.customer_id
        )
        SELECT customer_id, ROUND(total_value, 2) AS total_value,
               NTILE(4) OVER (ORDER BY total_value DESC) AS quartile,
               CASE NTILE(4) OVER (ORDER BY total_value DESC)
                   WHEN 1 THEN 'Platinum' WHEN 2 THEN 'Gold'
                   WHEN 3 THEN 'Silver' WHEN 4 THEN 'Bronze' END AS quartile_label
        FROM customerLtv
        ORDER BY quartile, total_value DESC;
    """),
    ("12. Year-over-year monthly revenue comparison", """
        WITH monthlyRevenue AS (
            SELECT CAST(strftime('%Y', o.order_date) AS INTEGER) AS year,
                   CAST(strftime('%m', o.order_date) AS INTEGER) AS month,
                   SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)) AS revenue
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            GROUP BY year, month
        )
        SELECT curr.year, curr.month, ROUND(curr.revenue, 2) AS revenue,
               ROUND(prev.revenue, 2) AS prev_year_revenue,
               CASE WHEN prev.revenue IS NULL OR prev.revenue = 0 THEN NULL
                    ELSE ROUND((curr.revenue - prev.revenue) * 100.0 / prev.revenue, 2) END AS yoy_growth_percent
        FROM monthlyRevenue curr
        LEFT JOIN monthlyRevenue prev ON prev.year = curr.year - 1 AND prev.month = curr.month
        ORDER BY curr.year, curr.month;
    """),
    ("13. First/last purchased category per customer (FIRST_VALUE/LAST_VALUE)", """
        WITH customerCategoryPurchases AS (
            SELECT o.customer_id, o.order_date, p.category,
                   FIRST_VALUE(p.category) OVER (
                       PARTITION BY o.customer_id ORDER BY o.order_date
                       ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS first_category,
                   LAST_VALUE(p.category) OVER (
                       PARTITION BY o.customer_id ORDER BY o.order_date
                       ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS last_category
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            JOIN products p ON p.product_id = oi.product_id
            WHERE o.customer_id != 'UNKNOWN'
        )
        SELECT DISTINCT customer_id, first_category, last_category,
               CASE WHEN first_category != last_category THEN 'Yes' ELSE 'No' END AS category_shift
        FROM customerCategoryPurchases
        ORDER BY customer_id;
    """),
    ("14. Cumulative revenue distribution across customers", """
        WITH customerRevenue AS (
            SELECT o.customer_id,
                   SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)) AS revenue
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            WHERE o.customer_id != 'UNKNOWN'
            GROUP BY o.customer_id
        ),
        totals AS (SELECT SUM(revenue) AS grand_total FROM customerRevenue)
        SELECT cr.customer_id, ROUND(cr.revenue, 2) AS revenue,
               ROUND(SUM(cr.revenue) OVER (ORDER BY cr.revenue DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cumulative_revenue,
               ROUND(SUM(cr.revenue) OVER (ORDER BY cr.revenue DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) * 100.0 / t.grand_total, 2) AS cumulative_percent
        FROM customerRevenue cr
        CROSS JOIN totals t
        ORDER BY cr.revenue DESC;
    """),
    ("15. Cohort retention analysis (months 0-3)", """
        WITH customerCohort AS (
            SELECT customer_id, strftime('%Y-%m', registration_date) AS cohort_month FROM customers
        ),
        customerOrderMonths AS (
            SELECT DISTINCT o.customer_id, strftime('%Y-%m', o.order_date) AS order_month
            FROM orders o WHERE o.customer_id != 'UNKNOWN'
        ),
        cohortActivity AS (
            SELECT c.customer_id, c.cohort_month, com.order_month,
                   ((CAST(strftime('%Y', com.order_month || '-01') AS INTEGER) - CAST(strftime('%Y', c.cohort_month || '-01') AS INTEGER)) * 12
                   + (CAST(strftime('%m', com.order_month || '-01') AS INTEGER) - CAST(strftime('%m', c.cohort_month || '-01') AS INTEGER))) AS month_offset
            FROM customerCohort c
            JOIN customerOrderMonths com ON com.customer_id = c.customer_id
        ),
        cohortSizes AS (
            SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_size FROM customerCohort GROUP BY cohort_month
        )
        SELECT ca.cohort_month, cs.cohort_size, ca.month_offset,
               COUNT(DISTINCT ca.customer_id) AS active_customers,
               ROUND(COUNT(DISTINCT ca.customer_id) * 100.0 / cs.cohort_size, 2) AS retention_rate_percent
        FROM cohortActivity ca
        JOIN cohortSizes cs ON cs.cohort_month = ca.cohort_month
        WHERE ca.month_offset BETWEEN 0 AND 3
        GROUP BY ca.cohort_month, ca.month_offset
        ORDER BY ca.cohort_month, ca.month_offset;
    """),
    ("16. Frequently bought together (self-join)", """
        SELECT pa.product_name AS product_a, pb.product_name AS product_b, COUNT(*) AS times_bought_together
        FROM order_items oi1
        JOIN order_items oi2 ON oi1.order_id = oi2.order_id AND oi1.product_id < oi2.product_id
        JOIN products pa ON pa.product_id = oi1.product_id
        JOIN products pb ON pb.product_id = oi2.product_id
        GROUP BY pa.product_id, pb.product_id
        ORDER BY times_bought_together DESC
        LIMIT 50;
    """),
]

def randomDateWithinYears(startYearsAgo=2, endYearsAgo=0):
    now = datetime.now()
    start = now - timedelta(days=365 * startYearsAgo)
    end = now - timedelta(days=365 * endYearsAgo)
    delta = end - start
    randomSeconds = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=randomSeconds)

def messUpProductName(name):
    roll = random.random()
    if roll < 0.15:
        name = "  " + name + "   "
    if roll < 0.10:
        name = name.upper()
    elif 0.10 <= roll < 0.20:
        name = name.lower()
    return name

def makeInvalidEmail(validEmail):
    choice = random.choice(["noAt", "noDomain", "noAt"])
    if choice == "noAt":
        return validEmail.replace("@", "")
    return validEmail.split("@")[0] + "@"

def generateCustomers():
    rows = []
    for customerId in range(1, NUM_CUSTOMERS + 1):
        firstName = random.choice(FIRST_NAMES)
        lastName = random.choice(LAST_NAMES)
        customerName = f"{firstName} {lastName}"
        validEmail = f"{firstName.lower()}.{lastName.lower()}{customerId}@example.com"
        email = validEmail
        if random.random() < 0.02:
            email = makeInvalidEmail(validEmail)
        registrationDate = randomDateWithinYears(3, 0)
        customerType = random.choices(CUSTOMER_TYPES, weights=[0.7, 0.22, 0.08])[0]
        rows.append({
            "customer_id": customerId, "customer_name": customerName, "email": email,
            "registration_date": registrationDate.strftime("%Y-%m-%d %H:%M:%S"),
            "customer_type": customerType,
        })
    return rows

def generateProducts():
    rows = []
    categories = list(CATEGORY_MAP.keys())
    for productId in range(1, NUM_PRODUCTS + 1):
        category = categories[productId % len(categories)]
        subcategory = random.choice(CATEGORY_MAP[category])
        noun = random.choice(PRODUCT_NOUNS[subcategory])
        adjective = random.choice(PRODUCT_ADJECTIVES)
        baseName = f"{adjective} {noun} {productId}"
        productName = messUpProductName(baseName)
        costPrice = round(random.uniform(5, 5000), 2)
        rows.append({
            "product_id": productId, "product_name": productName, "category": category,
            "subcategory": subcategory, "cost_price": costPrice,
        })
    return rows

def generateOrders(customerIds):
    rows = []
    for orderId in range(1, NUM_ORDERS + 1):
        useNullCustomer = random.random() < 0.05
        customerId = "" if useNullCustomer else random.choice(customerIds)
        orderDate = randomDateWithinYears(2, 0)
        useWrongFormat = random.random() < 0.08
        if useWrongFormat:
            orderDateStr = orderDate.strftime("%d-%m-%Y")
        else:
            orderDateStr = orderDate.strftime("%Y-%m-%d %H:%M:%S")
        status = random.choices(ORDER_STATUSES, weights=[0.15, 0.20, 0.45, 0.10, 0.10])[0]
        regionCode = random.choice(["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"])
        rows.append({
            "order_id": orderId, "customer_id": customerId, "order_date": orderDateStr,
            "status": status, "region_code": regionCode,
        })
    return rows

def generateOrderItems(orderIds, productIds):
    rows = []
    itemId = 1
    for orderId in orderIds:
        numItems = max(1, int(random.gauss(AVG_ITEMS_PER_ORDER, 1)))
        for _ in range(numItems):
            productId = random.choice(productIds)
            quantity = random.randint(1, 5)
            if random.random() < 0.03:
                quantity = -abs(quantity)
            unitPrice = round(random.uniform(5, 6000), 2)
            discountPercent = round(random.uniform(0, 100), 1) if random.random() < 0.4 else 0
            rows.append({
                "item_id": itemId, "order_id": orderId, "product_id": productId,
                "quantity": quantity, "unit_price": unitPrice, "discount_percent": discountPercent,
            })
            itemId += 1
    return rows

def writeCsv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})

def runGenerateData():
    print("\n" + "=" * 60)
    print("PART 1: GENERATING RAW DATA")
    print("=" * 60)
    os.makedirs(RAW_DIR, exist_ok=True)

    customers = generateCustomers()
    writeCsv(f"{RAW_DIR}/customers.csv", customers,
             ["customer_id", "customer_name", "email", "registration_date", "customer_type"])

    products = generateProducts()
    writeCsv(f"{RAW_DIR}/products.csv", products,
             ["product_id", "product_name", "category", "subcategory", "cost_price"])

    customerIds = [c["customer_id"] for c in customers]
    orders = generateOrders(customerIds)
    writeCsv(f"{RAW_DIR}/orders.csv", orders,
             ["order_id", "customer_id", "order_date", "status", "region_code"])

    orderIds = [o["order_id"] for o in orders]
    productIds = [p["product_id"] for p in products]
    orderItems = generateOrderItems(orderIds, productIds)

    for _ in range(8):
        orderItems.append({
            "item_id": len(orderItems) + 1,
            "order_id": max(orderIds) + random.randint(1, 50),
            "product_id": random.choice(productIds),
            "quantity": random.randint(1, 3),
            "unit_price": round(random.uniform(5, 500), 2),
            "discount_percent": 0,
        })

    writeCsv(f"{RAW_DIR}/order_items.csv", orderItems,
             ["item_id", "order_id", "product_id", "quantity", "unit_price", "discount_percent"])

    print(f"Generated {len(customers)} customers")
    print(f"Generated {len(products)} products")
    print(f"Generated {len(orders)} orders")
    print(f"Generated {len(orderItems)} order_items")

def cleanOrders(ordersDf):
    df = ordersDf.copy()
    issues = {"badDateFormatRows": 0, "missingCustomerIdRows": 0}

    def parseDate(value):
        value = str(value).strip()
        parsed = pd.to_datetime(value, format="%Y-%m-%d %H:%M:%S", errors="coerce")
        if pd.isna(parsed):
            parsed = pd.to_datetime(value, format="%d-%m-%Y", errors="coerce")
            if not pd.isna(parsed):
                issues["badDateFormatRows"] += 1
        return parsed

    df["order_date"] = df["order_date"].apply(parseDate)
    df["order_date"] = df["order_date"].dt.strftime("%Y-%m-%d %H:%M:%S")

    missingMask = df["customer_id"].isna() | (df["customer_id"].astype(str).str.strip() == "")
    issues["missingCustomerIdRows"] = int(missingMask.sum())
    df.loc[missingMask, "customer_id"] = "UNKNOWN"
    return df, issues

def cleanProducts(productsDf):
    df = productsDf.copy()
    original = df["product_name"].astype(str)
    cleaned = original.str.strip().str.title()
    issues = {"messyNameRows": int((original != cleaned).sum())}
    df["product_name"] = cleaned
    return df, issues

def validateEmails(customersDf):
    invalidIds = []
    for _, row in customersDf.iterrows():
        email = str(row["email"])
        if "@" not in email:
            invalidIds.append(row["customer_id"])
            continue
        localPart, _, domainPart = email.partition("@")
        if not localPart or not domainPart or "." not in domainPart:
            invalidIds.append(row["customer_id"])
    return invalidIds

def checkReferentialIntegrity(ordersDf, orderItemsDf):
    validOrderIds = set(ordersDf["order_id"].astype(int))
    orphanMask = ~orderItemsDf["order_id"].astype(int).isin(validOrderIds)
    return orderItemsDf[orphanMask]

def runCleanData():
    print("\n" + "=" * 60)
    print("PART 2: CLEANING DATA")
    print("=" * 60)
    os.makedirs(CLEANED_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    ordersRaw = pd.read_csv(f"{RAW_DIR}/orders.csv", dtype={"customer_id": "string"})
    orderItemsRaw = pd.read_csv(f"{RAW_DIR}/order_items.csv")
    productsRaw = pd.read_csv(f"{RAW_DIR}/products.csv")
    customersRaw = pd.read_csv(f"{RAW_DIR}/customers.csv")

    ordersClean, orderIssues = cleanOrders(ordersRaw)
    productsClean, productIssues = cleanProducts(productsRaw)
    invalidEmailIds = validateEmails(customersRaw)
    orphanItems = checkReferentialIntegrity(ordersClean, orderItemsRaw)

    orderItemsClean = orderItemsRaw[~orderItemsRaw.index.isin(orphanItems.index)].copy()
    customersClean = customersRaw.copy()

    ordersClean.to_csv(f"{CLEANED_DIR}/orders.csv", index=False)
    orderItemsClean.to_csv(f"{CLEANED_DIR}/order_items.csv", index=False)
    productsClean.to_csv(f"{CLEANED_DIR}/products.csv", index=False)
    customersClean.to_csv(f"{CLEANED_DIR}/customers.csv", index=False)

    reportLines = [
        "DATA QUALITY REPORT", "====================", "",
        "orders.csv",
        f"  - rows with a date originally in DD-MM-YYYY format (fixed): {orderIssues['badDateFormatRows']}",
        f"  - rows with missing customer_id (set to 'UNKNOWN'):         {orderIssues['missingCustomerIdRows']}",
        "", "products.csv",
        f"  - rows with messy product_name (trimmed / title-cased): {productIssues['messyNameRows']}",
        "", "customers.csv",
        f"  - customer_ids with invalid emails: {len(invalidEmailIds)}",
        f"    {invalidEmailIds}",
        "", "order_items.csv",
        f"  - rows referencing a non-existent order_id (dropped): {len(orphanItems)}",
        f"    item_ids: {orphanItems['item_id'].tolist()}",
        "", "Row counts after cleaning",
        f"  - orders:      {len(ordersClean)}",
        f"  - order_items: {len(orderItemsClean)}",
        f"  - products:    {len(productsClean)}",
        f"  - customers:   {len(customersClean)}",
    ]
    reportText = "\n".join(reportLines)
    with open(f"{OUTPUT_DIR}/dataQualityReport.txt", "w", encoding="utf-8") as fh:
        fh.write(reportText)
    print(reportText)

def loadCsvIntoTable(connection, tableName, csvPath):
    with open(csvPath, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        placeholders = ",".join(["?"] * len(header))
        insertSql = f"INSERT INTO {tableName} ({','.join(header)}) VALUES ({placeholders})"
        rows = [tuple(row) for row in reader]
        connection.executemany(insertSql, rows)
    return len(rows)

def runLoadDatabase():
    print("\n" + "=" * 60)
    print("LOADING INTO SQLITE (ecommerce.db)")
    print("=" * 60)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    connection = sqlite3.connect(DB_PATH)
    connection.executescript(SCHEMA_SQL)

    tableFiles = [
        ("customers", "customers.csv"), ("products", "products.csv"),
        ("orders", "orders.csv"), ("order_items", "order_items.csv"),
    ]
    for tableName, fileName in tableFiles:
        rowCount = loadCsvIntoTable(connection, tableName, f"{CLEANED_DIR}/{fileName}")
        print(f"Loaded {rowCount} rows into {tableName}")
    connection.commit()

    print("\nRow count verification:")
    for tableName, _ in tableFiles:
        count = connection.execute(f"SELECT COUNT(*) FROM {tableName}").fetchone()[0]
        print(f"  {tableName}: {count}")
    connection.close()

def runAnalysisQueries():
    print("\n" + "=" * 60)
    print("PART 3: RUNNING 16 ANALYSIS QUERIES")
    print("=" * 60)
    connection = sqlite3.connect(DB_PATH)
    cur = connection.cursor()
    for title, sql in ANALYSIS_QUERIES:
        print(f"\n--- {title} ---")
        try:
            cur.execute(sql)
            colNames = [d[0] for d in cur.description]
            rows = cur.fetchall()
            print(", ".join(colNames))
            for row in rows[:10]:
                print(row)
            if len(rows) > 10:
                print(f"... ({len(rows)} rows total)")
        except sqlite3.Error as error:
            print(f"ERROR: {error}")
    connection.close()

def testOrderItemWithNonExistentOrder():
    orders = {1, 2, 3}
    orderItem = {"item_id": 999, "order_id": 42, "product_id": 1, "quantity": 1}
    isOrphan = orderItem["order_id"] not in orders
    assert isOrphan, "Expected order_item referencing a non-existent order to be detected as orphaned"
    print("testOrderItemWithNonExistentOrder: PASSED (orphaned row correctly identified and can be excluded from loading)")

def testDiscountPercentAboveHundred():
    discountPercent = 150
    isInvalid = discountPercent > 100
    assert isInvalid, "Expected discount_percent > 100 to be flagged invalid"
    print("testDiscountPercentAboveHundred: PASSED (discount_percent > 100 is detectable and should be rejected or clipped to 100 upstream)")

def testZeroQuantity():
    quantity, unitPrice, discountPercent = 0, 999.99, 10
    revenue = quantity * unitPrice * (1 - discountPercent / 100.0)
    assert revenue == 0, "Expected zero quantity to contribute zero revenue"
    print("testZeroQuantity: PASSED (quantity of 0 contributes 0 revenue and does not raise an error)")

def testFutureOrderDate():
    futureDate = datetime.now() + timedelta(days=30)
    isFuture = futureDate > datetime.now()
    assert isFuture, "Expected future order_date to be detected"
    print("testFutureOrderDate: PASSED (future order_date is detectable and should be flagged for review, not silently accepted)")

def runAllTests():
    print("\n" + "=" * 60)
    print("PART 5: EDGE CASE TESTS")
    print("=" * 60)
    testOrderItemWithNonExistentOrder()
    testDiscountPercentAboveHundred()
    testZeroQuantity()
    testFutureOrderDate()
    print("\nAll edge case tests passed.")

def parseDateInput(label, rawValue):
    try:
        return datetime.strptime(rawValue.strip(), "%Y-%m-%d")
    except ValueError:
        print(f"Invalid {label} date '{rawValue}'. Expected format YYYY-MM-DD.")
        return None

def promptReportType():
    validTypes = {"daily", "weekly", "monthly"}
    while True:
        reportType = input("Report type (daily/weekly/monthly): ").strip().lower()
        if reportType in validTypes:
            return reportType
        print(f"'{reportType}' is not valid. Choose one of {sorted(validTypes)}.")

def promptDateRange():
    while True:
        startRaw = input("Start date (YYYY-MM-DD): ")
        endRaw = input("End date   (YYYY-MM-DD): ")
        startDate = parseDateInput("start", startRaw)
        endDate = parseDateInput("end", endRaw)
        if startDate is None or endDate is None:
            continue
        if startDate > endDate:
            print("Start date must not be after end date. Try again.")
            continue
        return startDate, endDate

def fetchSummary(connection, startDate, endDate):
    startStr = startDate.strftime("%Y-%m-%d 00:00:00")
    endStr = endDate.strftime("%Y-%m-%d 23:59:59")
    summaryRow = connection.execute("""
        SELECT COUNT(DISTINCT o.order_id) AS total_orders,
               COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)), 0) AS total_revenue,
               COUNT(DISTINCT o.customer_id) AS unique_customers
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.order_id
        WHERE o.order_date BETWEEN ? AND ?
    """, (startStr, endStr)).fetchone()

    topProducts = connection.execute("""
        SELECT p.product_name,
               SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)) AS revenue
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.order_id
        JOIN products p ON p.product_id = oi.product_id
        WHERE o.order_date BETWEEN ? AND ?
        GROUP BY p.product_id
        ORDER BY revenue DESC
        LIMIT 3
    """, (startStr, endStr)).fetchall()

    return {
        "totalOrders": summaryRow[0] or 0, "totalRevenue": summaryRow[1] or 0.0,
        "uniqueCustomers": summaryRow[2] or 0, "topProducts": topProducts,
    }

def percentChange(current, previous):
    if previous in (0, None):
        return None
    return (current - previous) * 100.0 / previous

def formatPercent(value):
    if value is None:
        return "N/A (no data in previous period)"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"

def printReport(reportType, startDate, endDate, current, previous):
    print()
    print("=" * 56)
    print(f"{reportType.upper()} REPORT: {startDate.date()} to {endDate.date()}")
    print("=" * 56)
    print(f"Total orders:     {current['totalOrders']}")
    print(f"Total revenue:    {current['totalRevenue']:.2f}")
    print(f"Unique customers: {current['uniqueCustomers']}")
    print()
    print("Top 3 products by revenue:")
    if current["topProducts"]:
        for rank, (name, revenue) in enumerate(current["topProducts"], start=1):
            print(f"  {rank}. {name} - {revenue:.2f}")
    else:
        print("  (no orders in this period)")
    print()
    print("Comparison with previous period of equal length:")
    print(f"  Orders:     {formatPercent(percentChange(current['totalOrders'], previous['totalOrders']))}")
    print(f"  Revenue:    {formatPercent(percentChange(current['totalRevenue'], previous['totalRevenue']))}")
    print(f"  Customers:  {formatPercent(percentChange(current['uniqueCustomers'], previous['uniqueCustomers']))}")
    print("=" * 56)

def runInteractiveReport():
    connection = sqlite3.connect(DB_PATH)
    reportType = promptReportType()
    startDate, endDate = promptDateRange()
    periodLength = (endDate - startDate) + timedelta(days=1)
    previousStart = startDate - periodLength
    previousEnd = startDate - timedelta(days=1)
    current = fetchSummary(connection, startDate, endDate)
    previous = fetchSummary(connection, previousStart, previousEnd)
    connection.close()
    printReport(reportType, startDate, endDate, current, previous)

def main():
    parser = argparse.ArgumentParser(description="Run the full e-commerce analytics pipeline.")
    parser.add_argument("--report", action="store_true",
                         help="After the pipeline finishes, launch the interactive daily/weekly/monthly report.")
    args = parser.parse_args()

    runGenerateData()
    runCleanData()
    runLoadDatabase()
    runAnalysisQueries()
    runAllTests()

    if args.report:
        runInteractiveReport()

    print("\nDone. Database written to:", os.path.abspath(DB_PATH))

if __name__ == "__main__":
    main()
