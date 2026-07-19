import csv
import sqlite3

DB_PATH = "ecommerce.db"
SCHEMA_PATH = "sql/schema.sql"
CLEANED_DIR = "data/cleaned"

TABLE_FILES = [
    ("customers", "customers.csv"),
    ("products", "products.csv"),
    ("orders", "orders.csv"),
    ("order_items", "order_items.csv"),
]


def loadCsvIntoTable(connection, tableName, csvPath):
    with open(csvPath, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        placeholders = ",".join(["?"] * len(header))
        insertSql = f"INSERT INTO {tableName} ({','.join(header)}) VALUES ({placeholders})"
        rows = [tuple(row) for row in reader]
        connection.executemany(insertSql, rows)
    return len(rows)


def main():
    connection = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
        connection.executescript(fh.read())

    for tableName, fileName in TABLE_FILES:
        rowCount = loadCsvIntoTable(connection, tableName, f"{CLEANED_DIR}/{fileName}")
        print(f"Loaded {rowCount} rows into {tableName}")

    connection.commit()

    print("\nRow count verification:")
    for tableName, _ in TABLE_FILES:
        count = connection.execute(f"SELECT COUNT(*) FROM {tableName}").fetchone()[0]
        print(f"  {tableName}: {count}")

    connection.close()


if __name__ == "__main__":
    main()
