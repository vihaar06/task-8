import sqlite3
import sys
from datetime import datetime, timedelta
DB_PATH = "ecommerce.db"
VALID_REPORT_TYPES = {"daily", "weekly", "monthly"}
def parseDate(label, rawValue):
    try:
        return datetime.strptime(rawValue.strip(), "%Y-%m-%d")
    except ValueError:
        print(f"Invalid {label} date '{rawValue}'. Expected format YYYY-MM-DD.")
        return None


def promptReportType():
    while True:
        reportType = input("Report type (daily/weekly/monthly): ").strip().lower()
        if reportType in VALID_REPORT_TYPES:
            return reportType
        print(f"'{reportType}' is not valid. Choose one of {sorted(VALID_REPORT_TYPES)}.")


def promptDateRange():
    while True:
        startRaw = input("Start date (YYYY-MM-DD): ")
        endRaw = input("End date   (YYYY-MM-DD): ")
        startDate = parseDate("start", startRaw)
        endDate = parseDate("end", endRaw)
        if startDate is None or endDate is None:
            continue
        if startDate > endDate:
            print("Start date must not be after end date. Try again.")
            continue
        return startDate, endDate


def fetchSummary(connection, startDate, endDate):
    startStr = startDate.strftime("%Y-%m-%d 00:00:00")
    endStr = endDate.strftime("%Y-%m-%d 23:59:59")

    summaryRow = connection.execute(
        """
        SELECT
            COUNT(DISTINCT o.order_id) AS total_orders,
            COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)), 0) AS total_revenue,
            COUNT(DISTINCT o.customer_id) AS unique_customers
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.order_id
        WHERE o.order_date BETWEEN ? AND ?
        """,
        (startStr, endStr),
    ).fetchone()

    topProducts = connection.execute(
        """
        SELECT
            p.product_name,
            SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100.0)) AS revenue
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.order_id
        JOIN products p ON p.product_id = oi.product_id
        WHERE o.order_date BETWEEN ? AND ?
        GROUP BY p.product_id
        ORDER BY revenue DESC
        LIMIT 3
        """,
        (startStr, endStr),
    ).fetchall()

    return {
        "totalOrders": summaryRow[0] or 0,
        "totalRevenue": summaryRow[1] or 0.0,
        "uniqueCustomers": summaryRow[2] or 0,
        "topProducts": topProducts,
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


def main():
    try:
        connection = sqlite3.connect(DB_PATH)
    except sqlite3.Error as error:
        print(f"Could not connect to database '{DB_PATH}': {error}")
        sys.exit(1)

    reportType = promptReportType()
    startDate, endDate = promptDateRange()

    periodLength = (endDate - startDate) + timedelta(days=1)
    previousStart = startDate - periodLength
    previousEnd = startDate - timedelta(days=1)

    try:
        current = fetchSummary(connection, startDate, endDate)
        previous = fetchSummary(connection, previousStart, previousEnd)
    except sqlite3.Error as error:
        print(f"Query failed: {error}")
        sys.exit(1)
    finally:
        connection.close()

    printReport(reportType, startDate, endDate, current, previous)


if __name__ == "__main__":
    main()
