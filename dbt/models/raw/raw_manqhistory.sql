{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'manques']
    )
}}

select * from {{ source('mysql_raw', 'RAW_MANQHISTORY') }}
