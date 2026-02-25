{% snapshot snap_fournisseur %}
{{
    config(
        target_schema='SNAPSHOTS',
        unique_key="PHA_ID || '-' || FOU_ID",
        strategy='check',
        check_cols=['FOU_NOM', 'FOU_TYPE', 'FOU_REPARTITEUR', 'FOU_ADRESSE', 'FOU_CP', 'FOU_VILLE']
    )
}}

select
    PHA_ID,
    FOU_ID,
    FOU_NOM,
    FOU_ADRESSE,
    FOU_CP,
    FOU_VILLE,
    FOU_TYPE,
    FOU_REPARTITEUR,
    FOU_ETABLISSEMENT,
    loaded_at
from {{ ref('stg_fournisseurs') }}

{% endsnapshot %}
