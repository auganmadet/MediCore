{% macro guard_full_refresh() %}
  {#
    Bloque le full-refresh sur les modeles tagues 'high_volume'
    sauf si --vars '{allow_full_refresh: true}' est passe explicitement.

    Usage : ajouter {{ guard_full_refresh() }} en haut du modele.
    Bypass : dbt run --full-refresh --vars '{allow_full_refresh: true}'
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
