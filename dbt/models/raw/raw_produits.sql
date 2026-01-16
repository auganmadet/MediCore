{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'dim_produits']
    )
}}

select * from {{ source('mysql_raw', 'RAW_PRODUITS') }}
