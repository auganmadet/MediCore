{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'dim_pharmacie']
    )
}}

select * from {{ source('mysql_raw', 'RAW_PHARMACIE') }}
