"""Mini-app Flask pour tester l'embedding Metabase avec filtres verrouilles.

Le pharmacien selectionne sa pharmacie, puis voit les 16 dashboards
dans des iframes Metabase avec le filtre pharmacie_sk LOCKED par JWT.

Usage :
    cd embed_app
    pip install -r requirements.txt
    python app.py
"""

import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

import jwt
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session

# Charge le .env du projet parent (c:\Temp\MediCore\.env)
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- Configuration ---

METABASE_SECRET_KEY = os.getenv(
    'METABASE_EMBEDDING_SECRET_KEY',
    '6bb88d0ecf2a8e8a45d60d04adda4ea87ab3cd50e809fa2d9ce1ae45b06f150c',
)
METABASE_SITE_URL = os.getenv('METABASE_SITE_URL', 'http://localhost:3001')

DASHBOARDS = [
    {'id': 2, 'name': 'D1 - Synthese pharmacie'},
    {'id': 3, 'name': 'D2 - Evolution CA'},
    {'id': 4, 'name': 'D3 - Tresorerie'},
    {'id': 5, 'name': 'D4 - Marge detaillee'},
    {'id': 6, 'name': 'D5 - Performance vendeurs'},
    {'id': 7, 'name': 'D6 - Univers RX OTC PARA'},
    {'id': 8, 'name': 'D7 - Stock et rotation'},
    {'id': 9, 'name': 'D8 - Ruptures et CA perdu'},
    {'id': 10, 'name': 'D9 - Ecoulement'},
    {'id': 11, 'name': 'D10 - Remises fournisseurs'},
    {'id': 12, 'name': 'D11 - Produits dormants'},
    {'id': 13, 'name': 'D12 - Classification ABC'},
    {'id': 14, 'name': 'D13 - Generiques et labos'},
    {'id': 15, 'name': 'D14 - Qualite des donnees'},
    {'id': 16, 'name': 'D15 - Detail transactions'},
    {'id': 17, 'name': 'D16 - Prix et mouvements stock'},
]


def get_metabase_token():
    """Authentification Metabase, retourne le session token."""
    data = json.dumps({
        'username': os.getenv('METABASE_ADMIN_EMAIL', 'augustin.madet@mediprix.fr'),
        'password': os.getenv('METABASE_ADMIN_PASSWORD', ''),
    }).encode()
    req = urllib.request.Request(
        f'{METABASE_SITE_URL}/api/session', data=data, method='POST',
        headers={'Content-Type': 'application/json'},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())['id']


def get_pharmacies():
    """Charge la liste des pharmacies via l'API Metabase (requete native admin)."""
    token = get_metabase_token()
    body = json.dumps({
        'database': int(os.getenv('MB_SOURCE_DATABASE_ID', '2')),
        'type': 'native',
        'native': {
            'query': 'SELECT PHA_ID, PHA_NOM FROM MARTS.DIM_PHARMACIE WHERE PHA_ID != -1 ORDER BY PHA_NOM',
        },
    }).encode()
    req = urllib.request.Request(
        f'{METABASE_SITE_URL}/api/dataset', data=body, method='POST',
        headers={
            'X-Metabase-Session': token,
            'Content-Type': 'application/json',
        },
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
    rows = resp.get('data', {}).get('rows', [])
    return [{'pha_id': row[0], 'pha_nom': row[1]} for row in rows]


# Dashboards sans filtre pharmacie (dashboard global)
DASHBOARDS_WITHOUT_PHARMACY = {15}  # D14 - Qualite des donnees


def generate_embed_token(dashboard_id, pha_id):
    """Genere le JWT d'embedding Metabase avec filtre pharmacie verrouille."""
    pharmacie_sk = hashlib.md5(str(pha_id).encode()).hexdigest()

    if dashboard_id in DASHBOARDS_WITHOUT_PHARMACY:
        payload = {
            'resource': {'dashboard': dashboard_id},
            'params': {},
            'exp': int(time.time()) + 600,
        }
    else:
        payload = {
            'resource': {'dashboard': dashboard_id},
            'params': {
                'pharmacie': [pharmacie_sk],
            },
            'exp': int(time.time()) + 600,
            '_embedding_params': {
                'pharmacie': 'locked',
                'mois': 'enabled',
                'date': 'enabled',
                'univers': 'enabled',
                'fournisseur': 'enabled',
                'operateur': 'enabled',
                'statut_dormant': 'enabled',
            },
        }

    return jwt.encode(payload, METABASE_SECRET_KEY, algorithm='HS256')


@app.route('/')
def index():
    """Page d'accueil : selection de la pharmacie."""
    pharmacies = get_pharmacies()
    return render_template('index.html', pharmacies=pharmacies)


@app.route('/select', methods=['POST'])
def select_pharmacy():
    """Enregistre la pharmacie selectionnee en session."""
    session['pha_id'] = int(request.form['pha_id'])
    session['pha_nom'] = request.form['pha_nom']
    return redirect(url_for('dashboard', dash_id=2))


@app.route('/dashboard/<int:dash_id>')
def dashboard(dash_id):
    """Affiche un dashboard Metabase en iframe."""
    pha_id = session.get('pha_id')
    pha_nom = session.get('pha_nom', '')

    if not pha_id:
        return redirect(url_for('index'))

    jwt_token = generate_embed_token(dash_id, pha_id)

    return render_template(
        'dashboard.html',
        jwt_token=jwt_token,
        metabase_url=METABASE_SITE_URL,
        pha_id=pha_id,
        pha_nom=pha_nom,
        dash_id=dash_id,
        dashboards=DASHBOARDS,
    )


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
