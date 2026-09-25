-- Rows that passed vs. were excluded from the marts, by reason.
select
    'API snapshot'                  as source,
    coalesce(dq_issue, 'Passed')    as outcome,
    count(*)                        as row_count
from {{ ref('stg_api_prices') }}
group by 1, 2
