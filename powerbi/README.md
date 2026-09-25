# Power BI dashboard — NSW fuel prices

Built on the Snowflake `MARTS` star schema (see [`../warehouse/README.md`](../warehouse/README.md)).

> Screenshots go in `powerbi/screenshots/` and the report file is `powerbi/nsw_fuel_prices.pbix`.

## 1. Install

- On a Windows on Arm laptop, run **Windows Update** first — Power BI Desktop is supported on Arm
  (it runs under x64 emulation) once the October 2025 Windows update or later is installed.
- Install **Power BI Desktop** (free) from the Microsoft Store.

## 2. Connect to Snowflake

1. **Get data → Database → Snowflake → Connect**
2. **Server:** your account URL without `https://` — in Snowsight click your name (bottom-left) →
   *Connect a tool to Snowflake* and copy it. Looks like `xxxxxxx.snowflakecomputing.com`.
3. **Warehouse:** `FUEL_WH`. Under *Advanced options* set **Role** `BI_READER` and **Database** `FUEL_DB`.
4. **Data connectivity mode:** Import.
5. Credentials, *Snowflake* tab: **User name** = your Snowflake username,
   **Password** = the token from `06_powerbi_access.sql` (not your normal password).
6. In the Navigator open `FUEL_DB → MARTS` and tick:
   `DIM_DATE`, `DIM_FUEL_TYPE`, `DIM_STATION`, `FCT_CURRENT_PRICE`, `DQ_SUMMARY`
   (+ `FCT_DAILY_PRICE`, `FCT_PRICE_CHANGE` if you loaded price history) → **Load**.

**If the connection fights you for more than 30 minutes:** in Snowsight run `SELECT * FROM FUEL_DB.MARTS.<table>`,
download each result as CSV, and use *Get data → Text/CSV*. Build the dashboard, and note in the README that
a production setup would use a live connection (SSO or key-pair auth).

## 3. Model view

Power BI may guess relationships — delete any that don't match this list. All are **many-to-one, single direction**:

| From (many) | To (one) |
|---|---|
| `FCT_CURRENT_PRICE[STATION_ID]` | `DIM_STATION[STATION_ID]` |
| `FCT_CURRENT_PRICE[FUEL_CODE]` | `DIM_FUEL_TYPE[FUEL_CODE]` |
| `FCT_CURRENT_PRICE[PRICE_DATE]` | `DIM_DATE[DATE_DAY]` |
| `FCT_DAILY_PRICE[…same three…]` | same dimensions |
| `FCT_PRICE_CHANGE[…same three…]` | same dimensions |

Then:
- `DIM_DATE` → *Table tools → Mark as date table* → `DATE_DAY`.
- `DIM_STATION[LATITUDE]` / `[LONGITUDE]` → *Column tools → Data category* → Latitude / Longitude.
- Sort `DIM_DATE[DAY_NAME]` by `DAY_OF_WEEK_NUM`, and `DIM_FUEL_TYPE[FUEL_NAME]` by `SORT_ORDER`.

## 4. Measures (DAX)

Create an empty table called `_Measures` (*Home → Enter data → Load*) and add:

```DAX
Avg Price (c/L) =
CALCULATE (
    AVERAGE ( FCT_CURRENT_PRICE[PRICE_CENTS] ),
    DIM_FUEL_TYPE[IS_LIQUID_FUEL] = TRUE (),
    FCT_CURRENT_PRICE[IS_STALE] = FALSE (),
    FCT_CURRENT_PRICE[IS_SUSPECT_PLACEHOLDER] = FALSE ()
)

Cheapest (c/L) =
CALCULATE (
    MIN ( FCT_CURRENT_PRICE[PRICE_CENTS] ),
    DIM_FUEL_TYPE[IS_LIQUID_FUEL] = TRUE (),
    FCT_CURRENT_PRICE[IS_STALE] = FALSE (),
    FCT_CURRENT_PRICE[IS_SUSPECT_PLACEHOLDER] = FALSE ()
)

Stations = DISTINCTCOUNT ( FCT_CURRENT_PRICE[STATION_ID] )

vs NSW Avg (c/L) =
[Avg Price (c/L)] - CALCULATE ( [Avg Price (c/L)], REMOVEFILTERS ( DIM_STATION ) )

Stale Price % =
DIVIDE (
    CALCULATE ( COUNTROWS ( FCT_CURRENT_PRICE ), FCT_CURRENT_PRICE[IS_STALE] = TRUE () ),
    COUNTROWS ( FCT_CURRENT_PRICE )
)

Rows Passed % =
DIVIDE (
    CALCULATE ( SUM ( DQ_SUMMARY[ROW_COUNT] ), DQ_SUMMARY[OUTCOME] = "Passed" ),
    SUM ( DQ_SUMMARY[ROW_COUNT] )
)

-- only if price history is loaded
Avg Daily Price (c/L) =
CALCULATE ( AVERAGE ( FCT_DAILY_PRICE[PRICE_CENTS] ), DIM_FUEL_TYPE[IS_LIQUID_FUEL] = TRUE () )

Price Changes = COUNTROWS ( FCT_PRICE_CHANGE )
```

## 5. Pages

**Page 1 — Current prices**
- Slicers: `DIM_FUEL_TYPE[FUEL_NAME]` (single select, Unleaded 91), `DIM_STATION[BRAND]`
- Cards: Avg Price (c/L), Cheapest (c/L), Stations
- Map (Azure Maps): Latitude / Longitude from `DIM_STATION`, bubble colour or size = Avg Price, tooltip = station name.
  If map visuals are greyed out, enable them under *File → Options and settings → Options → Security*.
- Bar chart: Avg Price by `DIM_STATION[BRAND]`, visual-level filter *Stations ≥ 30* so tiny brands don't dominate
- Table: station name, suburb, brand, Avg Price — sorted cheapest first, Top 10

**Page 2 — Trends** (needs price history)
- Line chart: `DIM_DATE[DATE_DAY]` × Avg Daily Price, legend = `FUEL_NAME`
- Column chart: Price Changes by `DIM_DATE[DAY_NAME]`

**Page 3 — Data quality**
- Table from `DQ_SUMMARY`: source, outcome, row_count
- Cards: Rows Passed %, Stale Price %
- Bar chart: Stale Price % by `FUEL_NAME`

## 6. Save and publish to GitHub

- *File → Save as* → `powerbi/nsw_fuel_prices.pbix` inside this repo.
- Screenshot each page (Win + Shift + S) into `powerbi/screenshots/` and add them to this README —
  most reviewers won't open a `.pbix`, but they will look at a picture.
