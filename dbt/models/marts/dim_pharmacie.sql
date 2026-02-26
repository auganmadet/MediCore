{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'dim', 'pharmacie']
    )
}}

with pharmacies_dedup as (
    select
        p.PHA_ID,
        p.PHA_NOM,
        p.PHA_IDNAT,
        p.PHA_GERS,
        p.PHA_DATE_INSTAL_WP,
        ph.name as external_pharmacy_name,
        ph.city as external_city,
        ph.postal_code,
        row_number() over (
            partition by p.PHA_ID
            order by p.loaded_at desc
        ) as rn
    from {{ ref('stg_pharmacie') }} p
    left join {{ ref('stg_pharmacies') }} ph
        on p.PHA_ID = ph.parent_id
)

select
    md5(PHA_ID::string) as pharmacie_sk,
    PHA_ID,
    PHA_NOM,
    PHA_IDNAT,
    PHA_GERS,
    PHA_DATE_INSTAL_WP,
    external_pharmacy_name,
    external_city,
    postal_code
from pharmacies_dedup
where rn = 1

union all

select
    md5('-1') as pharmacie_sk,
    -1 as PHA_ID,
    'INCONNU' as PHA_NOM,
    null as PHA_IDNAT,
    null as PHA_GERS,
    null as PHA_DATE_INSTAL_WP,
    null as external_pharmacy_name,
    null as external_city,
    null as postal_code
