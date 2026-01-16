{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'ordonnances']
    )
}}

select * from {{ source('mysql_raw', 'RAW_ORDERS') }}
