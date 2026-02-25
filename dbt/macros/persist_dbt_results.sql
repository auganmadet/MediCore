{% macro persist_dbt_results(results) %}
  {# Persiste les résultats dbt dans MEDICORE.AUDIT.DBT_MODEL_RUNS #}
  {% if execute %}
    {% set run_id = var('run_id', 'manual') %}
    {% for res in results %}
      {% set rows = res.adapter_response.rows_affected if res.adapter_response and res.adapter_response.rows_affected else None %}
      {% set insert_query %}
        INSERT INTO MEDICORE.AUDIT.DBT_MODEL_RUNS
          (RUN_ID, DBT_INVOCATION_ID, MODEL_NAME, MODEL_SCHEMA, STATUS, EXECUTION_TIME_S, ROWS_AFFECTED)
        VALUES (
          '{{ run_id }}',
          '{{ invocation_id }}',
          '{{ res.node.name }}',
          '{{ res.node.schema }}',
          '{{ res.status }}',
          {{ res.execution_time }},
          {{ rows if rows is not none else 'NULL' }}
        )
      {% endset %}
      {% do run_query(insert_query) %}
    {% endfor %}
  {% endif %}
{% endmacro %}
