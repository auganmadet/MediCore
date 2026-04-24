import urllib.request
import json

data = json.dumps({
    'username': 'augustin.madet@mediprix.fr',
    'password': 'AuganThuan1103',
}).encode()

req = urllib.request.Request(
    'http://localhost:3001/api/session',
    data=data,
    headers={'Content-Type': 'application/json'},
)

resp = json.loads(urllib.request.urlopen(req).read())
print(resp['id'])
