{{
    config(
        materialized='incremental',
        schema='MART',
        unique_key='pharmacie_sk',
        tags=['marts', 'dim', 'pharmacie']
    )
}}

with pharmacies_enriched as (
    select 
        p.PHA_ID,
        p.PHA_NOM,
        p.PHA_IDNAT,
        p.PHA_GERS,
        p.PHA_DATE_INSTAL_WP,
        ph.name as external_pharmacy_name,
        ph.city as external_city,
        ph.postal_code,
        p.loaded_at,
        row_number() over (
            partition by p.PHA_ID 
            order by p.loaded_at desc
        ) as rn
    from {{ ref('stg_pharmacie') }} p
    left join {{ ref('stg_pharmacies') }} ph 
        on p.PHA_ID = ph.parent_id
    where p.loaded_at > coalesce({{ this }}.valid_from, '1900-01-01')
),

scd2_changes as (
    select 
        PHA_ID,
        PHA_NOM,
        PHA_IDNAT,
        PHA_GERS,
        PHA_DATE_INSTAL_WP,
        external_pharmacy_name,
        external_city,
        postal_code,
        loaded_at,
        lag(PHA_NOM) over (partition by PHA_ID order by loaded_at) as prev_nom,
        lag(external_city) over (partition by PHA_ID order by loaded_at) as prev_city
    from pharmacies_enriched 
    where rn = 1
)

select 
    md5(PHA_ID::string || loaded_at::string) as pharmacie_sk,
    PHA_ID,
    coalesce(PHA_NOM, prev_nom) as PHA_NOM,
    PHA_IDNAT,
    PHA_GERS,
    PHA_DATE_INSTAL_WP,
    external_pharmacy_name,
    external_city,
    postal_code,
    loaded_at as valid_from,
    lead(loaded_at, 1, '9999-12-31') over (
        partition by PHA_ID order by loaded_at
    ) as valid_to,
    case 
        when lead(PHA_NOM) over (partition by PHA_ID order by loaded_at) is distinct from PHA_NOM 
        or lead(external_city) over (partition by PHA_ID order by loaded_at) is distinct from external_city
        then true 
        else false 
    end as is_current
from scd2_changes
