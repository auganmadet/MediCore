{% macro reapply_rls_policies() %}
{#
    Réapplique les Row Access Policies sur toutes les tables MARTS après chaque dbt run.
    Nécessaire car materialized='table' fait DROP + CREATE, ce qui supprime les policies.
    Appelé via on-run-end dans dbt_project.yml.

    Utilise un bloc Snowflake Scripting BEGIN/EXCEPTION pour ignorer l'erreur
    si la policy n'est pas attachée (cas après DROP+CREATE d'un modèle table).
#}

{% set tables_pha_id = ['DIM_PHARMACIE', 'DIM_PRODUIT', 'DIM_FOURNISSEUR', 'MART_KPI_DORMANT'] %}

{% set tables_pharmacie_sk = [
    'FACT_COMMANDES', 'FACT_OPERATEUR', 'FACT_PRIX_JOURNALIER', 'FACT_RUPTURES',
    'FACT_STOCK_MOUVEMENT', 'FACT_STOCK_VALORISATION', 'FACT_TRESORERIE', 'FACT_VENTES',
    'MART_KPI_ABC', 'MART_KPI_CA_EVOLUTION', 'MART_KPI_ECOULEMENT', 'MART_KPI_GENERIQUE',
    'MART_KPI_MARGE', 'MART_KPI_OPERATEUR', 'MART_KPI_QUALITE_DONNEES',
    'MART_KPI_REMISE_LABO', 'MART_KPI_RUPTURES', 'MART_KPI_STOCK_VALORISATION',
    'MART_KPI_SYNTHESE_PHARMACIE', 'MART_KPI_TRESORERIE', 'MART_KPI_UNIVERS',
    'MART_KPI_MARGE_PAR_PRODUIT', 'MART_KPI_MARGE_PAR_UNIVERS',
    'MART_KPI_RUPTURES_PAR_PRODUIT', 'MART_KPI_ECOULEMENT_PAR_FOURNISSEUR',
    'MART_KPI_VENTES_PAR_PRODUIT', 'MART_KPI_GENERIQUE_MARGE', 'MART_KPI_STOCK'
] %}

{% for table in tables_pha_id %}
    {% set fq_table = target.database ~ '.MARTS.' ~ table %}
    {% set fq_policy = target.database ~ '.AUDIT.RLS_PHARMACY_POLICY_ID' %}
    {% do run_query("BEGIN\n  ALTER TABLE " ~ fq_table ~ " DROP ROW ACCESS POLICY " ~ fq_policy ~ ";\nEXCEPTION\n  WHEN OTHER THEN NULL;\nEND;") %}
    {% do run_query("ALTER TABLE " ~ fq_table ~ " ADD ROW ACCESS POLICY " ~ fq_policy ~ " ON (PHA_ID)") %}
{% endfor %}

{% for table in tables_pharmacie_sk %}
    {% set fq_table = target.database ~ '.MARTS.' ~ table %}
    {% set fq_policy = target.database ~ '.AUDIT.RLS_PHARMACY_POLICY_SK' %}
    {% do run_query("BEGIN\n  ALTER TABLE " ~ fq_table ~ " DROP ROW ACCESS POLICY " ~ fq_policy ~ ";\nEXCEPTION\n  WHEN OTHER THEN NULL;\nEND;") %}
    {% do run_query("ALTER TABLE " ~ fq_table ~ " ADD ROW ACCESS POLICY " ~ fq_policy ~ " ON (PHARMACIE_SK)") %}
{% endfor %}

{{ log("RLS policies réappliquées sur " ~ (tables_pha_id | length) ~ " + " ~ (tables_pharmacie_sk | length) ~ " tables MARTS", info=True) }}

{% endmacro %}
