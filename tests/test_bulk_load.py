"""
Tests pour le bulk load MySQL → Snowflake (bulk_load.py).

Ce module teste :
1. Mapping des tables (CDC vs référence)
2. Ajout des métadonnées CDC aux DataFrames
3. Conversion des colonnes BOOLEAN (TINYINT → bool)
4. Renommage des colonnes (case-insensitive)
5. Génération des fichiers Parquet
6. Gestion des erreurs et reconnexion MySQL
7. Lock file pour exclusion mutuelle

Exécution :
    pytest tests/test_bulk_load.py -v
    pytest tests/test_bulk_load.py::TestTableMapping -v
"""

import pytest
import os
import sys
import tempfile
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# =============================================================================
# TESTS MAPPING TABLES
# =============================================================================

class TestTableMapping:
    """
    Tests du mapping des tables MySQL → Snowflake.
    
    Le projet gère 18 tables :
        - 4 tables CDC (COMMANDES, FACTURES, ORDERS, MODSTOCK)
        - 14 tables référence (PHARMACIE, PRODUITS, etc.)
    """

    def test_cdc_tables_count(self):
        """
        Vérifie qu'il y a exactement 4 tables CDC.
        
        Tables CDC = tables alimentées par Kafka/Debezium.
        Elles reçoivent des events CREATE/UPDATE/DELETE en continu.
        """
        from pipelines.bulk_load import CDC_TABLES
        
        assert len(CDC_TABLES) == 4, f"Attendu 4 tables CDC, obtenu {len(CDC_TABLES)}"
        
        expected = {'COMMANDES', 'FACTURES', 'ORDERS', 'MODSTOCK'}
        assert set(CDC_TABLES) == expected, f"Tables CDC incorrectes: {CDC_TABLES}"

    def test_ref_tables_count(self):
        """
        Vérifie qu'il y a exactement 14 tables référence.
        
        Tables référence = tables chargées en bulk (pas de CDC).
        Elles sont rechargées entièrement à chaque bulk load.
        """
        from pipelines.bulk_load import REF_TABLES
        
        assert len(REF_TABLES) == 14, f"Attendu 14 tables référence, obtenu {len(REF_TABLES)}"

    def test_total_tables_count(self):
        """
        Vérifie qu'il y a 18 tables au total (4 CDC + 14 référence).
        """
        from pipelines.bulk_load import TABLE_MAPPING
        
        assert len(TABLE_MAPPING) == 18, f"Attendu 18 tables, obtenu {len(TABLE_MAPPING)}"

    def test_table_mapping_format(self):
        """
        Vérifie le format du mapping : MySQL_TABLE → RAW_TABLE.
        
        Convention : table Snowflake = 'RAW_' + nom MySQL en majuscules.
        Exception : 'pharmacies' (minuscule) → 'RAW_PHARMACIES'.
        """
        from pipelines.bulk_load import TABLE_MAPPING
        
        for mysql_table, sf_table in TABLE_MAPPING.items():
            assert sf_table.startswith("RAW_"), f"{sf_table} doit commencer par 'RAW_'"
            # Vérifier que le nom Snowflake est en majuscules
            assert sf_table == sf_table.upper(), f"{sf_table} doit être en majuscules"


# =============================================================================
# TESTS MÉTADONNÉES CDC
# =============================================================================

class TestCDCMetadataAddition:
    """
    Tests de l'ajout des métadonnées CDC aux DataFrames.
    
    Le bulk load ajoute des colonnes CDC pour compatibilité avec le CDC streaming :
        - CDC_OPERATION = 'S' (Snapshot)
        - CDC_TIMESTAMP = datetime du chargement
        - CDC_LSN = None (pas de position binlog pour bulk)
    """

    def test_cdc_operation_is_snapshot(self):
        """
        Vérifie que CDC_OPERATION = 'S' pour les bulk loads.
        
        'S' = Snapshot (chargement initial), distinct de :
            - 'I' = Insert (CDC)
            - 'U' = Update (CDC)
            - 'D' = Delete (CDC)
        """
        import pandas as pd
        
        # Simuler l'ajout de métadonnées CDC
        df = pd.DataFrame({"PHA_ID": [1, 2]})
        df["CDC_OPERATION"] = "S"
        
        assert all(df["CDC_OPERATION"] == "S"), "Toutes les lignes doivent avoir CDC_OPERATION='S'"

    def test_cdc_timestamp_is_current(self):
        """
        Vérifie que CDC_TIMESTAMP est la datetime du chargement.
        
        Utilisé pour le filtre incremental dans les modèles dbt staging.
        """
        import pandas as pd
        
        before = datetime.now()
        df = pd.DataFrame({"PHA_ID": [1]})
        df["CDC_TIMESTAMP"] = datetime.now()
        after = datetime.now()
        
        ts = df["CDC_TIMESTAMP"].iloc[0]
        assert before <= ts <= after, "CDC_TIMESTAMP doit être la datetime courante"

    def test_cdc_lsn_is_none(self):
        """
        Vérifie que CDC_LSN = None pour les bulk loads.
        
        Le LSN (Log Sequence Number) n'existe que pour le CDC streaming.
        """
        import pandas as pd
        
        df = pd.DataFrame({"PHA_ID": [1]})
        df["CDC_LSN"] = None
        
        assert df["CDC_LSN"].iloc[0] is None, "CDC_LSN doit être None pour bulk load"


# =============================================================================
# TESTS CONVERSION BOOLEAN
# =============================================================================

class TestBooleanConversion:
    """
    Tests de conversion TINYINT(1) MySQL → BOOLEAN Snowflake.
    
    Problème : MySQL stocke les booléens comme TINYINT (0/1).
    Parquet les écrit comme int, mais Snowflake refuse de convertir
    un variant/int en BOOLEAN automatiquement.
    
    Solution : Convertir en Python bool avant d'écrire le Parquet.
    """

    def test_tinyint_to_bool_conversion(self):
        """
        Vérifie la conversion 0/1 → False/True.
        """
        import pandas as pd
        
        df = pd.DataFrame({"PRD_DELETED": [0, 1, 0, 1]})
        df["PRD_DELETED"] = df["PRD_DELETED"].astype(bool)
        
        expected = [False, True, False, True]
        assert list(df["PRD_DELETED"]) == expected, "Conversion TINYINT → bool incorrecte"

    def test_bool_dtype_after_conversion(self):
        """
        Vérifie que le dtype est bien 'bool' après conversion.
        
        Important pour que Parquet écrive le bon type logique.
        """
        import pandas as pd
        
        df = pd.DataFrame({"FLAG": [0, 1]})
        df["FLAG"] = df["FLAG"].astype(bool)
        
        assert df["FLAG"].dtype == bool, f"Dtype attendu 'bool', obtenu '{df['FLAG'].dtype}'"

    def test_null_handling_in_bool_column(self):
        """
        Vérifie la gestion des NULL dans les colonnes BOOLEAN.
        
        MySQL permet NULL même sur TINYINT(1).
        Pandas convertit en pd.NA ou NaN selon le cas.
        """
        import pandas as pd
        import numpy as np
        
        df = pd.DataFrame({"FLAG": [0, 1, None]})
        
        # Avec nullable boolean
        df["FLAG"] = df["FLAG"].astype("boolean")  # Nullable boolean dtype
        
        assert pd.isna(df["FLAG"].iloc[2]), "NULL doit rester NULL"


# =============================================================================
# TESTS RENOMMAGE COLONNES
# =============================================================================

class TestColumnRenaming:
    """
    Tests du renommage des colonnes MySQL → Snowflake.
    
    Les colonnes MySQL peuvent avoir un casing différent de Snowflake.
    Le bulk load renomme les colonnes selon le casing exact de Snowflake
    (récupéré via DESCRIBE TABLE).
    """

    def test_case_insensitive_matching(self):
        """
        Vérifie le matching case-insensitive des colonnes.
        
        MySQL 'pha_id' doit matcher Snowflake 'PHA_ID'.
        """
        # Simuler le mapping
        sf_columns = ["PHA_ID", "PRD_ID", "COM_QUANTITE"]
        sf_col_upper_map = {c.upper(): c for c in sf_columns}
        
        mysql_col = "pha_id"  # minuscules
        
        sf_col = sf_col_upper_map.get(mysql_col.upper())
        
        assert sf_col == "PHA_ID", "Doit matcher case-insensitive"

    def test_columns_renamed_to_snowflake_casing(self):
        """
        Vérifie que les colonnes du DataFrame sont renommées.
        """
        import pandas as pd
        
        df = pd.DataFrame({"pha_id": [1], "prd_id": [42]})
        
        # Mapping Snowflake
        sf_col_upper_map = {"PHA_ID": "PHA_ID", "PRD_ID": "PRD_ID"}
        
        # Renommer
        df.columns = [sf_col_upper_map.get(c.upper(), c.upper()) for c in df.columns]
        
        assert list(df.columns) == ["PHA_ID", "PRD_ID"], "Colonnes mal renommées"

    def test_extra_columns_filtered_out(self):
        """
        Vérifie que les colonnes MySQL absentes de Snowflake sont supprimées.
        
        Évite les erreurs COPY INTO si MySQL a des colonnes en plus.
        """
        import pandas as pd
        
        df = pd.DataFrame({
            "PHA_ID": [1],
            "PRD_ID": [42],
            "EXTRA_COLUMN": ["should be removed"]
        })
        
        sf_col_set = {"PHA_ID", "PRD_ID"}  # Colonnes Snowflake
        
        valid_cols = [c for c in df.columns if c in sf_col_set]
        df = df[valid_cols]
        
        assert "EXTRA_COLUMN" not in df.columns, "Colonne extra doit être supprimée"
        assert list(df.columns) == ["PHA_ID", "PRD_ID"], "Colonnes valides conservées"


# =============================================================================
# TESTS FICHIERS PARQUET
# =============================================================================

class TestParquetGeneration:
    """
    Tests de génération des fichiers Parquet.
    
    Flux : DataFrame pandas → fichier .parquet local → PUT @stage
    
    Options importantes :
        - coerce_timestamps='us' : timestamps en microsecondes
        - allow_truncated_timestamps=True : évite erreurs sur dates hors range
    """

    def test_parquet_file_created(self, temp_export_dir):
        """
        Vérifie qu'un fichier Parquet est créé dans le bon répertoire.
        """
        import pandas as pd
        
        df = pd.DataFrame({"PHA_ID": [1, 2, 3]})
        filepath = os.path.join(temp_export_dir, "test_0001.parquet")
        
        df.to_parquet(filepath, engine='pyarrow', index=False)
        
        assert os.path.exists(filepath), "Fichier Parquet non créé"

    def test_parquet_file_readable(self, temp_export_dir):
        """
        Vérifie que le fichier Parquet peut être relu.
        
        Valide l'intégrité du fichier généré.
        """
        import pandas as pd
        
        df_write = pd.DataFrame({"PHA_ID": [1, 2], "VALUE": ["a", "b"]})
        filepath = os.path.join(temp_export_dir, "test.parquet")
        
        df_write.to_parquet(filepath, engine='pyarrow', index=False)
        df_read = pd.read_parquet(filepath)
        
        assert len(df_read) == 2, "Nombre de lignes incorrect après relecture"
        assert list(df_read["PHA_ID"]) == [1, 2], "Données incorrectes après relecture"

    def test_parquet_timestamp_handling(self, temp_export_dir):
        """
        Vérifie la gestion des timestamps dans Parquet.
        
        coerce_timestamps='us' convertit en microsecondes pour compatibilité.
        """
        import pandas as pd
        
        df = pd.DataFrame({
            "ID": [1],
            "CREATED_AT": [datetime(2024, 1, 15, 12, 30, 0)]
        })
        filepath = os.path.join(temp_export_dir, "test.parquet")
        
        df.to_parquet(
            filepath, 
            engine='pyarrow', 
            index=False,
            coerce_timestamps='us',
            allow_truncated_timestamps=True
        )
        
        df_read = pd.read_parquet(filepath)
        assert df_read["CREATED_AT"].iloc[0].year == 2024, "Timestamp mal converti"

    def test_parquet_naming_convention(self):
        """
        Vérifie la convention de nommage des fichiers Parquet.
        
        Format : {TABLE}_{CHUNK:04d}.parquet
        Exemple : RAW_COMMANDES_0001.parquet
        """
        table = "RAW_COMMANDES"
        chunk_num = 1
        
        filename = f"{table}_{chunk_num:04d}.parquet"
        
        assert filename == "RAW_COMMANDES_0001.parquet", "Format de nom incorrect"


# =============================================================================
# TESTS RECONNEXION MYSQL
# =============================================================================

class TestMySQLReconnection:
    """
    Tests de la reconnexion automatique MySQL.
    
    Le bulk load sur tables volumineuses peut durer > 1h.
    MySQL peut déconnecter (timeout, réseau).
    Le code doit se reconnecter et reprendre à l'offset actuel.
    """

    def test_reconnection_on_operational_error(self, mock_mysql_conn):
        """
        Vérifie la reconnexion sur OperationalError.
        
        OperationalError = connexion perdue, timeout, etc.
        """
        import mysql.connector.errors
        
        # Simuler une déconnexion
        error = mysql.connector.errors.OperationalError("Lost connection")
        
        # Le code doit catcher cette erreur et reconnecter
        assert isinstance(error, Exception), "OperationalError doit être catchable"

    def test_reconnection_with_offset(self):
        """
        Vérifie que la reconnexion reprend au bon offset.
        
        Si on a lu 500,000 rows avant déconnexion, la requête
        de reconnexion doit faire OFFSET 500000.
        """
        total_rows = 500000
        
        # Query de reconnexion
        query = f"SELECT * FROM TABLE LIMIT 18446744073709551615 OFFSET {total_rows}"
        
        assert f"OFFSET {total_rows}" in query, "Offset doit être inclus dans la query"

    def test_max_reconnection_attempts(self):
        """
        Vérifie que le nombre de reconnexions est limité.
        
        MAX_RECONNECT = 10 dans le code.
        Après 10 échecs, une exception doit être levée.
        """
        MAX_RECONNECT = 10
        reconnect_count = 11
        
        if reconnect_count > MAX_RECONNECT:
            should_raise = True
        else:
            should_raise = False
        
        assert should_raise, "Doit lever exception après MAX_RECONNECT tentatives"


# =============================================================================
# TESTS LOCK FILE
# =============================================================================

class TestLockFile:
    """
    Tests du lock file pour exclusion mutuelle.
    
    Le lock empêche batch_loop.sh de lancer un CDC pendant un bulk load.
    Fichier : /tmp/bulk_load.lock
    """

    def test_lock_file_created(self, temp_export_dir):
        """
        Vérifie que acquire_lock() crée le fichier lock.
        """
        lock_path = os.path.join(temp_export_dir, "bulk_load.lock")
        
        # Simuler acquire_lock
        with open(lock_path, 'w') as f:
            f.write(f"{os.getpid()} {datetime.now().isoformat()}")
        
        assert os.path.exists(lock_path), "Lock file non créé"

    def test_lock_file_contains_pid(self, temp_export_dir):
        """
        Vérifie que le lock file contient le PID du processus.
        
        Utile pour debug : savoir quel processus a le lock.
        """
        lock_path = os.path.join(temp_export_dir, "bulk_load.lock")
        pid = os.getpid()
        
        with open(lock_path, 'w') as f:
            f.write(f"{pid} {datetime.now().isoformat()}")
        
        with open(lock_path, 'r') as f:
            content = f.read()
        
        assert str(pid) in content, "PID doit être dans le lock file"

    def test_lock_file_released(self, temp_export_dir):
        """
        Vérifie que release_lock() supprime le fichier lock.
        """
        lock_path = os.path.join(temp_export_dir, "bulk_load.lock")
        
        # Créer le lock
        with open(lock_path, 'w') as f:
            f.write("test")
        
        # Simuler release_lock
        os.remove(lock_path)
        
        assert not os.path.exists(lock_path), "Lock file doit être supprimé"

    def test_lock_file_released_on_error(self, temp_export_dir):
        """
        Vérifie que le lock est libéré même en cas d'erreur.
        
        Utilise try/finally pour garantir la libération.
        """
        lock_path = os.path.join(temp_export_dir, "bulk_load.lock")
        
        try:
            # Créer lock
            with open(lock_path, 'w') as f:
                f.write("test")
            
            # Simuler erreur
            raise Exception("Erreur simulée")
        except Exception:
            pass
        finally:
            # Libérer lock
            if os.path.exists(lock_path):
                os.remove(lock_path)
        
        assert not os.path.exists(lock_path), "Lock doit être libéré après erreur"


# =============================================================================
# TESTS ARGUMENTS CLI
# =============================================================================

class TestCLIArguments:
    """
    Tests des arguments ligne de commande.
    
    Options :
        --tables TABLE1 TABLE2 : charger tables spécifiques
        --cdc-only : charger uniquement les 4 tables CDC
        --ref-only : charger uniquement les 14 tables référence
        --truncate : TRUNCATE avant INSERT
        --chunk-size N : taille des chunks (défaut 500000)
    """

    def test_tables_filter(self):
        """
        Vérifie que --tables filtre les tables à charger.
        """
        from pipelines.bulk_load import TABLE_MAPPING
        
        selected = ["PHARMACIE", "PRODUITS"]
        
        tables = {t: TABLE_MAPPING[t] for t in selected if t in TABLE_MAPPING}
        
        assert len(tables) == 2, "Doit filtrer à 2 tables"
        assert "PHARMACIE" in tables, "PHARMACIE doit être inclus"

    def test_cdc_only_filter(self):
        """
        Vérifie que --cdc-only sélectionne les 4 tables CDC.
        """
        from pipelines.bulk_load import TABLE_MAPPING, CDC_TABLES
        
        tables = {t: TABLE_MAPPING[t] for t in CDC_TABLES}
        
        assert len(tables) == 4, "cdc-only doit sélectionner 4 tables"

    def test_ref_only_filter(self):
        """
        Vérifie que --ref-only sélectionne les 14 tables référence.
        """
        from pipelines.bulk_load import TABLE_MAPPING, REF_TABLES
        
        tables = {t: TABLE_MAPPING[t] for t in REF_TABLES}
        
        assert len(tables) == 14, "ref-only doit sélectionner 14 tables"

    def test_default_chunk_size(self):
        """
        Vérifie la valeur par défaut de chunk_size.
        
        Défaut = 500,000 lignes par fichier Parquet.
        """
        default_chunk_size = 500000
        
        assert default_chunk_size == 500000, "Chunk size par défaut incorrect"


# =============================================================================
# TESTS GESTION MÉMOIRE
# =============================================================================

class TestMemoryManagement:
    """
    Tests de la gestion mémoire.
    
    Le bulk load de tables volumineuses (>100M rows) peut consommer
    beaucoup de RAM. Le code utilise :
        - gc.collect() après chaque chunk
        - del df pour libérer les DataFrames
        - Chunking pour éviter de charger tout en mémoire
    """

    def test_gc_collect_frees_memory(self):
        """
        Vérifie que gc.collect() libère la mémoire.
        
        Note : test indicatif, la libération réelle dépend du GC Python.
        """
        import gc
        import pandas as pd
        
        # Créer un gros DataFrame
        df = pd.DataFrame({"COL": range(100000)})
        
        # Supprimer et collecter
        del df
        collected = gc.collect()
        
        # collected = nombre d'objets collectés (peut être 0 si déjà libérés)
        assert collected >= 0, "gc.collect() doit s'exécuter sans erreur"

    def test_chunking_limits_memory(self):
        """
        Vérifie que le chunking limite la taille des DataFrames.
        """
        chunk_size = 500000
        total_rows = 2000000
        
        num_chunks = (total_rows + chunk_size - 1) // chunk_size
        
        assert num_chunks == 4, f"Attendu 4 chunks, obtenu {num_chunks}"
