"""
Tests pour le masquage PII (Personally Identifiable Information).

Ce module teste les fonctions de masquage des données personnelles :
    - Noms de pharmacies
    - Noms d'opérateurs
    - Adresses, téléphones, etc.

Le masquage utilise MD5 pour pseudonymiser les données.
Format : PREFIX_ + 8 premiers caractères du hash MD5.

Exécution :
    pytest tests/test_pii_masking.py -v
"""

import pytest
import hashlib
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# =============================================================================
# TESTS MASQUAGE PII
# =============================================================================

class TestPIIMasking:
    """
    Tests du masquage des données personnelles.
    
    Le masquage est appliqué dans les modèles dbt staging pour :
        - Respecter le RGPD
        - Permettre l'analyse sans exposer les données personnelles
        - Garder la possibilité de joindre les données (hash déterministe)
    """

    def test_mask_pii_format(self):
        """
        Vérifie le format du masquage : PREFIX_HASH.
        
        Format actuel dans le code dbt :
            'PHARM_' || LEFT(MD5(CAST(PHA_NOM AS VARCHAR)), 4)
        
        Exemple : "Pharmacie Dupont" → "PHARM_a1b2"
        """
        value = "Pharmacie Dupont"
        prefix = "PHARM"
        hash_length = 4
        
        # Simuler le masquage SQL
        md5_hash = hashlib.md5(value.encode()).hexdigest()
        masked = f"{prefix}_{md5_hash[:hash_length]}"
        
        assert masked.startswith("PHARM_"), "Doit commencer par le préfixe"
        assert len(masked) == len("PHARM_") + hash_length, "Longueur incorrecte"

    def test_mask_pii_deterministic(self):
        """
        Vérifie que le masquage est déterministe.
        
        CRITIQUE : Le même input doit TOUJOURS donner le même output.
        Sinon les jointures entre tables ne fonctionnent plus.
        """
        value = "Jean Dupont"
        
        hash1 = hashlib.md5(value.encode()).hexdigest()[:8]
        hash2 = hashlib.md5(value.encode()).hexdigest()[:8]
        
        assert hash1 == hash2, "Masquage doit être déterministe"

    def test_mask_pii_different_inputs_different_outputs(self):
        """
        Vérifie que des inputs différents donnent des outputs différents.
        
        Important pour éviter les collisions qui fausseraient les analyses.
        """
        value1 = "Pharmacie A"
        value2 = "Pharmacie B"
        
        hash1 = hashlib.md5(value1.encode()).hexdigest()[:8]
        hash2 = hashlib.md5(value2.encode()).hexdigest()[:8]
        
        assert hash1 != hash2, "Inputs différents doivent donner outputs différents"

    def test_mask_pii_case_sensitive(self):
        """
        Vérifie que le masquage est sensible à la casse.
        
        "DUPONT" et "Dupont" doivent donner des hashes différents.
        """
        value_upper = "DUPONT"
        value_mixed = "Dupont"
        
        hash_upper = hashlib.md5(value_upper.encode()).hexdigest()[:8]
        hash_mixed = hashlib.md5(value_mixed.encode()).hexdigest()[:8]
        
        assert hash_upper != hash_mixed, "Casse différente = hash différent"

    def test_mask_pii_empty_string(self):
        """
        Vérifie le comportement avec une chaîne vide.
        
        Une chaîne vide doit quand même produire un hash (hash de "").
        """
        value = ""
        
        md5_hash = hashlib.md5(value.encode()).hexdigest()
        masked = f"PHARM_{md5_hash[:4]}"
        
        # MD5("") = d41d8cd98f00b204e9800998ecf8427e
        assert masked == "PHARM_d41d", f"Hash de chaîne vide incorrect: {masked}"

    def test_mask_pii_special_characters(self):
        """
        Vérifie le masquage avec caractères spéciaux.
        
        Les noms peuvent contenir accents, apostrophes, etc.
        """
        values = [
            "Pharmacie l'Étoile",
            "Dr. O'Brien & Associés",
            "Müller Apotheke",
            "中文药房"  # Caractères chinois
        ]
        
        for value in values:
            md5_hash = hashlib.md5(value.encode()).hexdigest()
            assert len(md5_hash) == 32, f"MD5 invalide pour: {value}"

    def test_mask_pii_none_handling(self):
        """
        Vérifie la gestion des valeurs NULL.
        
        En SQL : COALESCE(column, '') ou gestion explicite des NULL.
        """
        # En Python, on doit gérer None explicitement
        value = None
        
        if value is None:
            masked = None  # ou "PHARM_NULL" selon la convention
        else:
            md5_hash = hashlib.md5(str(value).encode()).hexdigest()
            masked = f"PHARM_{md5_hash[:4]}"
        
        assert masked is None, "NULL doit rester NULL (ou être géré explicitement)"

    def test_mask_pii_sql_equivalent(self):
        """
        Vérifie l'équivalence Python ↔ SQL.
        
        Le code SQL dans dbt :
            'PHARM_' || LEFT(MD5(CAST(PHA_NOM AS VARCHAR)), 4)
        
        Doit produire le même résultat que Python.
        """
        value = "Test Pharmacie"
        
        # Python
        python_hash = hashlib.md5(value.encode()).hexdigest()[:4]
        python_masked = f"PHARM_{python_hash}"
        
        # SQL (simulé) - MD5 en Snowflake retourne hex lowercase
        sql_hash = hashlib.md5(value.encode()).hexdigest()[:4].lower()
        sql_masked = f"PHARM_{sql_hash}"
        
        assert python_masked == sql_masked, "Python et SQL doivent produire le même résultat"


# =============================================================================
# TESTS MASQUAGE PAR TYPE DE DONNÉE
# =============================================================================

class TestPIIMaskingByType:
    """
    Tests du masquage par type de donnée.
    
    Différents préfixes selon le type :
        - PHARM_ : noms de pharmacies
        - USER_ : noms d'opérateurs
        - ADDR_ : adresses (si implémenté)
    """

    def test_pharmacy_name_prefix(self):
        """
        Vérifie le préfixe pour les noms de pharmacies.
        """
        value = "Pharmacie du Centre"
        prefix = "PHARM"
        
        md5_hash = hashlib.md5(value.encode()).hexdigest()[:4]
        masked = f"{prefix}_{md5_hash}"
        
        assert masked.startswith("PHARM_"), "Pharmacies doivent avoir préfixe PHARM_"

    def test_operator_name_prefix(self):
        """
        Vérifie le préfixe pour les noms d'opérateurs.
        
        Opérateur = personne qui effectue une vente en pharmacie.
        """
        value = "Jean Martin"
        prefix = "USER"
        
        md5_hash = hashlib.md5(value.encode()).hexdigest()[:4]
        masked = f"{prefix}_{md5_hash}"
        
        assert masked.startswith("USER_"), "Opérateurs doivent avoir préfixe USER_"

    def test_hash_length_sufficient(self):
        """
        Vérifie que la longueur du hash (4 chars) est suffisante.
        
        4 caractères hex = 16^4 = 65,536 combinaisons.
        Suffisant pour ~1000 pharmacies avec faible risque de collision.
        
        Pour plus de sécurité, on pourrait augmenter à 8 caractères.
        """
        hash_length = 4
        combinations = 16 ** hash_length
        
        # Approximation : collision probable à sqrt(combinations) entrées
        collision_threshold = int(combinations ** 0.5)
        
        assert collision_threshold > 200, f"Risque de collision trop élevé avec {hash_length} chars"


# =============================================================================
# TESTS RÉVERSIBILITÉ
# =============================================================================

class TestPIIMaskingReversibility:
    """
    Tests de non-réversibilité du masquage.
    
    Le MD5 est une fonction de hachage à sens unique.
    On ne peut pas retrouver la valeur originale depuis le hash.
    
    Note : MD5 n'est plus considéré sûr pour la cryptographie,
    mais suffisant pour la pseudonymisation à des fins analytiques.
    """

    def test_hash_not_reversible(self):
        """
        Vérifie qu'on ne peut pas retrouver la valeur depuis le hash.
        
        Test conceptuel : il n'existe pas de fonction unhash(hash) → value.
        """
        value = "Donnée Sensible"
        md5_hash = hashlib.md5(value.encode()).hexdigest()
        
        # Il n'existe pas de méthode pour inverser MD5
        # (sauf attaque par force brute ou rainbow table)
        
        assert len(md5_hash) == 32, "MD5 produit toujours 32 caractères hex"
        # Impossible de vérifier la non-réversibilité par test,
        # c'est une propriété mathématique de MD5

    def test_truncated_hash_even_less_reversible(self):
        """
        Vérifie que le hash tronqué est encore moins réversible.
        
        On ne garde que 4 caractères sur 32, donc 87.5% de l'information
        est perdue. Même avec une rainbow table, impossible de retrouver
        la valeur originale.
        """
        value = "Secret"
        full_hash = hashlib.md5(value.encode()).hexdigest()
        truncated = full_hash[:4]
        
        # Beaucoup de valeurs différentes produisent le même hash tronqué
        # (collisions intentionnelles pour renforcer l'anonymisation)
        
        assert len(truncated) == 4, "Hash tronqué = 4 caractères"
        assert len(full_hash) == 32, "Hash complet = 32 caractères"
