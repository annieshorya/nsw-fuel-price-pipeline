-- Latest price per station x fuel type (grain: station_id, fuel_code).
with base as (

    select
        *,
        max(last_updated_at) over () as snapshot_as_at   -- roughly when the API was pulled
    from {{ ref('stg_api_prices') }}
    where dq_issue is null

)

select
    station_id,
    fuel_code,
    last_updated_at::date                                           as price_date,
    last_updated_at,
    price_cents,
    (snapshot_as_at::date - last_updated_at::date)                  as days_since_update,
    (snapshot_as_at::date - last_updated_at::date) > 30             as is_stale,
    is_suspect_placeholder,
    snapshot_as_at,
    source_file
from base
