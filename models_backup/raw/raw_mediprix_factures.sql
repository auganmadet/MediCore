{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'factures_mediprix']
    )
}}

select * from {{ source('mysql_raw', 'RAW_MEDIPRIX_FACTURES') }}

