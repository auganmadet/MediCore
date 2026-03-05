{% macro guard_full_refresh() %}
  {#
    ============================================================================
    MACRO : guard_full_refresh()
    ============================================================================

    PURPOSE:
      Protège les modèles incrémentaux tagués 'high_volume' contre un
      full-refresh accidentel qui pourrait recharger des millions de lignes
      et saturer le warehouse.

    BEHAVIOR:
      1. Premier run (table inexistante)  → laisse passer (bootstrap normal)
      2. Run incrémental classique         → laisse passer (pas de full-refresh)
      3. --full-refresh SANS allow_full_refresh → BLOQUE avec erreur explicite
      4. --full-refresh AVEC allow_full_refresh → laisse passer (bypass volontaire)

    USAGE:
      Ajouter en haut de chaque modèle incrémental high_volume, juste après
      le bloc config() :

        {{ config(
            materialized='incremental',
            tags=['high_volume', ...]
        ) }}
        {{ guard_full_refresh() }}

    BYPASS (refresh volontaire, ex: migration de schéma) :
      dbt run --full-refresh --vars '{allow_full_refresh: true}' --select <model>

    MODELS USING THIS MACRO:
      fact_commandes, fact_operateur, fact_prix_journalier,
      fact_stock_mouvement, fact_stock_valorisation, fact_ventes

    NOTE:
      Les modèles sans le tag 'high_volume' ne sont pas affectés même si
      la macro est appelée. Seul le tag déclenche le blocage.
    ============================================================================
  #}
  {% if not is_incremental() and not flags.FULL_REFRESH %}
    {# Premier run (table n'existe pas encore) : on laisse passer #}
  {% elif flags.FULL_REFRESH and var('allow_full_refresh', false) != true %}
    {% set model_tags = config.get('tags', []) %}
    {% if 'high_volume' in model_tags %}
      {{ exceptions.raise_compiler_error(
        "BLOQUE: full-refresh sur '" ~ this.name ~ "' (high_volume, potentiellement des millions de rows). "
        "Utiliser: dbt run --full-refresh --vars '{allow_full_refresh: true}' --select " ~ this.name
      ) }}
    {% endif %}
  {% endif %}
{% endmacro %}
