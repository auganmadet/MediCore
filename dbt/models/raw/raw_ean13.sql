{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'ean13']
    )
}}

select * from {{ source('mysql_raw', 'RAW_EAN13') }}
