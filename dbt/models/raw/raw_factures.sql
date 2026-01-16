{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'factures', 'high_volume']
    )
}}

select * from {{ source('mysql_raw', 'RAW_FACTURES') }}
