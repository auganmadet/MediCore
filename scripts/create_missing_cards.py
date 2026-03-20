"""Création des 17 cartes manquantes pour atteindre 95 cartes MediCore.

Utilise des requêtes natives SQL pour les cartes nécessitant des JOINs
et MBQL pour les cartes simples.
"""

import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:3000/api"
DB_ID = 2  # Snowflake MediCore

# ── Collections ────────────────────────────────────────────────────────────
C = {
    "direction": 6,
    "ventes": 7,
    "achats": 8,
    "qualite": 9,
    "detail": 10,
}

# ── Dashboards ─────────────────────────────────────────────────────────────
D = {
    "d3": 4, "d4": 5, "d5": 6, "d7": 8, "d8": 9,
    "d9": 10, "d10": 11, "d11": 12, "d12": 13,
    "d13": 14, "d14": 15, "d15": 16, "d16": 17,
}

# ── Tables ─────────────────────────────────────────────────────────────────
T = {
    "kpi_stock": 16,
    "kpi_stock_val": 19,
    "kpi_ruptures": 18,
    "kpi_ecoulement": 9,
    "kpi_dormant": 17,
    "kpi_abc": 10,
    "kpi_generique": 21,
    "kpi_qualite": 12,
    "kpi_operateur": 14,
    "kpi_remise_labo": 34,
    "fact_tresorerie": 24,
    "fact_stock_mouvement": 28,
    "fact_ventes": 27,
}

# ── Field IDs ──────────────────────────────────────────────────────────────
# fact_tresorerie
F_FT_DATE = 276
F_FT_TVA1 = 293
F_FT_TVA2 = 294
F_FT_TVA3 = 295
F_FT_TVA4 = 296
F_FT_TVA5 = 297

# kpi_stock
F_KS_MOIS = 256
F_KS_STOCK_MOY = 257
F_KS_QTE_VENDUE = 262

# kpi_stock_val
F_KSV_MOIS = 108
F_KSV_VAR_PRIX = 117

# kpi_operateur
F_KO_OP = 228
F_KO_MOIS = 229
F_KO_CLIENTS_JOUR = 236  # NB_CLIENTS_PAR_JOUR

# kpi_dormant
F_KD_FOU_NOM = 78
F_KD_DORM6 = 89

# kpi_abc
F_KA_CLASSE = 175

# kpi_generique
F_KG_IS_GEN = 132
F_KG_MARGE = None  # Need to check

# kpi_qualite
F_KQ_STATUT = 195

# kpi_remise_labo
F_KRL_FOU_NOM = 442
F_KRL_MOIS = 443
F_KRL_MONTANT = 445
F_KRL_EVOL_MONTANT = 456

# fact_stock_mouvement
F_FSM_DATE = 342
F_FSM_APRES = 344

# fact_ventes
F_FV_DATE = 330
F_FV_AGE = 336
F_FV_CA_TTC = 333


def api(method: str, path: str, body: dict = None) -> dict:
    """Appel API Metabase."""
    url = f"{BASE_URL}/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Content-Type": "application/json",
            "X-Metabase-Session": TOKEN,
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"  ERREUR {e.code}: {err[:300]}")
        return {}


def field(fid: int) -> list:
    """Référence à un champ."""
    return ["field", fid, None]


def field_temporal(fid: int, unit: str = "month") -> list:
    """Référence temporelle."""
    return ["field", fid, {"temporal-unit": unit}]


def create_card_mbql(
    name: str,
    table_id: int,
    collection_id: int,
    display: str = "table",
    breakout: list = None,
    aggregation: list = None,
    fields: list = None,
    filter_clause: list = None,
    order_by: list = None,
    limit: int = None,
) -> int:
    """Créé une carte MBQL et retourne son ID."""
    query = {
        "database": DB_ID,
        "type": "query",
        "query": {"source-table": table_id},
    }
    if aggregation:
        query["query"]["aggregation"] = aggregation
    if breakout:
        query["query"]["breakout"] = breakout
    if fields:
        query["query"]["fields"] = fields
    if filter_clause:
        query["query"]["filter"] = filter_clause
    if order_by:
        query["query"]["order-by"] = order_by
    if limit:
        query["query"]["limit"] = limit

    body = {
        "name": name,
        "dataset_query": query,
        "display": display,
        "collection_id": collection_id,
        "visualization_settings": {},
    }
    result = api("POST", "card", body)
    card_id = result.get("id", 0)
    if card_id:
        print(f"  + carte {card_id:>4}: {name} ({display})")
    return card_id


def create_card_native(
    name: str,
    sql: str,
    collection_id: int,
    display: str = "table",
) -> int:
    """Créé une carte SQL native et retourne son ID."""
    body = {
        "name": name,
        "dataset_query": {
            "database": DB_ID,
            "type": "native",
            "native": {"query": sql},
        },
        "display": display,
        "collection_id": collection_id,
        "visualization_settings": {},
    }
    result = api("POST", "card", body)
    card_id = result.get("id", 0)
    if card_id:
        print(f"  + carte {card_id:>4}: {name} ({display}) [SQL]")
    return card_id


def add_to_dash(dash_id: int, new_card_ids: list) -> None:
    """Ajoute des cartes à un dashboard en préservant les existantes."""
    dash = api("GET", f"dashboard/{dash_id}")
    existing = dash.get("dashcards", [])

    max_row = 0
    for dc in existing:
        bottom = dc.get("row", 0) + dc.get("size_y", 4)
        if bottom > max_row:
            max_row = bottom

    dashcards = []
    for dc in existing:
        dashcards.append({
            "id": dc["id"],
            "card_id": dc.get("card", {}).get("id") or dc.get("card_id"),
            "row": dc["row"],
            "col": dc["col"],
            "size_x": dc["size_x"],
            "size_y": dc["size_y"],
        })

    for i, cid in enumerate(new_card_ids):
        if not cid:
            continue
        col = (i % 2) * 9
        row = max_row + (i // 2) * 4
        size_x = 9 if (i % 2 == 0 and i + 1 < len(new_card_ids)) else 18 - col
        dashcards.append({
            "id": -1,
            "card_id": cid,
            "row": row,
            "col": col,
            "size_x": size_x,
            "size_y": 4,
        })

    if len(new_card_ids) % 2 == 1 and dashcards:
        dashcards[-1]["size_x"] = 18

    api("PUT", f"dashboard/{dash_id}", {"dashcards": dashcards})
    print(f"  => +{len(new_card_ids)} cartes ajoutées au dashboard {dash_id} "
          f"(total {len(dashcards)})")


def build_missing_cards() -> None:
    """Construit les 17 cartes manquantes."""

    # ══════════════════════════════════════════════════════════════════════
    # D3 — TVA par taux (fact_tresorerie, 5 colonnes) — déjà créée
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D3 - TVA par taux (déjà créée id=375) ===")
    c1 = 375
    add_to_dash(D["d3"], [c1])

    # ══════════════════════════════════════════════════════════════════════
    # D4 — 3 cartes manquantes (JOINs dim_produit)
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D4 - Cartes manquantes : Top produits, Taux par univers, Distribution ===")
    c2 = create_card_native(
        "Top 20 produits par marge", """
SELECT p.PRD_NOM, SUM(m.MARGE_BRUTE) AS marge_brute
FROM MEDICORE_PROD.MARTS.MART_KPI_MARGE m
JOIN MEDICORE_PROD.MARTS.DIM_PRODUIT p ON m.PRODUIT_SK = p.PRODUIT_SK
GROUP BY 1 ORDER BY 2 DESC
LIMIT 20""",
        C["ventes"], "bar",
    )
    c3 = create_card_native(
        "Taux de marge par univers", """
SELECT p.PRD_UNIVERS AS univers,
       AVG(m.TAUX_MARGE) AS taux_marge_moyen
FROM MEDICORE_PROD.MARTS.MART_KPI_MARGE m
JOIN MEDICORE_PROD.MARTS.DIM_PRODUIT p ON m.PRODUIT_SK = p.PRODUIT_SK
WHERE p.PRD_UNIVERS IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC""",
        C["ventes"], "bar",
    )
    c4 = create_card_native(
        "Distribution taux de marge", """
SELECT
    CASE
        WHEN TAUX_MARGE < 0 THEN '< 0%'
        WHEN TAUX_MARGE < 0.10 THEN '0-10%'
        WHEN TAUX_MARGE < 0.20 THEN '10-20%'
        WHEN TAUX_MARGE < 0.30 THEN '20-30%'
        WHEN TAUX_MARGE < 0.40 THEN '30-40%'
        WHEN TAUX_MARGE < 0.50 THEN '40-50%'
        ELSE '50%+'
    END AS tranche_marge,
    COUNT(*) AS nb_lignes
FROM MEDICORE_PROD.MARTS.MART_KPI_MARGE
GROUP BY 1 ORDER BY 1""",
        C["ventes"], "bar",
    )
    add_to_dash(D["d4"], [c2, c3, c4])

    # ══════════════════════════════════════════════════════════════════════
    # D5 — Clients/jour par opérateur
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D5 - Carte manquante : Clients/jour ===")
    c5 = create_card_mbql(
        "Nb clients/jour par opérateur", T["kpi_operateur"], C["ventes"], "table",
        fields=[field(F_KO_OP), field(F_KO_CLIENTS_JOUR)],
        order_by=[["desc", field(F_KO_CLIENTS_JOUR)]],
    )
    add_to_dash(D["d5"], [c5])

    # ══════════════════════════════════════════════════════════════════════
    # D7 — Stock moyen vs ventes + Variation prix achat
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D7 - Cartes manquantes : Stock vs ventes, Variation prix ===")
    c6 = create_card_mbql(
        "Stock moyen vs ventes", T["kpi_stock"], C["achats"], "bar",
        breakout=[field_temporal(F_KS_MOIS)],
        aggregation=[["avg", field(F_KS_STOCK_MOY)], ["sum", field(F_KS_QTE_VENDUE)]],
    )
    c7 = create_card_mbql(
        "Variation prix achat", T["kpi_stock_val"], C["achats"], "table",
        filter_clause=["!=", field(F_KSV_VAR_PRIX), 0],
        order_by=[["desc", field(F_KSV_VAR_PRIX)]],
        limit=20,
    )
    add_to_dash(D["d7"], [c6, c7])

    # ══════════════════════════════════════════════════════════════════════
    # D8 — Top 10 produits rupture + Jours de rupture/produit
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D8 - Cartes manquantes : Top ruptures, Jours rupture ===")
    c8 = create_card_native(
        "Top 10 produits en rupture", """
SELECT p.PRD_NOM, SUM(r.NB_BOITES_MANQUANTES) AS boites_manquantes
FROM MEDICORE_PROD.MARTS.MART_KPI_RUPTURES r
JOIN MEDICORE_PROD.MARTS.DIM_PRODUIT p ON r.PRODUIT_SK = p.PRODUIT_SK
GROUP BY 1 ORDER BY 2 DESC
LIMIT 10""",
        C["achats"], "bar",
    )
    c9 = create_card_native(
        "Jours de rupture par produit", """
SELECT p.PRD_NOM, SUM(r.NB_JOURS_RUPTURE) AS jours_rupture
FROM MEDICORE_PROD.MARTS.MART_KPI_RUPTURES r
JOIN MEDICORE_PROD.MARTS.DIM_PRODUIT p ON r.PRODUIT_SK = p.PRODUIT_SK
GROUP BY 1 ORDER BY 2 DESC
LIMIT 20""",
        C["achats"], "table",
    )
    add_to_dash(D["d8"], [c8, c9])

    # ══════════════════════════════════════════════════════════════════════
    # D9 — Écoulement par fournisseur
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D9 - Carte manquante : Ecoulement par fournisseur ===")
    c10 = create_card_native(
        "Écoulement par fournisseur", """
SELECT f.FOU_NOM, AVG(e.TAUX_ECOULEMENT) AS taux_ecoulement_moy
FROM MEDICORE_PROD.MARTS.MART_KPI_ECOULEMENT e
JOIN MEDICORE_PROD.MARTS.DIM_FOURNISSEUR f ON e.FOURNISSEUR_SK = f.FOURNISSEUR_SK
GROUP BY 1 ORDER BY 2 DESC
LIMIT 15""",
        C["achats"], "bar",
    )
    add_to_dash(D["d9"], [c10])

    # ══════════════════════════════════════════════════════════════════════
    # D10 — Montant achats par labo + évolution
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D10 - Carte manquante : Montant achats + evolution ===")
    c11 = create_card_mbql(
        "Montant achats par labo + évolution", T["kpi_remise_labo"], C["achats"], "table",
        fields=[field(F_KRL_FOU_NOM), field(F_KRL_MONTANT),
                field(F_KRL_EVOL_MONTANT)],
        order_by=[["desc", field(F_KRL_MONTANT)]],
        limit=20,
    )
    add_to_dash(D["d10"], [c11])

    # ══════════════════════════════════════════════════════════════════════
    # D11 — Dormants par fournisseur
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D11 - Carte manquante : Dormants par fournisseur ===")
    c12 = create_card_mbql(
        "Dormants par fournisseur", T["kpi_dormant"], C["achats"], "bar",
        breakout=[field(F_KD_FOU_NOM)],
        aggregation=[["count"]],
        filter_clause=["=", field(F_KD_DORM6), True],
        order_by=[["desc", ["aggregation", 0]]],
        limit=15,
    )
    add_to_dash(D["d11"], [c12])

    # ══════════════════════════════════════════════════════════════════════
    # D12 — Nb produits par classe (3 scalars)
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D12 - Cartes manquantes : Nb produits A / B / C ===")
    c13 = create_card_mbql(
        "Nb produits classe A", T["kpi_abc"], C["qualite"], "scalar",
        aggregation=[["count"]],
        filter_clause=["=", field(F_KA_CLASSE), "A"],
    )
    c14 = create_card_mbql(
        "Nb produits classe B", T["kpi_abc"], C["qualite"], "scalar",
        aggregation=[["count"]],
        filter_clause=["=", field(F_KA_CLASSE), "B"],
    )
    c15 = create_card_mbql(
        "Nb produits classe C", T["kpi_abc"], C["qualite"], "scalar",
        aggregation=[["count"]],
        filter_clause=["=", field(F_KA_CLASSE), "C"],
    )
    add_to_dash(D["d12"], [c13, c14, c15])

    # ══════════════════════════════════════════════════════════════════════
    # D13 — Marge générique vs princeps
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D13 - Carte manquante : Marge generique vs princeps ===")
    c16 = create_card_native(
        "Marge générique vs princeps", """
SELECT
    CASE WHEN IS_GENERIQUE THEN 'Générique' ELSE 'Princeps' END AS type_produit,
    AVG(TAUX_MARGE) AS taux_marge_moyen,
    SUM(MARGE_BRUTE) AS marge_brute_totale
FROM MEDICORE_PROD.MARTS.MART_KPI_GENERIQUE
GROUP BY 1""",
        C["qualite"], "bar",
    )
    add_to_dash(D["d13"], [c16])

    # ══════════════════════════════════════════════════════════════════════
    # D14 — Nb pharmacies en alerte
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D14 - Carte manquante : Nb pharmacies alerte ===")
    c17 = create_card_mbql(
        "Nb pharmacies en alerte", T["kpi_qualite"], C["qualite"], "scalar",
        aggregation=[["count"]],
        filter_clause=["or",
                       ["=", field(F_KQ_STATUT), "ALERTE"],
                       ["=", field(F_KQ_STATUT), "CRITIQUE"]],
    )
    add_to_dash(D["d14"], [c17])

    # ══════════════════════════════════════════════════════════════════════
    # D15 — Top produits vendus + CA par tranche d'âge
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D15 - Cartes manquantes : Top produits, CA par age ===")
    c18 = create_card_native(
        "Top produits vendus", """
SELECT p.PRD_NOM, SUM(v.FAC_QTE) AS quantite_vendue
FROM MEDICORE_PROD.MARTS.FACT_VENTES v
JOIN MEDICORE_PROD.MARTS.DIM_PRODUIT p ON v.PRODUIT_SK = p.PRODUIT_SK
GROUP BY 1 ORDER BY 2 DESC
LIMIT 20""",
        C["detail"], "bar",
    )
    c19 = create_card_native(
        "CA par tranche d'âge", """
SELECT
    CASE
        WHEN ORD_CLIENT_AGE_MONTHS IS NULL THEN 'Inconnu'
        WHEN ORD_CLIENT_AGE_MONTHS < 216 THEN '0-17 ans'
        WHEN ORD_CLIENT_AGE_MONTHS < 468 THEN '18-38 ans'
        WHEN ORD_CLIENT_AGE_MONTHS < 720 THEN '39-59 ans'
        WHEN ORD_CLIENT_AGE_MONTHS < 960 THEN '60-79 ans'
        ELSE '80+ ans'
    END AS tranche_age,
    SUM(FAC_CA_TTC) AS ca_ttc
FROM MEDICORE_PROD.MARTS.FACT_VENTES
GROUP BY 1 ORDER BY 2 DESC""",
        C["detail"], "bar",
    )
    add_to_dash(D["d15"], [c18, c19])

    # ══════════════════════════════════════════════════════════════════════
    # D16 — Niveau stock après mouvement
    # ══════════════════════════════════════════════════════════════════════
    print("\n=== D16 - Carte manquante : Niveau stock apres mouvement ===")
    c20 = create_card_mbql(
        "Niveau stock après mouvement", T["fact_stock_mouvement"], C["detail"], "line",
        breakout=[field_temporal(F_FSM_DATE, "day")],
        aggregation=[["avg", field(F_FSM_APRES)]],
    )
    add_to_dash(D["d16"], [c20])

    print("\n========================================")
    print("17 cartes manquantes créées avec succès !")
    print("========================================")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python create_missing_cards.py <session_token>")
        sys.exit(1)
    TOKEN = sys.argv[1]
    build_missing_cards()
