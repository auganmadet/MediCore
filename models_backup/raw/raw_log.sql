{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'audit']
    )
}}

select * from {{ source('mysql_raw', 'RAW_LOG') }}

