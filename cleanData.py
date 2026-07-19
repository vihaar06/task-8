import os
import pandas as pd

RAW_DIR = "data/raw"
CLEANED_DIR = "data/cleaned"
OUTPUT_DIR = "output"


def cleanOrders(ordersDf):
    """
    - Normalizes order_date to YYYY-MM-DD HH:MM:SS, handling DD-MM-YYYY inputs.
    - Fills missing/blank customer_id with the sentinel 'UNKNOWN' so it survives
      as a real (non-null) value while still being obviously flagged as missing.
    Returns (cleanedDf, issuesDict).
    """
    df = ordersDf.copy()
    issues = {"badDateFormatRows": 0, "missingCustomerIdRows": 0}

    def parseDate(value):
        value = str(value).strip()
        # Try the canonical format first
        parsed = pd.to_datetime(value, format="%Y-%m-%d %H:%M:%S", errors="coerce")
        if pd.isna(parsed):
            # Fall back to the known "wrong" format: DD-MM-YYYY
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
    """
    Trims whitespace and applies title case to product_name.
    Returns (cleanedDf, issuesDict).
    """
    df = productsDf.copy()
    original = df["product_name"].astype(str)
    cleaned = original.str.strip().str.title()
    issues = {"messyNameRows": int((original != cleaned).sum())}
    df["product_name"] = cleaned
    return df, issues


def validateEmails(customersDf):
    """
    Returns the list of customer_ids whose email is invalid
    (missing '@' or missing a domain after '@').
    """
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
    """
    Returns the subset of order_items rows whose order_id does not
    exist in the orders table.
    """
    validOrderIds = set(ordersDf["order_id"].astype(int))
    orphanMask = ~orderItemsDf["order_id"].astype(int).isin(validOrderIds)
    return orderItemsDf[orphanMask]


def main():
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

    # order_items: drop rows that reference non-existent orders (can't be fixed, only removed)
    orderItemsClean = orderItemsRaw[~orderItemsRaw.index.isin(orphanItems.index)].copy()

    # customers: leave emails as-is but this is where a downstream consumer would
    # act on validateEmails()'s output (e.g. flag the account, block marketing email, etc.)
    customersClean = customersRaw.copy()

    ordersClean.to_csv(f"{CLEANED_DIR}/orders.csv", index=False)
    orderItemsClean.to_csv(f"{CLEANED_DIR}/order_items.csv", index=False)
    productsClean.to_csv(f"{CLEANED_DIR}/products.csv", index=False)
    customersClean.to_csv(f"{CLEANED_DIR}/customers.csv", index=False)

    reportLines = [
        "DATA QUALITY REPORT",
        "====================",
        "",
        "orders.csv",
        f"  - rows with a date originally in DD-MM-YYYY format (fixed): {orderIssues['badDateFormatRows']}",
        f"  - rows with missing customer_id (set to 'UNKNOWN'):         {orderIssues['missingCustomerIdRows']}",
        "",
        "products.csv",
        f"  - rows with messy product_name (trimmed / title-cased): {productIssues['messyNameRows']}",
        "",
        "customers.csv",
        f"  - customer_ids with invalid emails: {len(invalidEmailIds)}",
        f"    {invalidEmailIds}",
        "",
        "order_items.csv",
        f"  - rows referencing a non-existent order_id (dropped): {len(orphanItems)}",
        f"    item_ids: {orphanItems['item_id'].tolist()}",
        "",
        "Row counts after cleaning",
        f"  - orders:      {len(ordersClean)}",
        f"  - order_items: {len(orderItemsClean)}",
        f"  - products:    {len(productsClean)}",
        f"  - customers:   {len(customersClean)}",
    ]
    reportText = "\n".join(reportLines)
    with open(f"{OUTPUT_DIR}/dataQualityReport.txt", "w", encoding="utf-8") as fh:
        fh.write(reportText)

    print(reportText)


if __name__ == "__main__":
    main()
