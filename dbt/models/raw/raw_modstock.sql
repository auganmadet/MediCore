{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'stock_mouvements']
    )
}}

select * from {{ source('mysql_raw', 'RAW_MODSTOCK') }}
