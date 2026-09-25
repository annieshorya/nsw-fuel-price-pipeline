-- Typed, cleaned, de-duplicated API snapshot (one row per station x fuel type).
-- Bad rows are LABELLED in dq_issue, not dropped; marts keep dq_issue is null.
-- Port of warehouse/snowflake/03_staging.sql (STG_API_PRICES) to Postgres.
with source as (

    select * from {{ source('raw', 'api_price_snapshot') }}

),

typed as (

    select
        trim(stationid)                                                           as station_id,
        trim(code)                                                                as station_code,
        -- strip "(Members Only)" and collapse repeated spaces
        trim(regexp_replace(regexp_replace(name, '\(Members Only\)', '', 'gi'), '\s+', ' ', 'g')) as station_name,
        upper(name) like '%(MEMBERS ONLY)%'                                       as is_members_only,
        trim(brand)                                                               as brand,
        trim(address)                                                             as address,
        -- "208-212 Pacific Hwy North, Coffs Harbour NSW 2450" -> Coffs Harbour / NSW / 2450
        initcap(trim((regexp_match(address, ',\s*([^,]*)\s+(?:NSW|ACT)\s+[0-9]{4}\s*$'))[1])) as suburb,
        (regexp_match(address, '(NSW|ACT)\s+[0-9]{4}\s*$'))[1]                    as state,
        (regexp_match(address, '([0-9]{4})\s*$'))[1]                              as postcode,
        {{ safe_double('latitude') }}                                             as latitude,
        {{ safe_double('longitude') }}                                            as longitude,
        {{ safe_boolean('isadblueavailable') }}                                   as has_adblue,
        upper(trim(fueltype))                                                     as fuel_code,
        {{ safe_numeric('price') }}                                               as price_cents,
        {{ safe_timestamp_dmy('lastupdated') }}                                   as last_updated_at,
        _source_file                                                              as source_file,
        _loaded_at                                                                as loaded_at
    from source

),

deduped as (

    -- several snapshots can be loaded: keep the newest price per station x fuel
    select *
    from (
        select
            *,
            row_number() over (
                partition by station_id, fuel_code
                order by last_updated_at desc nulls last, loaded_at desc
            ) as rn
        from typed
    ) ranked
    where rn = 1

)

select
    station_id,
    station_code,
    station_name,
    is_members_only,
    brand,
    address,
    suburb,
    state,
    postcode,
    latitude,
    longitude,
    has_adblue,
    fuel_code,
    price_cents,
    last_updated_at,
    source_file,
    loaded_at,
    -- same price on 3+ fuel types at the same second looks like a placeholder, not a real price
    count(*) over (partition by station_id, last_updated_at, price_cents) >= 3 as is_suspect_placeholder,
    case
        when station_id is null                                   then 'missing station id'
        when latitude is null or longitude is null                then 'missing or invalid coordinates'
        when not (latitude between -38 and -28
              and longitude between 140 and 154)                  then 'outside NSW/ACT bounding box'
        when fuel_code is null                                    then 'missing fuel type'
        when price_cents is null                                  then 'unparseable price'
        when last_updated_at is null                              then 'unparseable timestamp'
        when fuel_code <> 'EV' and price_cents not between 50 and 500 then 'price outside 50-500 c/L'
    end                                                           as dq_issue
from deduped
