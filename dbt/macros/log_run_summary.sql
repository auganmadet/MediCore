{% macro log_run_summary(results) %}
  {# Comptage des statuts : pass/success, warn, error/fail, skip #}
  {% if execute %}
    {% set ns = namespace(ok=0, warn=0, err=0, skip=0, elapsed=0.0) %}
    {% for res in results %}
      {% if res.status in ['pass', 'success'] %}
        {% set ns.ok = ns.ok + 1 %}
      {% elif res.status == 'warn' %}
        {% set ns.warn = ns.warn + 1 %}
      {% elif res.status in ['error', 'fail'] %}
        {% set ns.err = ns.err + 1 %}
      {% else %}
        {% set ns.skip = ns.skip + 1 %}
      {% endif %}
      {% set ns.elapsed = ns.elapsed + res.execution_time %}
    {% endfor %}
    {% set total = results | length %}
    {{ log("DBT_SUMMARY | total=" ~ total ~ " ok=" ~ ns.ok ~ " warn=" ~ ns.warn ~ " error=" ~ ns.err ~ " skip=" ~ ns.skip ~ " elapsed=" ~ (ns.elapsed | round(1)) ~ "s", info=True) }}

    {# Persistance audit #}
    {{ persist_dbt_results(results) }}
  {% endif %}
{% endmacro %}
