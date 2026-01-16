{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'ca_journalier']
    )
}}

select * from {{ source('mysql_raw', 'RAW_HISTORY') }}
