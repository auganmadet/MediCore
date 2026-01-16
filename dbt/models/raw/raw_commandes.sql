{{
    config(
        materialized='view',
        schema='RAW',
        tags=['raw', 'commandes']
    )
}}

select * from {{ source('mysql_raw', 'RAW_COMMANDES') }}

