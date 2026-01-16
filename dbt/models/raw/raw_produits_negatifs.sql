{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'produits_negatifs']
    )
}}

select * from {{ source('mysql_raw', 'RAW_PRODUITS_NEGATIFS') }}
