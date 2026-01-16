{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'stock_history']
    )
}}

select * from {{ source('mysql_raw', 'RAW_STOCKHISTORY') }}
