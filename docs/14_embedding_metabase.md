# Embedding Metabase — Guide d'intégration pour Mediprix

## Table des matières

1. [Objectif](#objectif)
2. [Architecture](#architecture)
3. [Prérequis](#prérequis)
4. [Configuration Metabase](#configuration-metabase)
5. [Fonction d'intégration](#fonction-dintégration)
6. [Snippet HTML](#snippet-html)
7. [Mapping des dashboards](#mapping-des-dashboards)
8. [Mapping pharmacie_sk](#mapping-pharmacie_sk)
9. [Paramètres des filtres](#paramètres-des-filtres)
10. [Mini-app de test](#mini-app-de-test)
11. [Sécurité](#sécurité)
12. [Dépannage](#dépannage)

---

## Objectif

Permettre à l'application Mediprix d'afficher les 16 dashboards MediCore BI dans des iframes avec le filtre pharmacie **verrouillé** par un JWT (JSON Web Token). Chaque pharmacien ne voit que les données de sa pharmacie.

[↑ Retour au sommaire](#table-des-matières)

---

## Architecture

```
Application Mediprix
  │
  ├── 1. Le pharmacien se connecte (authentification Mediprix)
  │
  ├── 2. Mediprix connaît le PHA_ID du pharmacien connecté
  │
  ├── 3. Mediprix génère un JWT signé avec :
  │        - dashboard_id (ex: 2 pour D1)
  │        - pharmacie_sk = MD5(PHA_ID) → VERROUILLÉ
  │
  ├── 4. Mediprix affiche le dashboard via le Web Component Metabase :
  │        <metabase-dashboard token="<JWT>"></metabase-dashboard>
  │
  └── 5. Metabase vérifie la signature JWT et applique les filtres
           → Le pharmacien ne voit que ses données
           → Il ne peut PAS modifier le filtre pharmacie
           → Il PEUT modifier le filtre Mois
```

[↑ Retour au sommaire](#table-des-matières)

---

## Prérequis

  ┌──────────────────────────────────┬──────────────────────────────────────────────────┐
  │ Élément                          │ Détail                                           │
  ├──────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Metabase                         │ v0.58+ avec signed embedding activé              │
  ├──────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Clé secrète                      │ Dans .env : METABASE_EMBEDDING_SECRET_KEY        │
  ├──────────────────────────────────┼──────────────────────────────────────────────────┤
  │ URL Metabase                     │ Accessible depuis le navigateur du pharmacien    │
  │                                  │ (ex: http://192.168.0.37:3001)                   │
  ├──────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Bibliothèque JWT                 │ PyJWT (Python) ou jsonwebtoken (Node.js)         │
  │                                  │ ou équivalent dans le langage de Mediprix        │
  ├──────────────────────────────────┼──────────────────────────────────────────────────┤
  │ PHA_ID du pharmacien             │ Mediprix doit connaître le PHA_ID du user        │
  │                                  │ connecté (depuis sa propre base de données)      │
  └──────────────────────────────────┴──────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Configuration Metabase

L'embedding signé est déjà activé et configuré sur les 16 dashboards. Chaque dashboard a les paramètres suivants :

  ┌──────────────────┬──────────────────────────────────────────────────────────┐
  │ Paramètre        │ Configuration                                            │
  ├──────────────────┼──────────────────────────────────────────────────────────┤
  │ pharmacie        │ LOCKED — défini par le JWT, non modifiable par le user   │
  ├──────────────────┼──────────────────────────────────────────────────────────┤
  │ mois             │ EDITABLE — le pharmacien peut changer le mois affiché    │
  ├──────────────────┼──────────────────────────────────────────────────────────┤
  │ univers          │ EDITABLE — le pharmacien peut filtrer par univers        │
  ├──────────────────┼──────────────────────────────────────────────────────────┤
  │ fournisseur      │ EDITABLE — le pharmacien peut filtrer par fournisseur    │
  ├──────────────────┼──────────────────────────────────────────────────────────┤
  │ operateur        │ EDITABLE — le pharmacien peut filtrer par opérateur      │
  ├──────────────────┼──────────────────────────────────────────────────────────┤
  │ statut_dormant   │ EDITABLE — le pharmacien peut filtrer par statut         │
  └──────────────────┴──────────────────────────────────────────────────────────┘

Si un nouveau dashboard est créé, activer l'embedding via :

```bash
python scripts/enable_embedding.py <token>
```

[↑ Retour au sommaire](#table-des-matières)

---

## Fonction d'intégration

C'est la seule fonction que Mediprix doit intégrer dans son backend. Elle génère le JWT signé pour un dashboard et une pharmacie donnés.

### Python

```python
import hashlib
import time
import jwt  # pip install PyJWT

METABASE_SECRET_KEY = "6bb88d0ecf2a8e8a45d60d04adda4ea87ab3cd50e809fa2d9ce1ae45b06f150c"


def generate_embed_token(dashboard_id: int, pha_id: int) -> str:
    """Génère le JWT d'embedding Metabase avec filtre pharmacie verrouillé.

    Args:
        dashboard_id: ID du dashboard Metabase (voir mapping ci-dessous)
        pha_id: PHA_ID de la pharmacie du pharmacien connecté

    Returns:
        Token JWT signé (str)
    """
    pharmacie_sk = hashlib.md5(str(pha_id).encode()).hexdigest()

    payload = {
        "resource": {"dashboard": dashboard_id},
        "params": {
            "pharmacie": [pharmacie_sk],
        },
        "exp": int(time.time()) + 600,  # expire dans 10 minutes
        "_embedding_params": {
            "pharmacie": "locked",
            "mois": "enabled",
            "univers": "enabled",
            "fournisseur": "enabled",
            "operateur": "enabled",
            "statut_dormant": "enabled",
        },
    }

    return jwt.encode(payload, METABASE_SECRET_KEY, algorithm="HS256")
```

### JavaScript / Node.js

```javascript
const jwt = require('jsonwebtoken');
const crypto = require('crypto');

const METABASE_SECRET_KEY = "6bb88d0ecf2a8e8a45d60d04adda4ea87ab3cd50e809fa2d9ce1ae45b06f150c";

function generateEmbedToken(dashboardId, phaId) {
    const pharmacieSk = crypto.createHash('md5').update(String(phaId)).digest('hex');

    const payload = {
        resource: { dashboard: dashboardId },
        params: {
            pharmacie: [pharmacieSk],
        },
        exp: Math.floor(Date.now() / 1000) + 600,
        _embedding_params: {
            pharmacie: "locked",
            mois: "enabled",
            univers: "enabled",
            fournisseur: "enabled",
            operateur: "enabled",
            statut_dormant: "enabled",
        },
    };

    return jwt.sign(payload, METABASE_SECRET_KEY, { algorithm: "HS256" });
}
```

[↑ Retour au sommaire](#table-des-matières)

---

## Snippet HTML

Le dashboard est affiché via le Web Component Metabase (pas un iframe classique) :

```html
<!-- Charger le SDK Metabase (une seule fois par page) -->
<script defer src="http://192.168.0.37:3001/app/embed.js"></script>
<script>
  window.metabaseConfig = {
    theme: { preset: "light" },
    isGuest: true,
    instanceUrl: "http://192.168.0.37:3001"
  };
</script>

<!-- Afficher un dashboard (le token est généré par le backend) -->
<metabase-dashboard
  token="<JWT_TOKEN>"
  with-title="true"
  with-downloads="true"
></metabase-dashboard>
```

**Important** : le `token` doit être généré côté serveur (backend Mediprix), jamais côté client. La clé secrète ne doit jamais être exposée dans le JavaScript du navigateur.

[↑ Retour au sommaire](#table-des-matières)

---

## Mapping des dashboards

  ┌──────────────────┬─────────────────────────────────────┐
  │ dashboard_id     │ Nom                                 │
  ├──────────────────┼─────────────────────────────────────┤
  │ 2                │ D1 - Synthèse pharmacie             │
  ├──────────────────┼─────────────────────────────────────┤
  │ 3                │ D2 - Évolution CA                   │
  ├──────────────────┼─────────────────────────────────────┤
  │ 4                │ D3 - Trésorerie                     │
  ├──────────────────┼─────────────────────────────────────┤
  │ 5                │ D4 - Marge détaillée                │
  ├──────────────────┼─────────────────────────────────────┤
  │ 6                │ D5 - Performance vendeurs           │
  ├──────────────────┼─────────────────────────────────────┤
  │ 7                │ D6 - Univers RX OTC PARA            │
  ├──────────────────┼─────────────────────────────────────┤
  │ 8                │ D7 - Stock et rotation              │
  ├──────────────────┼─────────────────────────────────────┤
  │ 9                │ D8 - Ruptures et CA perdu           │
  ├──────────────────┼─────────────────────────────────────┤
  │ 10               │ D9 - Écoulement                     │
  ├──────────────────┼─────────────────────────────────────┤
  │ 11               │ D10 - Remises fournisseurs          │
  ├──────────────────┼─────────────────────────────────────┤
  │ 12               │ D11 - Produits dormants             │
  ├──────────────────┼─────────────────────────────────────┤
  │ 13               │ D12 - Classification ABC            │
  ├──────────────────┼─────────────────────────────────────┤
  │ 14               │ D13 - Génériques et labos           │
  ├──────────────────┼─────────────────────────────────────┤
  │ 15               │ D14 - Qualité des données           │
  ├──────────────────┼─────────────────────────────────────┤
  │ 16               │ D15 - Détail transactions           │
  ├──────────────────┼─────────────────────────────────────┤
  │ 17               │ D16 - Prix et mouvements stock      │
  └──────────────────┴─────────────────────────────────────┘

**Exception** : D14 (Qualité des données) n'a pas de filtre pharmacie — c'est un dashboard global. Le JWT pour D14 ne doit pas contenir le paramètre `pharmacie`.

[↑ Retour au sommaire](#table-des-matières)

---

## Mapping pharmacie_sk

Le filtre pharmacie utilise `pharmacie_sk` (hash MD5 de PHA_ID), pas PHA_ID directement.

```
pharmacie_sk = MD5(str(pha_id))
```

Exemples :

  ┌──────────┬────────────────────────────────────┐
  │ PHA_ID   │ pharmacie_sk                       │
  ├──────────┼────────────────────────────────────┤
  │ 217      │ 8c19f571e251e61cb8dd3612f26d5ecf   │
  ├──────────┼────────────────────────────────────┤
  │ 5372     │ e7a0ac723159df05cb1edaa7683e1a53   │
  ├──────────┼────────────────────────────────────┤
  │ 13973    │ 301af7614f87909bb1649e27087db4af   │
  └──────────┴────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Paramètres des filtres

Le JWT contient un champ `_embedding_params` qui définit quels filtres sont verrouillés ou éditables :

```json
{
  "_embedding_params": {
    "pharmacie": "locked",
    "mois": "enabled",
    "univers": "enabled",
    "fournisseur": "enabled",
    "operateur": "enabled",
    "statut_dormant": "enabled"
  }
}
```

  ┌───────────────────┬──────────────────────────────────────────────────────────┐
  │ Valeur            │ Comportement                                             │
  ├───────────────────┼──────────────────────────────────────────────────────────┤
  │ locked            │ Valeur définie dans params, non modifiable par le user   │
  ├───────────────────┼──────────────────────────────────────────────────────────┤
  │ enabled           │ Filtre visible et modifiable par le user                 │
  ├───────────────────┼──────────────────────────────────────────────────────────┤
  │ disabled          │ Filtre masqué (non affiché)                              │
  └───────────────────┴──────────────────────────────────────────────────────────┘

Tous les dashboards n'ont pas tous les filtres. Seuls les filtres existants sur le dashboard doivent apparaître dans `_embedding_params`. Les filtres non listés sont ignorés par Metabase.

[↑ Retour au sommaire](#table-des-matières)

---

## Mini-app de test

Une mini-app Flask est disponible dans `embed_app/` pour tester l'embedding avant intégration dans Mediprix :

```bash
cd embed_app
python -m pip install -r requirements.txt
python app.py
```

Accessible sur `http://localhost:5000`. Permet de sélectionner une pharmacie et naviguer entre les 16 dashboards.

**Cette mini-app est un outil de test**, pas un livrable de production. Mediprix doit intégrer uniquement la fonction `generate_embed_token()` dans son propre backend.

[↑ Retour au sommaire](#table-des-matières)

---

## Sécurité

  ┌─────────────────────────────────────┬──────────────────────────────────────────────────┐
  │ Risque                              │ Protection                                       │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Pharmacien modifie le filtre        │ LOCKED par JWT — le filtre est signé, toute      │
  │ pharmacie                           │ modification invalide la signature               │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Pharmacien forge un JWT             │ Impossible sans la clé secrète (connue           │
  │                                     │ uniquement du backend Mediprix)                  │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Pharmacien accède directement       │ Metabase n'autorise pas l'accès direct aux       │
  │ à Metabase                          │ dashboards embedded sans JWT valide              │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Pharmacien modifie un dashboard     │ Impossible en mode embedding — pas d'UI          │
  │                                     │ Metabase, pas de mode édition                    │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Pharmacien exécute du SQL           │ Impossible — l'embedding n'expose pas le         │
  │                                     │ query builder ni le SQL natif                    │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Token JWT volé                      │ Expire après 10 minutes (configurable)           │
  │                                     │ et ne donne accès qu'à une seule pharmacie       │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Clé secrète compromise              │ Régénérer dans Metabase Admin → Paramètres →     │
  │                                     │ Embedding. Mettre à jour .env et le backend      │
  │                                     │ Mediprix                                         │
  └─────────────────────────────────────┴──────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Dépannage

  ┌──────────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Problème                             │ Solution                                                 │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Iframe affiche un écran blanc        │ Vérifier que l'embedding est activé sur le dashboard :   │
  │                                      │ `python scripts/enable_embedding.py <token>`             │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Erreur "Token is not valid"          │ Vérifier que METABASE_EMBEDDING_SECRET_KEY dans .env     │
  │                                      │ correspond à la clé dans Metabase Admin                  │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Carte affiche triangle jaune         │ Voir `docs/15_metabase_checklist_depannage.md`           │
  │                                      │ Lancer : `python scripts/metabase_maintenance.py`        │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Filtre pharmacie visible et          │ Vérifier que le paramètre "pharmacie" est bien           │
  │ modifiable                           │ "locked" dans embedding_params du dashboard              │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Metabase non accessible depuis       │ Vérifier le pare-feu Windows : port 3000 doit être       │
  │ l'application Mediprix               │ ouvert. Commande :                                       │
  │                                      │ `netsh advfirewall firewall add rule name="Metabase"     │
  │                                      │ dir=in action=allow protocol=TCP localport=3000`         │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ D14 affiche une erreur               │ D14 n'a pas de filtre pharmacie. Le JWT ne doit pas      │
  │                                      │ contenir le paramètre "pharmacie" pour ce dashboard      │
  └──────────────────────────────────────┴──────────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)
