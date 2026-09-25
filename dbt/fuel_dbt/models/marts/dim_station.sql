-- One row per station, keyed on the API station id
-- (name + postcode is NOT unique: several "7-Eleven Blacktown" stations share 2148).
select
    station_id,
    station_code,
    station_name,
    brand,
    address,
    suburb,
    state,
    postcode,
    latitude,
    longitude,
    has_adblue,
    is_members_only
from (
    select
        *,
        row_number() over (partition by station_id order by last_updated_at desc) as rn
    from {{ ref('stg_api_prices') }}
    where dq_issue is null
) latest
where rn = 1
