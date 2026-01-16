{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'prix_journalier']
    )
}}

select * from {{ source('mysql_raw', 'RAW_DAYBYDAY') }}
