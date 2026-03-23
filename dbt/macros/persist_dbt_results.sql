{% macro persist_dbt_results(results) %}
  {# Persiste les résultats dbt dans MEDICORE_PROD.AUDIT.DBT_MODEL_RUNS #}
  {# NOTE: Ce macro skip silencieusement si la table n'existe pas #}
  {% if execute %}
    {% set run_id = var('run_id', 'manual') %}
    
    {# Tente d'insérer - ignore les erreurs si table inexistante #}
    {% for res in results %}
      {% set rows = res.adapter_response.rows_affected if res.adapter_response and res.adapter_response.rows_affected else None %}
      {% set insert_query %}
        INSERT INTO MEDICORE_PROD.AUDIT.DBT_MODEL_RUNS
          (RUN_ID, DBT_INVOCATION_ID, MODEL_NAME, MODEL_SCHEMA, STATUS, EXECUTION_TIME_S, ROWS_AFFECTED)
        SELECT 
          '{{ run_id }}',
          '{{ invocation_id }}',
          '{{ res.node.name }}',
          '{{ res.node.schema }}',
          '{{ res.status }}',
          {{ res.execution_time }},
          {{ rows if rows is not none else 'NULL' }}
        WHERE EXISTS (
          SELECT 1 FROM MEDICORE_PROD.INFORMATION_SCHEMA.TABLES 
          WHERE TABLE_SCHEMA = 'AUDIT' AND TABLE_NAME = 'DBT_MODEL_RUNS'
        )
      {% endset %}
      {% do run_query(insert_query) %}
    {% endfor %}
  {% endif %}
{% endmacro %}
