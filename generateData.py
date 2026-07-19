import csv
import random
from datetime import datetime, timedelta

random.seed(42)

NUM_CUSTOMERS = 600
NUM_PRODUCTS = 520
NUM_ORDERS = 1500
AVG_ITEMS_PER_ORDER = 2.2   # -> comfortably produces 500+ order_items rows

RAW_DIR = "data/raw"

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


def randomDateWithinYears(startYearsAgo=2, endYearsAgo=0):
    now = datetime.now()
    start = now - timedelta(days=365 * startYearsAgo)
    end = now - timedelta(days=365 * endYearsAgo)
    delta = end - start
    randomSeconds = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=randomSeconds)


def messUpProductName(name):
    """Randomly add extra spaces and/or mixed case to a product name."""
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
            "customer_id": customerId,
            "customer_name": customerName,
            "email": email,
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
            "product_id": productId,
            "product_name": productName,
            "category": category,
            "subcategory": subcategory,
            "cost_price": costPrice,
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
        status = random.choices(
            ORDER_STATUSES,
            weights=[0.15, 0.20, 0.45, 0.10, 0.10],
        )[0]
        regionCode = random.choice(["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"])
        rows.append({
            "order_id": orderId,
            "customer_id": customerId,
            "order_date": orderDateStr,
            "status": status,
            "region_code": regionCode,
            "_sortDate": orderDate,  # kept only for internal ordering, stripped before writing
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
                quantity = -abs(quantity)  # negative quantity = return
            unitPrice = round(random.uniform(5, 6000), 2)
            discountPercent = round(random.uniform(0, 100), 1) if random.random() < 0.4 else 0
            rows.append({
                "item_id": itemId,
                "order_id": orderId,
                "product_id": productId,
                "quantity": quantity,
                "unit_price": unitPrice,
                "discount_percent": discountPercent,
            })
            itemId += 1
    return rows


def writeCsv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})


def main():
    import os
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

    # Deliberately inject a handful of order_items rows that reference
    # non-existent orders, so check_referential_integrity() has something to find.
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


if __name__ == "__main__":
    main()
