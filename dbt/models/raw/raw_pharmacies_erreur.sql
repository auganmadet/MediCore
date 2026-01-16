{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'erreurs']
    )
}}

select * from {{ source('mysql_raw', 'RAW_PHARMACIES_ERREUR') }}
