"""
Package de tests pytest pour le projet MediCore.

Structure :
    tests/
    ├── conftest.py              # Fixtures partagées
    ├── test_daily_cdc_batch.py  # Tests consumer CDC Kafka
    ├── test_bulk_load.py        # Tests bulk load MySQL → Snowflake
    ├── test_pii_masking.py      # Tests masquage données personnelles
    └── __init__.py              # Ce fichier

Exécution :
    # Tous les tests
    pytest tests/ -v
    
    # Un fichier spécifique
    pytest tests/test_daily_cdc_batch.py -v
    
    # Un test spécifique
    pytest tests/test_daily_cdc_batch.py::TestParseDebeziumEvent::test_parse_debezium_create_event -v
    
    # Avec couverture de code
    pytest tests/ -v --cov=pipelines --cov-report=html
"""
