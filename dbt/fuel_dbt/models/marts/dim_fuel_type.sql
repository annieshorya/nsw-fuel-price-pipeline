-- Readable fuel names + a flag that keeps EV charging out of c/L averages.
-- Any code seen in the data but missing from the seed still gets a row.
with known as (

    select * from {{ ref('fuel_types') }}

),

seen as (

    select distinct fuel_code
    from {{ ref('stg_api_prices') }}
    where fuel_code is not null

)

select
    coalesce(k.fuel_code, s.fuel_code)                     as fuel_code,
    coalesce(k.fuel_name, s.fuel_code || ' (unmapped)')    as fuel_name,
    coalesce(k.fuel_group, 'Other')                        as fuel_group,
    coalesce(k.is_liquid_fuel, true)                       as is_liquid_fuel,
    coalesce(k.sort_order, 99)                             as sort_order
from known k
full outer join seen s on k.fuel_code = s.fuel_code
