{# Postgres has no TRY_CAST: return NULL instead of failing on a malformed value. #}
{% macro safe_double(col) -%}
    case when trim({{ col }}) ~ '^-?[0-9]+(\.[0-9]+)?$' then trim({{ col }})::double precision end
{%- endmacro %}

{% macro safe_numeric(col, precision=7, scale=2) -%}
    case when trim({{ col }}) ~ '^-?[0-9]+(\.[0-9]+)?$' then trim({{ col }})::numeric({{ precision }}, {{ scale }}) end
{%- endmacro %}

{# FuelCheck timestamps look like 27/05/2025 06:00:50 #}
{% macro safe_timestamp_dmy(col) -%}
    case when trim({{ col }}) ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}$'
         then to_timestamp(trim({{ col }}), 'DD/MM/YYYY HH24:MI:SS')::timestamp end
{%- endmacro %}

{% macro safe_boolean(col) -%}
    case lower(trim({{ col }})) when 'true' then true when 'false' then false end
{%- endmacro %}
