# E-Commerce Order Analytics — Single-File Edition

`ecommerceAnalytics_all.py` is a single, self-contained, executable Python
file that runs the entire analytics pipeline in one shot — no `sql/`
folder, no separate scripts, no other files required.

It merges everything from the original multi-file project:

- Part 1 — generate messy raw e-commerce data
- Part 2 — clean it
- Part 3 — load into SQLite and run 16 analytical SQL queries
- Part 4 — interactive daily/weekly/monthly report (optional)
- Part 5 — edge case tests

## Requirements

```bash
pip install pandas --break-system-packages
```

Everything else (`csv`, `sqlite3`, `random`, `datetime`, `argparse`) is
Python standard library.

## Usage

```bash
# Run the full pipeline: generate -> clean -> load -> analyze -> test
python3 ecommerceAnalytics_all.py

# Same, then also launch the interactive report prompt at the end
python3 ecommerceAnalytics_all.py --report
```

Running it creates, in the current directory:

```
data/raw/*.csv        generated, messy CSVs
data/cleaned/*.csv     cleaned CSVs
output/dataQualityReport.txt
ecommerce.db           SQLite database
```

## What it prints

1. **Data generation** — row counts for customers, products, orders,
   order_items (600 / 520 / 1500 / ~2700).
2. **Data quality report** — counts of fixed bad dates, filled missing
   `customer_id`s, cleaned product names, invalid emails, and dropped
   orphaned `order_items` rows.
3. **Database load** — rows loaded and verified per table.
4. **All 16 analysis queries** — revenue per category, top customers,
   monthly order counts, delivery/return diagnostics, running totals,
   `DENSE_RANK` ranking, `LAG` gap analysis, multi-level CTEs, `NTILE`
   quartiles, YoY comparison, `FIRST_VALUE`/`LAST_VALUE` category-shift
   detection, cumulative revenue distribution, cohort retention, and a
   self-join "frequently bought together" query. Each result set prints
   its column names and up to 10 sample rows.
5. **Edge case tests** — 4 assertions (orphaned order_item, discount >
   100%, zero quantity, future order date), each printed as PASSED.
6. With `--report`: prompts for a report type (`daily`/`weekly`/`monthly`)
   and a date range, then prints total orders/revenue/unique customers,
   top 3 products by revenue, and a % comparison against the previous
   period of equal length.

## Notes

- Data is randomly generated but seeded (`random.seed(42)`), so repeated
  runs produce the same structure and roughly the same issue counts
  each time (dates/randomized values will still vary run-to-run since
  the RNG state also depends on system clock–based order dates).
- Re-running the script overwrites `ecommerce.db` and the `data/` /
  `output/` folders from scratch each time.
- This single-file version has no comments or docstrings (per request)
  — for the fully commented/documented multi-file version, see the
  original `ecommerceAnalytics` project files.
