"""Script de création des 95 cartes Metabase pour les 16 dashboards MediCore.

Créé les questions (saved questions) et les ajoute aux dashboards existants
via l'API Metabase. Nécessite un session token valide.
"""

import json
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:3000/api"
DB_ID = 2  # Snowflake MediCore

# ── Tables MARTS (id Metabase) ──────────────────────────────────────────────
T = {
    "dim_pharmacie": 26,
    "dim_produit": 11,
    "dim_fournisseur": 31,
    "fact_commandes": 29,
    "fact_operateur": 22,
    "fact_prix_journalier": 23,
    "fact_ruptures": 20,
    "fact_stock_mouvement": 28,
    "fact_stock_valorisation": 15,
    "fact_tresorerie": 24,
    "fact_ventes": 27,
    "kpi_abc": 10,
    "kpi_ca_evolution": 25,
    "kpi_dormant": 17,
    "kpi_ecoulement": 9,
    "kpi_generique": 21,
    "kpi_marge": 30,
    "kpi_operateur": 14,
    "kpi_qualite": 12,
    "kpi_ruptures": 18,
    "kpi_stock": 16,
    "kpi_stock_val": 19,
    "kpi_tresorerie": 13,
}

# ── Dashboards (id Metabase) ────────────────────────────────────────────────
D = {
    "d1": 2, "d2": 3, "d3": 4, "d4": 5, "d5": 6, "d6": 7,
    "d7": 8, "d8": 9, "d9": 10, "d10": 11, "d11": 12,
    "d12": 13, "d13": 14, "d14": 15, "d15": 16, "d16": 17,
}

# ── Collections (id Metabase) ───────────────────────────────────────────────
C = {
    "direction": 6,
    "ventes": 7,
    "achats": 8,
    "qualite": 9,
    "detail": 10,
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
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"  ERREUR {e.code}: {err[:200]}")
        return {}


def create_card(
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
    """Créé une question Metabase et retourne son ID."""
    query = {
        "database": DB_ID,
        "type": "query",
        "query": {
            "source-table": table_id,
        }
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


def add_cards_to_dashboard(dash_id: int, card_ids: list) -> None:
    """Ajoute les cartes à un dashboard sur une grille 2 colonnes."""
    cards = []
    for i, cid in enumerate(card_ids):
        if not cid:
            continue
        col = (i % 2) * 9
        row = (i // 2) * 4
        cards.append({
            "id": -1,
            "card_id": cid,
            "row": row,
            "col": col,
            "size_x": 9 if (i % 2 == 0 and i < len(card_ids) - 1) else 18 - col,
            "size_y": 4,
        })
    # Premiere ligne en pleine largeur si nombre impair
    if len(card_ids) % 2 == 1 and cards:
        cards[-1]["size_x"] = 18

    api("PUT", f"dashboard/{dash_id}", {"dashcards": cards})
    print(f"  => {len(cards)} cartes ajoutees au dashboard {dash_id}")


# ── Helpers pour les field refrences ────────────────────────────────────────

def field(fid: int) -> list:
    """Reference a un champ."""
    return ["field", fid, None]


def field_temporal(fid: int, unit: str = "month") -> list:
    """Reference temporelle."""
    return ["field", fid, {"temporal-unit": unit}]


# ── Field IDs (extraits de la metadata) ─────────────────────────────────────
# Notation : F_TABLE_COLUMN = field_id

# kpi_ca_evolution (25)
F_CAE_MOIS = 302
F_CAE_CA_HT = 304
F_CAE_CA_HT_A1 = 308
F_CAE_EVOL = 310
F_CAE_CA_HT_YTD = 311
F_CAE_CA_HT_YTD_A1 = 313
F_CAE_EVOL_YTD = 314
F_CAE_CA_HT_12DM = 315
F_CAE_NB_JOURS = 307

# kpi_tresorerie (13)
F_KT_MOIS = 205
F_KT_CA_TOTAL = 206
F_KT_PANIER = 209
F_KT_NB_FACT = 207
F_KT_PCT_CB = 212
F_KT_PCT_ESP = 210
F_KT_PCT_CHQ = 211
F_KT_PCT_TP = 213
F_KT_PCT_VIR = 214
F_KT_MARGE_REMB = 216
F_KT_MARGE_NREMB = 217
F_KT_RETRO = 224
F_KT_POINTS = 225
F_KT_REMISES = 226

# kpi_marge (30)
F_KM_DATE = 358
F_KM_MARGE = 366
F_KM_TAUX = 367
F_KM_CA_HT = 360
F_KM_PRODUIT_SK = 357

# kpi_operateur (14)
F_KO_MOIS = 229
F_KO_OP = 228
F_KO_CA_TTC = 231
F_KO_PANIER = 235
F_KO_TAUX_MARGE = 238
F_KO_PCT_REMB = 239
F_KO_CLIENTS_JOUR = 236  # ca_moyen_par_jour actually
F_KO_HEURE_PIC = 240
F_KO_CA_MOY_JOUR = 236

# kpi_stock (16)
F_KS_MOIS = 256
F_KS_ROTATION = 263
F_KS_STOCK_MOY = 257
F_KS_QTE_VENDUE = 262
F_KS_TAUX_RUPT = 264

# kpi_stock_val (19)
F_KSV_MOIS = 108
F_KSV_PA_FIN = 110
F_KSV_PV_FIN = 111
F_KSV_COUV = 116
F_KSV_MARGE_LAT = 115
F_KSV_VAR_PRIX = 117

# kpi_ruptures (18)
F_KR_MOIS = 94
F_KR_CA_PERDU = 104
F_KR_MARGE_PERDUE = 105
F_KR_CLIENTS = 97
F_KR_BOITES = 96
F_KR_TAUX = 103
F_KR_JOURS = 99
F_KR_PRODUIT_SK = 93

# kpi_ecoulement (9)
F_KE_MOIS = 157
F_KE_TAUX = 163
F_KE_QTE_CMD = 158
F_KE_QTE_VENDU = 161

# kpi_dormant (17)
F_KD_PRD_NOM = 76
F_KD_FOU_NOM = 78
F_KD_QTE = 81
F_KD_VAL_PA = 82
F_KD_JOURS = 87
F_KD_STATUT = 88
F_KD_DORM6 = 89
F_KD_UNIVERS = 79
F_KD_MARGE_BLQ = 91

# kpi_abc (10)
F_KA_MOIS = 166
F_KA_RANG = 167
F_KA_CA = 168
F_KA_CLASSE = 175
F_KA_PCT_CA = 173
F_KA_PCT_CUM = 174
F_KA_PRODUIT_SK = 165

# kpi_generique (21)
F_KG_MOIS = 129
F_KG_FOU_NOM = 131
F_KG_IS_GEN = 132
F_KG_CA_HT = 134
F_KG_PDM = 138
F_KG_TAUX_GEN = 141
F_KG_EVOL = 143
F_KG_NB_PROD = 137
F_KG_CA_A1 = 142

# kpi_qualite (12)
F_KQ_PHA_NOM = 192
F_KQ_SYNC = 193
F_KQ_HEURES = 194
F_KQ_STATUT = 195
F_KQ_TAUX_OK = 200
F_KQ_NB_ALERTE = 198
F_KQ_NB_CRIT = 199
F_KQ_NB_ERR = 201
F_KQ_DERN_ERR = 203

# fact_ventes (27)
F_FV_DATE = 330
F_FV_CA_HT = 332
F_FV_QTE = 331
F_FV_CA_TTC = 333
F_FV_AGE = 336
F_FV_SEX = 337
F_FV_PRODUIT_SK = 329

# fact_commandes (29)
F_FC_DATE = 350
F_FC_MONTANT = 353
F_FC_FOUR_SK = 349

# fact_prix_journalier (23)
F_FP_DATE = 267
F_FP_TARIF = 268
F_FP_PUBLIC = 269
F_FP_ACHAT_NET = 271
F_FP_MARGE_U = 272

# fact_stock_mouvement (28)
F_FSM_DATE = 342
F_FSM_DELTA = 343
F_FSM_APRES = 344
F_FSM_TYPE = 345

# fact_tresorerie (24)
F_FT_DATE = 276
F_FT_TVA1 = 293
F_FT_TVA2 = 294
F_FT_TVA3 = 295
F_FT_TVA4 = 296
F_FT_TVA5 = 297

# dim_produit (11)
F_DP_NOM = 179
F_DP_UNIVERS = 189
F_DP_PRODUIT_SK = 176

# dim_fournisseur (31)
F_DF_NOM = 371
F_DF_FOUR_SK = 368


def build_dashboards() -> None:
    """Construit les 16 dashboards avec leurs cartes."""

    # ════════════════════════════════════════════════════════════════════════
    # D2 — Evolution CA
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D2 - Evolution CA ===")
    coll = C["direction"]
    tid = T["kpi_ca_evolution"]
    cards = []

    cards.append(create_card(
        "CA mensuel N vs N-1", tid, coll, "line",
        breakout=[field_temporal(F_CAE_MOIS)],
        aggregation=[["avg", field(F_CAE_CA_HT)], ["avg", field(F_CAE_CA_HT_A1)]],
    ))
    cards.append(create_card(
        "Evolution YoY par mois", tid, coll, "bar",
        breakout=[field_temporal(F_CAE_MOIS)],
        aggregation=[["avg", field(F_CAE_EVOL)]],
    ))
    cards.append(create_card(
        "CA YTD cumule N vs N-1", tid, coll, "area",
        breakout=[field_temporal(F_CAE_MOIS)],
        aggregation=[["avg", field(F_CAE_CA_HT_YTD)], ["avg", field(F_CAE_CA_HT_YTD_A1)]],
    ))
    cards.append(create_card(
        "CA 12DM tendance lissee", tid, coll, "line",
        breakout=[field_temporal(F_CAE_MOIS)],
        aggregation=[["avg", field(F_CAE_CA_HT_12DM)]],
    ))
    cards.append(create_card(
        "Jours de vente par mois", tid, coll, "bar",
        breakout=[field_temporal(F_CAE_MOIS)],
        aggregation=[["avg", field(F_CAE_NB_JOURS)]],
    ))
    add_cards_to_dashboard(D["d2"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D3 — Trésorerie
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D3 - Tresorerie ===")
    coll = C["direction"]
    tid = T["kpi_tresorerie"]
    cards = []

    cards.append(create_card(
        "CA total mensuel", tid, coll, "scalar",
        aggregation=[["sum", field(F_KT_CA_TOTAL)]],
    ))
    cards.append(create_card(
        "Panier moyen", tid, coll, "scalar",
        aggregation=[["avg", field(F_KT_PANIER)]],
    ))
    cards.append(create_card(
        "Nb factures", tid, coll, "scalar",
        aggregation=[["sum", field(F_KT_NB_FACT)]],
    ))
    cards.append(create_card(
        "Repartition modes de paiement", tid, coll, "pie",
        fields=[field(F_KT_PCT_CB), field(F_KT_PCT_ESP), field(F_KT_PCT_CHQ),
                field(F_KT_PCT_TP), field(F_KT_PCT_VIR)],
    ))
    cards.append(create_card(
        "Marge remb. vs non-remb.", tid, coll, "bar",
        breakout=[field_temporal(F_KT_MOIS)],
        aggregation=[["sum", field(F_KT_MARGE_REMB)], ["sum", field(F_KT_MARGE_NREMB)]],
    ))
    cards.append(create_card(
        "Retrocessions", tid, coll, "line",
        breakout=[field_temporal(F_KT_MOIS)],
        aggregation=[["sum", field(F_KT_RETRO)]],
    ))
    cards.append(create_card(
        "Points fidelite", tid, coll, "scalar",
        aggregation=[["sum", field(F_KT_POINTS)]],
    ))
    cards.append(create_card(
        "Remises totales", tid, coll, "scalar",
        aggregation=[["sum", field(F_KT_REMISES)]],
    ))
    add_cards_to_dashboard(D["d3"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D4 — Marge détaillée
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D4 - Marge detaillee ===")
    coll = C["ventes"]
    tid = T["kpi_marge"]
    cards = []

    cards.append(create_card(
        "Marge brute par jour", tid, coll, "line",
        breakout=[field_temporal(F_KM_DATE, "day")],
        aggregation=[["sum", field(F_KM_MARGE)]],
    ))
    cards.append(create_card(
        "Distribution taux de marge", tid, coll, "bar",
        breakout=[["binning-strategy", field(F_KM_TAUX)[1], field(F_KM_TAUX)[2], "default"]],
        aggregation=[["count"]],
    ))
    cards.append(create_card(
        "Marges negatives", tid, coll, "table",
        filter_clause=["<", field(F_KM_TAUX), 0],
        order_by=[["asc", field(F_KM_TAUX)]],
        limit=20,
    ))
    add_cards_to_dashboard(D["d4"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D5 — Performance vendeurs
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D5 - Performance vendeurs ===")
    coll = C["ventes"]
    tid = T["kpi_operateur"]
    cards = []

    cards.append(create_card(
        "CA par operateur", tid, coll, "bar",
        breakout=[field(F_KO_OP)],
        aggregation=[["sum", field(F_KO_CA_TTC)]],
    ))
    cards.append(create_card(
        "Panier moyen par operateur", tid, coll, "bar",
        breakout=[field(F_KO_OP)],
        aggregation=[["avg", field(F_KO_PANIER)]],
    ))
    cards.append(create_card(
        "Taux de marge par operateur", tid, coll, "bar",
        breakout=[field(F_KO_OP)],
        aggregation=[["avg", field(F_KO_TAUX_MARGE)]],
    ))
    cards.append(create_card(
        "% lignes remboursables", tid, coll, "bar",
        breakout=[field(F_KO_OP)],
        aggregation=[["avg", field(F_KO_PCT_REMB)]],
    ))
    cards.append(create_card(
        "Productivite CA moyen par jour", tid, coll, "bar",
        breakout=[field(F_KO_OP)],
        aggregation=[["avg", field(F_KO_CA_MOY_JOUR)]],
    ))
    cards.append(create_card(
        "Heure de pic CA par operateur", tid, coll, "table",
        fields=[field(F_KO_OP), field(F_KO_HEURE_PIC)],
    ))
    add_cards_to_dashboard(D["d5"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D7 — Stock & rotation
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D7 - Stock & rotation ===")
    coll = C["achats"]
    cards = []

    cards.append(create_card(
        "Rotation stock mensuelle", T["kpi_stock"], coll, "line",
        breakout=[field_temporal(F_KS_MOIS)],
        aggregation=[["avg", field(F_KS_ROTATION)]],
    ))
    cards.append(create_card(
        "Taux de rupture stock", T["kpi_stock"], coll, "line",
        breakout=[field_temporal(F_KS_MOIS)],
        aggregation=[["avg", field(F_KS_TAUX_RUPT)]],
    ))
    cards.append(create_card(
        "Valorisation stock PA fin mois", T["kpi_stock_val"], coll, "line",
        breakout=[field_temporal(F_KSV_MOIS)],
        aggregation=[["sum", field(F_KSV_PA_FIN)]],
    ))
    cards.append(create_card(
        "Couverture stock en jours", T["kpi_stock_val"], coll, "line",
        breakout=[field_temporal(F_KSV_MOIS)],
        aggregation=[["avg", field(F_KSV_COUV)]],
    ))
    cards.append(create_card(
        "Marge latente moyenne", T["kpi_stock_val"], coll, "scalar",
        aggregation=[["avg", field(F_KSV_MARGE_LAT)]],
    ))
    add_cards_to_dashboard(D["d7"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D8 — Ruptures & CA perdu
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D8 - Ruptures & CA perdu ===")
    coll = C["achats"]
    tid = T["kpi_ruptures"]
    cards = []

    cards.append(create_card(
        "CA estime perdu par mois", tid, coll, "bar",
        breakout=[field_temporal(F_KR_MOIS)],
        aggregation=[["sum", field(F_KR_CA_PERDU)]],
    ))
    cards.append(create_card(
        "Marge estimee perdue", tid, coll, "line",
        breakout=[field_temporal(F_KR_MOIS)],
        aggregation=[["sum", field(F_KR_MARGE_PERDUE)]],
    ))
    cards.append(create_card(
        "Clients impactes par mois", tid, coll, "line",
        breakout=[field_temporal(F_KR_MOIS)],
        aggregation=[["sum", field(F_KR_CLIENTS)]],
    ))
    cards.append(create_card(
        "Taux de rupture demande", tid, coll, "line",
        breakout=[field_temporal(F_KR_MOIS)],
        aggregation=[["avg", field(F_KR_TAUX)]],
    ))
    add_cards_to_dashboard(D["d8"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D9 — Ecoulement
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D9 - Ecoulement ===")
    coll = C["achats"]
    tid = T["kpi_ecoulement"]
    cards = []

    cards.append(create_card(
        "Taux ecoulement mensuel", tid, coll, "line",
        breakout=[field_temporal(F_KE_MOIS)],
        aggregation=[["avg", field(F_KE_TAUX)]],
    ))
    cards.append(create_card(
        "Commande vs vendu par mois", tid, coll, "bar",
        breakout=[field_temporal(F_KE_MOIS)],
        aggregation=[["sum", field(F_KE_QTE_CMD)], ["sum", field(F_KE_QTE_VENDU)]],
    ))
    cards.append(create_card(
        "Produits sur-stockes (taux < 50%)", tid, coll, "table",
        filter_clause=["<", field(F_KE_TAUX), 0.5],
        order_by=[["asc", field(F_KE_TAUX)]],
        limit=20,
    ))
    add_cards_to_dashboard(D["d9"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D11 — Produits dormants
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D11 - Produits dormants ===")
    coll = C["achats"]
    tid = T["kpi_dormant"]
    cards = []

    cards.append(create_card(
        "Capital immobilise (dormants 6m)", tid, coll, "scalar",
        aggregation=[["sum", field(F_KD_VAL_PA)]],
        filter_clause=["=", field(F_KD_DORM6), True],
    ))
    cards.append(create_card(
        "Nb produits dormants 6m", tid, coll, "scalar",
        aggregation=[["count"]],
        filter_clause=["=", field(F_KD_DORM6), True],
    ))
    cards.append(create_card(
        "Marge latente bloquee", tid, coll, "scalar",
        aggregation=[["sum", field(F_KD_MARGE_BLQ)]],
        filter_clause=["=", field(F_KD_DORM6), True],
    ))
    cards.append(create_card(
        "Repartition par statut dormant", tid, coll, "pie",
        breakout=[field(F_KD_STATUT)],
        aggregation=[["count"]],
    ))
    cards.append(create_card(
        "Dormants par univers", tid, coll, "bar",
        breakout=[field(F_KD_UNIVERS)],
        aggregation=[["count"]],
        filter_clause=["=", field(F_KD_DORM6), True],
    ))
    cards.append(create_card(
        "Top 20 dormants par valeur", tid, coll, "table",
        fields=[field(F_KD_PRD_NOM), field(F_KD_FOU_NOM), field(F_KD_QTE),
                field(F_KD_VAL_PA), field(F_KD_JOURS), field(F_KD_STATUT)],
        filter_clause=["=", field(F_KD_DORM6), True],
        order_by=[["desc", field(F_KD_VAL_PA)]],
        limit=20,
    ))
    add_cards_to_dashboard(D["d11"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D12 — Classification ABC
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D12 - Classification ABC ===")
    coll = C["qualite"]
    tid = T["kpi_abc"]
    cards = []

    cards.append(create_card(
        "Repartition A / B / C", tid, coll, "pie",
        breakout=[field(F_KA_CLASSE)],
        aggregation=[["count"]],
    ))
    cards.append(create_card(
        "CA par classe ABC", tid, coll, "bar",
        breakout=[field(F_KA_CLASSE)],
        aggregation=[["sum", field(F_KA_CA)]],
    ))
    cards.append(create_card(
        "Courbe de Pareto (% CA cumule)", tid, coll, "line",
        breakout=[field(F_KA_RANG)],
        aggregation=[["avg", field(F_KA_PCT_CUM)]],
    ))
    cards.append(create_card(
        "Top 10 produits A", tid, coll, "table",
        fields=[field(F_KA_RANG), field(F_KA_PRODUIT_SK), field(F_KA_CA),
                field(F_KA_PCT_CA), field(F_KA_PCT_CUM)],
        filter_clause=["=", field(F_KA_CLASSE), "A"],
        order_by=[["asc", field(F_KA_RANG)]],
        limit=10,
    ))
    add_cards_to_dashboard(D["d12"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D13 — Génériques & labos
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D13 - Generiques & labos ===")
    coll = C["qualite"]
    tid = T["kpi_generique"]
    cards = []

    cards.append(create_card(
        "Taux generique pharmacie", tid, coll, "scalar",
        aggregation=[["avg", field(F_KG_TAUX_GEN)]],
    ))
    cards.append(create_card(
        "CA generique vs princeps", tid, coll, "bar",
        breakout=[field(F_KG_IS_GEN)],
        aggregation=[["sum", field(F_KG_CA_HT)]],
    ))
    cards.append(create_card(
        "PDM par labo (top 15)", tid, coll, "bar",
        breakout=[field(F_KG_FOU_NOM)],
        aggregation=[["avg", field(F_KG_PDM)]],
        order_by=[["desc", ["aggregation", 0]]],
        limit=15,
    ))
    cards.append(create_card(
        "Nb produits par labo", tid, coll, "bar",
        breakout=[field(F_KG_FOU_NOM)],
        aggregation=[["sum", field(F_KG_NB_PROD)]],
        order_by=[["desc", ["aggregation", 0]]],
        limit=15,
    ))
    cards.append(create_card(
        "Evolution CA par labo vs A-1", tid, coll, "table",
        fields=[field(F_KG_FOU_NOM), field(F_KG_CA_HT), field(F_KG_CA_A1), field(F_KG_EVOL)],
        limit=20,
    ))
    add_cards_to_dashboard(D["d13"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D14 — Qualité des données
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D14 - Qualite des donnees ===")
    coll = C["qualite"]
    tid = T["kpi_qualite"]
    cards = []

    cards.append(create_card(
        "Taux pharmacies OK", tid, coll, "scalar",
        aggregation=[["avg", field(F_KQ_TAUX_OK)]],
    ))
    cards.append(create_card(
        "Nb erreurs total", tid, coll, "scalar",
        aggregation=[["sum", field(F_KQ_NB_ERR)]],
    ))
    cards.append(create_card(
        "Repartition OK / Alerte / Critique", tid, coll, "pie",
        breakout=[field(F_KQ_STATUT)],
        aggregation=[["count"]],
    ))
    cards.append(create_card(
        "Fraicheur par pharmacie", tid, coll, "table",
        fields=[field(F_KQ_PHA_NOM), field(F_KQ_SYNC), field(F_KQ_HEURES), field(F_KQ_STATUT)],
        order_by=[["desc", field(F_KQ_HEURES)]],
    ))
    cards.append(create_card(
        "Erreurs recentes", tid, coll, "table",
        fields=[field(F_KQ_PHA_NOM), field(F_KQ_NB_ERR), field(F_KQ_DERN_ERR)],
        filter_clause=[">", field(F_KQ_NB_ERR), 0],
        order_by=[["desc", field(F_KQ_NB_ERR)]],
    ))
    add_cards_to_dashboard(D["d14"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D15 — Détail transactions
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D15 - Detail transactions ===")
    coll = C["detail"]
    cards = []

    cards.append(create_card(
        "Ventes par jour", T["fact_ventes"], coll, "line",
        breakout=[field_temporal(F_FV_DATE, "day")],
        aggregation=[["sum", field(F_FV_CA_HT)]],
    ))
    cards.append(create_card(
        "CA par tranche d age", T["fact_ventes"], coll, "bar",
        breakout=[["binning-strategy", F_FV_AGE, None, "default"]],
        aggregation=[["sum", field(F_FV_CA_TTC)]],
    ))
    cards.append(create_card(
        "Ventes par sexe", T["fact_ventes"], coll, "pie",
        breakout=[field(F_FV_SEX)],
        aggregation=[["sum", field(F_FV_CA_TTC)]],
    ))
    cards.append(create_card(
        "Commandes par fournisseur", T["fact_commandes"], coll, "bar",
        breakout=[field(F_FC_FOUR_SK)],
        aggregation=[["sum", field(F_FC_MONTANT)]],
        order_by=[["desc", ["aggregation", 0]]],
        limit=15,
    ))
    add_cards_to_dashboard(D["d15"], cards)

    # ════════════════════════════════════════════════════════════════════════
    # D16 — Prix & mouvements stock
    # ════════════════════════════════════════════════════════════════════════
    print("\n=== D16 - Prix & mouvements stock ===")
    coll = C["detail"]
    cards = []

    cards.append(create_card(
        "Evolution prix (tarif, public, achat net)", T["fact_prix_journalier"], coll, "line",
        breakout=[field_temporal(F_FP_DATE, "day")],
        aggregation=[["avg", field(F_FP_TARIF)], ["avg", field(F_FP_PUBLIC)],
                     ["avg", field(F_FP_ACHAT_NET)]],
    ))
    cards.append(create_card(
        "Marge brute unitaire", T["fact_prix_journalier"], coll, "line",
        breakout=[field_temporal(F_FP_DATE, "day")],
        aggregation=[["avg", field(F_FP_MARGE_U)]],
    ))
    cards.append(create_card(
        "Mouvements stock par jour", T["fact_stock_mouvement"], coll, "bar",
        breakout=[field_temporal(F_FSM_DATE, "day")],
        aggregation=[["sum", field(F_FSM_DELTA)]],
    ))
    cards.append(create_card(
        "Type operation stock", T["fact_stock_mouvement"], coll, "pie",
        breakout=[field(F_FSM_TYPE)],
        aggregation=[["count"]],
    ))
    add_cards_to_dashboard(D["d16"], cards)

    print("\n========================================")
    print("16 dashboards crees avec succes !")
    print("========================================")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python create_metabase_dashboards.py <session_token>")
        sys.exit(1)
    TOKEN = sys.argv[1]
    build_dashboards()
