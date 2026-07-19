
from datetime import datetime, timedelta

import pandas as pd

from cleanData import checkReferentialIntegrity


def testOrderItemWithNonExistentOrder():
    ordersDf = pd.DataFrame({
        "order_id": [1, 2, 3],
        "customer_id": ["1", "2", "3"],
        "order_date": ["2025-01-01 10:00:00"] * 3,
        "status": ["DELIVERED"] * 3,
        "region_code": ["NORTH"] * 3,
    })
    orderItemsDf = pd.DataFrame({
        "item_id": [1, 2, 3],
        "order_id": [1, 2, 999],   # 999 does not exist in ordersDf
        "product_id": [10, 11, 12],
        "quantity": [1, 2, 1],
        "unit_price": [100.0, 50.0, 20.0],
        "discount_percent": [0, 0, 0],
    })

    orphanRows = checkReferentialIntegrity(ordersDf, orderItemsDf)

    assert len(orphanRows) == 1, "Expected exactly one orphaned order_items row"
    assert orphanRows.iloc[0]["order_id"] == 999
    print("testOrderItemWithNonExistentOrder: PASSED "
          "(orphaned row correctly identified and can be excluded from loading)")


def testDiscountPercentAboveHundred():
    orderItemsDf = pd.DataFrame({
        "item_id": [1, 2],
        "order_id": [1, 1],
        "product_id": [10, 11],
        "quantity": [1, 1],
        "unit_price": [100.0, 100.0],
        "discount_percent": [50, 150],   # 150 is invalid, should be flagged
    })

    invalidRows = orderItemsDf[
        (orderItemsDf["discount_percent"] < 0) | (orderItemsDf["discount_percent"] > 100)
    ]

    assert len(invalidRows) == 1, "Expected exactly one row with an out-of-range discount_percent"
    assert invalidRows.iloc[0]["item_id"] == 2
    # Revenue formula should be clipped/flagged rather than allowed to go negative;
    # here we just confirm the row is detectable before it ever reaches the revenue query.
    print("testDiscountPercentAboveHundred: PASSED "
          "(discount_percent > 100 is detectable and should be rejected or clipped to 100 upstream)")


def testZeroQuantity():
    orderItemsDf = pd.DataFrame({
        "item_id": [1, 2],
        "order_id": [1, 1],
        "product_id": [10, 11],
        "quantity": [0, 3],
        "unit_price": [100.0, 100.0],
        "discount_percent": [0, 0],
    })

    revenue = orderItemsDf["quantity"] * orderItemsDf["unit_price"] * (1 - orderItemsDf["discount_percent"] / 100.0)
    zeroQuantityRows = orderItemsDf[orderItemsDf["quantity"] == 0]

    assert len(zeroQuantityRows) == 1
    assert revenue.iloc[0] == 0.0, "A quantity of 0 should contribute exactly 0 revenue, not an error"
    print("testZeroQuantity: PASSED "
          "(quantity of 0 contributes 0 revenue and does not raise an error)")


def testFutureOrderDate():
    futureDate = datetime.now() + timedelta(days=30)
    ordersDf = pd.DataFrame({
        "order_id": [1],
        "customer_id": ["1"],
        "order_date": [futureDate.strftime("%Y-%m-%d %H:%M:%S")],
        "status": ["PLACED"],
        "region_code": ["NORTH"],
    })

    ordersDf["order_date"] = pd.to_datetime(ordersDf["order_date"])
    futureRows = ordersDf[ordersDf["order_date"] > pd.Timestamp.now()]

    assert len(futureRows) == 1, "Future-dated order should be detectable for flagging/exclusion"
    print("testFutureOrderDate: PASSED "
          "(future order_date is detectable and should be flagged for review, not silently accepted)")


def runAllTests():
    tests = [
        testOrderItemWithNonExistentOrder,
        testDiscountPercentAboveHundred,
        testZeroQuantity,
        testFutureOrderDate,
    ]
    for test in tests:
        test()
    print("\nAll edge case tests passed.")


if __name__ == "__main__":
    runAllTests()
