{% snapshot snap_produit %}
{{
    config(
        target_schema='SNAPSHOTS',
        unique_key="PHA_ID || '-' || PRD_ID",
        strategy='check',
        check_cols=['PRD_NOM', 'PRD_CODEREMBT', 'PRD_CODEACTE', 'PRD_TVA', 'FOU_ID']
    )
}}

select
    PHA_ID,
    PRD_ID,
    PRD_NOM,
    PRD_EAN13,
    PRD_CODEREMBT,
    PRD_CODEACTE,
    PRD_TVA,
    FOU_ID,
    loaded_at
from {{ ref('stg_produits') }}

{% endsnapshot %}
