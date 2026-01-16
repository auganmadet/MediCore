{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'lppr']
    )
}}

select * from {{ source('mysql_raw', 'RAW_LPPR') }}
