{% macro guard_seed_prod() %}
  {#
    ============================================================================
    MACRO : guard_seed_prod()
    ============================================================================

    PURPOSE:
      Empêche l'exécution de `dbt seed` sur l'environnement prod.
      Les seeds contiennent des fixtures de test (quelques dizaines de lignes)
      qui écraseraient les ~934M lignes des 18 tables RAW de production.

    BEHAVIOR:
      - `dbt seed --target test`  → laisse passer (usage normal CI)
      - `dbt seed --target dev`   → laisse passer (usage développeur)
      - `dbt seed --target prod`  → BLOQUE avec erreur explicite
      - bypass : `dbt seed --target prod --vars '{allow_seed_prod: true}'`

    USAGE:
      Appelée dans on-run-start de dbt_project.yml :
        on-run-start: "{{ guard_seed_prod() }}"
    ============================================================================
  #}
  {% if target.name == 'prod' and flags.WHICH == 'seed' %}
    {% if var('allow_seed_prod', false) != true %}
      {{ exceptions.raise_compiler_error(
        "BLOQUE: `dbt seed` interdit sur prod (target.name='" ~ target.name ~ "'). "
        "Les seeds écraseraient les tables RAW de production (~934M lignes). "
        "Les seeds sont réservés à l'environnement test (CI). "
        "Bypass (à vos risques) : dbt seed --target prod --vars '{allow_seed_prod: true}'"
      ) }}
    {% endif %}
  {% endif %}
{% endmacro %}
