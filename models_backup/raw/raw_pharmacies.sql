{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'ref_pharmacies']
    )
}}

select * from {{ source('mysql_raw', 'RAW_PHARMACIES') }}

