-- Liquid fuel prices in the marts must be between 50 and 500 cents per litre.
select f.*
from {{ ref('fct_current_price') }} f
join {{ ref('dim_fuel_type') }} d using (fuel_code)
where d.is_liquid_fuel and f.price_cents not between 50 and 500
