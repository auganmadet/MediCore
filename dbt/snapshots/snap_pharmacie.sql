{% snapshot snap_pharmacie %}
{{
    config(
        target_schema='SNAPSHOTS',
        unique_key='PHA_ID',
        strategy='check',
        check_cols=['PHA_NOM', 'PHA_GERS', 'PHA_DATE_INSTAL_WP']
    )
}}

select
    PHA_ID,
    PHA_NOM,
    PHA_IDNAT,
    PHA_GERS,
    PHA_DATE_INSTAL_WP,
    loaded_at
from {{ ref('stg_pharmacie') }}

{% endsnapshot %}
