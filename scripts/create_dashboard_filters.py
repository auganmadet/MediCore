"""Création des filtres dashboard Metabase pour les 16 dashboards MediCore.

Ajoute les paramètres (pharmacie, mois, produit, fournisseur, etc.)
et les mappe aux cartes MBQL et native SQL.
"""

import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:3000/api"

# ── Field IDs PHARMACIE_SK par table ──────────────────────────────────────
PHARMACIE_SK = {
    25: 301,   # kpi_ca_evolution
    13: 204,   # kpi_tresorerie
    30: 356,   # kpi_marge
    14: 227,   # kpi_operateur
    32: 389,   # kpi_univers
    16: 254,   # kpi_stock
    19: 106,   # kpi_stock_val
    18: 92,    # kpi_ruptures
    9: 155,    # kpi_ecoulement
    34: 439,   # kpi_remise_labo
    17: 73,    # kpi_dormant
    10: 164,   # kpi_abc
    21: 128,   # kpi_generique
    12: 191,   # kpi_qualite
    33: 407,   # kpi_synthese
    27: 328,   # fact_ventes
    29: 347,   # fact_commandes
    23: 265,   # fact_prix_journalier
    28: 340,   # fact_stock_mouvement
    24: 275,   # fact_tresorerie
}

# ── Field IDs MOIS par table ──────────────────────────────────────────────
MOIS = {
    25: 302,   # kpi_ca_evolution
    13: 205,   # kpi_tresorerie
    14: 229,   # kpi_operateur
    16: 256,   # kpi_stock
    19: 108,   # kpi_stock_val
    18: 94,    # kpi_ruptures
    9: 157,    # kpi_ecoulement
    34: 443,   # kpi_remise_labo
    10: 166,   # kpi_abc
    21: 129,   # kpi_generique
    33: 408,   # kpi_synthese
    32: 390,   # kpi_univers
}

# ── Field IDs DATE par table (pour facts sans MOIS) ──────────────────────
DATE_FIELD = {
    30: 358,   # kpi_marge -> DATE_JOUR
    27: 330,   # fact_ventes -> DATE_VENTE
    29: 350,   # fact_commandes -> DATE_COMMANDE
    23: 267,   # fact_prix_journalier -> DATE_PRIX
    28: 342,   # fact_stock_mouvement -> DATE_MOUVEMENT
    24: 276,   # fact_tresorerie -> TRS_DATE
}

# ── Field IDs PRODUIT_SK par table ────────────────────────────────────────
PRODUIT_SK = {
    30: 357,   # kpi_marge
    16: 255,   # kpi_stock
    19: 107,   # kpi_stock_val
    18: 93,    # kpi_ruptures
    9: 156,    # kpi_ecoulement
    10: 165,   # kpi_abc
    27: 329,   # fact_ventes
    29: 348,   # fact_commandes
    23: 266,   # fact_prix_journalier
    28: 341,   # fact_stock_mouvement
}

# ── Field IDs FOURNISSEUR par table ───────────────────────────────────────
FOURNISSEUR = {
    34: 442,   # kpi_remise_labo -> FOU_NOM
    21: 131,   # kpi_generique -> FOU_NOM
    17: 78,    # kpi_dormant -> FOU_NOM
}

# ── Field IDs OPERATEUR par table ─────────────────────────────────────────
OPERATEUR = {
    14: 228,   # kpi_operateur -> OPERATEUR
}

# ── Field IDs UNIVERS par table ───────────────────────────────────────────
UNIVERS = {
    32: 391,   # kpi_univers -> UNIVERS
    21: 133,   # kpi_generique -> UNIVERS
    17: 79,    # kpi_dormant -> UNIVERS
}

# ── Field IDs STATUT_DORMANT par table ────────────────────────────────────
STATUT_DORMANT = {
    17: 88,    # kpi_dormant -> STATUT_DORMANT
}


# ── Dashboard filter definitions ──────────────────────────────────────────
# dash_id: list of (param_id, param_name, param_type, field_map)
DASHBOARD_FILTERS = {
    # D1 - Synthese pharmacie: pharmacie, mois
    2: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("mois", "Mois", "date/month-year", MOIS),
    ],
    # D2 - Evolution CA: pharmacie
    3: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
    ],
    # D3 - Tresorerie: pharmacie, mois
    4: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("mois", "Mois", "date/month-year", MOIS),
    ],
    # D4 - Marge detaillee: pharmacie, date
    5: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("date", "Date", "date/range", DATE_FIELD),
    ],
    # D5 - Performance vendeurs: pharmacie, mois, operateur
    6: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("mois", "Mois", "date/month-year", MOIS),
        ("operateur", "Opérateur", "string/=", OPERATEUR),
    ],
    # D6 - Univers: pharmacie, mois
    7: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("mois", "Mois", "date/month-year", MOIS),
    ],
    # D7 - Stock: pharmacie, mois
    8: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("mois", "Mois", "date/month-year", MOIS),
    ],
    # D8 - Ruptures: pharmacie, mois
    9: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("mois", "Mois", "date/month-year", MOIS),
    ],
    # D9 - Ecoulement: pharmacie, mois
    10: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("mois", "Mois", "date/month-year", MOIS),
    ],
    # D10 - Remises fournisseurs: pharmacie, mois, fournisseur
    11: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("mois", "Mois", "date/month-year", MOIS),
        ("fournisseur", "Fournisseur", "string/=", FOURNISSEUR),
    ],
    # D11 - Dormants: pharmacie, statut_dormant, univers, fournisseur
    12: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("statut_dormant", "Statut dormant", "string/=", STATUT_DORMANT),
        ("univers", "Univers", "string/=", UNIVERS),
        ("fournisseur", "Fournisseur", "string/=", FOURNISSEUR),
    ],
    # D12 - ABC: pharmacie, mois
    13: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("mois", "Mois", "date/month-year", MOIS),
    ],
    # D13 - Generiques: pharmacie, mois, fournisseur, univers
    14: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("mois", "Mois", "date/month-year", MOIS),
        ("fournisseur", "Fournisseur", "string/=", FOURNISSEUR),
        ("univers", "Univers", "string/=", UNIVERS),
    ],
    # D14 - Qualite: aucun filtre
    # D15 - Detail transactions: pharmacie, date
    16: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("date", "Date", "date/range", DATE_FIELD),
    ],
    # D16 - Prix & mouvements: pharmacie, date
    17: [
        ("pharmacie", "Pharmacie", "string/=", PHARMACIE_SK),
        ("date", "Date", "date/range", DATE_FIELD),
    ],
}

# ── Native SQL cards: table name used in FROM clause ──────────────────────
# card_id -> (main_table_column_for_pharmacie, main_table_column_for_mois_or_date)
NATIVE_CARD_COLUMNS = {
    # D1 - kpi_synthese_pharmacie
    348: {"pharmacie": "s.PHARMACIE_SK", "mois": "s.MOIS"},
    349: {"pharmacie": "s.PHARMACIE_SK", "mois": "s.MOIS"},
    350: {"pharmacie": "s.PHARMACIE_SK", "mois": "s.MOIS"},
    351: {"pharmacie": "s.PHARMACIE_SK", "mois": "s.MOIS"},
    352: {"pharmacie": "s.PHARMACIE_SK", "mois": "s.MOIS"},
    353: {"pharmacie": "s.PHARMACIE_SK", "mois": "s.MOIS"},
    354: {"pharmacie": "s.PHARMACIE_SK", "mois": "s.MOIS"},
    355: {"pharmacie": "s.PHARMACIE_SK", "mois": "s.MOIS"},
    356: {"pharmacie": "s.PHARMACIE_SK", "mois": "s.MOIS"},
    # D3 - TVA par taux (fact_tresorerie)
    366: {"pharmacie": "PHARMACIE_SK", "mois": "TRS_DATE"},
    # D4 - Marge (JOINs)
    367: {"pharmacie": "m.PHARMACIE_SK", "date": "m.DATE_JOUR"},
    369: {"pharmacie": "PHARMACIE_SK", "date": "DATE_JOUR"},
    # D6 - Univers
    357: {"pharmacie": "PHARMACIE_SK", "mois": "MOIS"},
    358: {"pharmacie": "PHARMACIE_SK", "mois": "MOIS"},
    359: {"pharmacie": "PHARMACIE_SK", "mois": "MOIS"},
    360: {"pharmacie": "PHARMACIE_SK", "mois": "MOIS"},
    361: {"pharmacie": "PHARMACIE_SK", "mois": "MOIS"},
    # D8 - Ruptures (JOINs)
    373: {"pharmacie": "r.PHARMACIE_SK", "mois": "r.MOIS"},
    374: {"pharmacie": "r.PHARMACIE_SK", "mois": "r.MOIS"},
    # D9 - Ecoulement (JOIN)
    384: {"pharmacie": "e.PHARMACIE_SK", "mois": "e.MOIS"},
    # D10 - Remises (native)
    362: {"pharmacie": "PHARMACIE_SK", "mois": "MOIS", "fournisseur": "FOU_NOM"},
    363: {"pharmacie": "PHARMACIE_SK", "mois": "MOIS", "fournisseur": "FOU_NOM"},
    364: {"pharmacie": "PHARMACIE_SK", "mois": "MOIS", "fournisseur": "FOU_NOM"},
    365: {"pharmacie": "PHARMACIE_SK", "mois": "MOIS", "fournisseur": "FOU_NOM"},
    # D13 - Marge generique (native JOIN)
    402: {"pharmacie": "PHARMACIE_SK", "mois": "MOIS",
          "fournisseur": "FOU_NOM", "univers": "UNIVERS"},
    # D15 - Detail (native JOINs)
    404: {"pharmacie": "v.PHARMACIE_SK", "date": "v.DATE_VENTE"},
    405: {"pharmacie": "PHARMACIE_SK", "date": "DATE_VENTE"},
}


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


def get_card_type(card_data: dict) -> str:
    """Détermine si une carte est MBQL ou native."""
    dq = card_data.get("dataset_query", {})
    stages = dq.get("stages", [])
    if stages:
        stage_type = stages[0].get("lib/type", "")
        if "native" in stage_type:
            return "native"
        return "mbql"
    qtype = dq.get("type", "")
    if qtype == "native":
        return "native"
    return "mbql"


def get_source_table(card_data: dict) -> int:
    """Récupère la source-table d'une carte MBQL."""
    dq = card_data.get("dataset_query", {})
    stages = dq.get("stages", [])
    if stages:
        return stages[0].get("source-table", 0)
    return dq.get("query", {}).get("source-table", 0)


def add_native_filter(card_id: int, param_id: str, column: str) -> bool:
    """Ajoute un filtre template-tag à une carte native SQL."""
    card = api("GET", f"card/{card_id}")
    if not card:
        return False

    dq = card.get("dataset_query", {})
    stages = dq.get("stages", [])

    if not stages or "native" not in stages[0].get("lib/type", ""):
        return False

    sql = stages[0].get("native", "")
    template_tags = stages[0].get("template-tags", {})

    if param_id in template_tags:
        return True

    if param_id in ("mois", "date"):
        tag_type = "date"
        where_clause = f"\n  [[AND {column} = {{{{mois}}}}]]" if param_id == "mois" else f"\n  [[AND {column} = {{{{date}}}}]]"
    else:
        tag_type = "text"
        where_clause = f"\n  [[AND {column} = '{{{{" + param_id + "}}}}'"  + "]]"

    template_tags[param_id] = {
        "name": param_id,
        "display-name": param_id.replace("_", " ").title(),
        "type": tag_type,
    }

    if "WHERE" in sql.upper():
        sql = sql.rstrip() + where_clause
    elif "GROUP BY" in sql.upper():
        idx = sql.upper().index("GROUP BY")
        sql = sql[:idx] + f"WHERE 1=1{where_clause}\n" + sql[idx:]
    elif "ORDER BY" in sql.upper():
        idx = sql.upper().index("ORDER BY")
        sql = sql[:idx] + f"WHERE 1=1{where_clause}\n" + sql[idx:]
    else:
        sql = sql.rstrip() + f"\nWHERE 1=1{where_clause}"

    stages[0]["native"] = sql
    stages[0]["template-tags"] = template_tags

    result = api("PUT", f"card/{card_id}", {"dataset_query": dq})
    if result:
        print(f"    Card {card_id}: ajouté filtre {param_id} sur {column}")
        return True
    return False


def create_filters() -> None:
    """Ajoute les filtres à tous les dashboards."""

    for dash_id, params in DASHBOARD_FILTERS.items():
        dash = api("GET", f"dashboard/{dash_id}")
        if not dash:
            continue
        print(f"\n=== D{dash_id - 1} - {dash['name']} ===")

        parameters = []
        for param_id, param_name, param_type, _ in params:
            parameters.append({
                "id": param_id,
                "name": param_name,
                "slug": param_id,
                "type": param_type,
                "sectionId": "string" if "string" in param_type else "date",
            })

        dashcards = []
        for dc in dash.get("dashcards", []):
            card = dc.get("card", {})
            card_id = card.get("id", 0)
            if not card_id:
                continue

            full_card = api("GET", f"card/{card_id}")
            card_type = get_card_type(full_card)
            source_table = get_source_table(full_card) if card_type == "mbql" else 0

            mappings = []
            for param_id, _, param_type, field_map in params:
                if card_type == "mbql" and source_table in field_map:
                    fid = field_map[source_table]
                    if "date" in param_type:
                        target = ["dimension", ["field", fid,
                                                {"temporal-unit": "month"
                                                 if param_type == "date/month-year"
                                                 else None}]]
                    else:
                        target = ["dimension", ["field", fid, None]]
                    mappings.append({
                        "parameter_id": param_id,
                        "card_id": card_id,
                        "target": target,
                    })
                elif card_type == "native" and card_id in NATIVE_CARD_COLUMNS:
                    cols = NATIVE_CARD_COLUMNS[card_id]
                    if param_id in cols:
                        add_native_filter(card_id, param_id, cols[param_id])
                        mappings.append({
                            "parameter_id": param_id,
                            "card_id": card_id,
                            "target": ["variable", ["template-tag", param_id]],
                        })

            dashcards.append({
                "id": dc["id"],
                "card_id": card_id,
                "row": dc["row"],
                "col": dc["col"],
                "size_x": dc["size_x"],
                "size_y": dc["size_y"],
                "parameter_mappings": mappings,
            })

            if mappings:
                mapped = [m["parameter_id"] for m in mappings]
                print(f"  Card {card_id} ({card_type}): {mapped}")

        result = api("PUT", f"dashboard/{dash_id}", {
            "parameters": parameters,
            "dashcards": dashcards,
        })
        if result:
            n_params = len(parameters)
            n_mapped = sum(1 for dc in dashcards if dc["parameter_mappings"])
            print(f"  => {n_params} filtres, {n_mapped}/{len(dashcards)} cartes mappées")

    print("\n========================================")
    print("Filtres créés avec succès !")
    print("========================================")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python create_dashboard_filters.py <session_token>")
        sys.exit(1)
    TOKEN = sys.argv[1]
    create_filters()
