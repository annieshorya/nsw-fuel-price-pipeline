-- Every staged row is either in the fact table or counted as excluded in dq_summary.
with staged as (select count(*) as n from {{ ref('stg_api_prices') }}),
     accounted as (select sum(row_count) as n from {{ ref('dq_summary') }})
select * from staged, accounted where staged.n <> accounted.n
