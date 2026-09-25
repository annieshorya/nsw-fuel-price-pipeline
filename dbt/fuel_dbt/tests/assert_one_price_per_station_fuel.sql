-- Grain check: fct_current_price must have exactly one row per station x fuel type.
select station_id, fuel_code, count(*) as n
from {{ ref('fct_current_price') }}
group by 1, 2
having count(*) > 1
