{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'fournisseurs']
    )
}}

select * from {{ source('mysql_raw', 'RAW_FOURNISSEURS') }}
