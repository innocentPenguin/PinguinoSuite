#!/usr/bin/env python3
"""NOTE: with the Host running (and the streamer signed in) you do not need this script: open http://127.0.0.1:8770/api/helix-ids and the Host does the same lookup with its own credentials.
Optional: ask Helix /users?id= for every id in Data\namehistory\lookups.json and save the answer for
build-namehistory.py --helix-ids. Same id under a different login than we logged = CERTAIN rename.
Needs env TWITCH_CLIENT_ID and TWITCH_APP_TOKEN (an app token; nothing is read from the vault, nothing printed).
Opted-out users are already excluded from lookups.json."""
import json, os, sys, urllib.request
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ids = json.load(open(os.path.join(root, 'Data', 'namehistory', 'lookups.json'), encoding='utf-8'))['ids']
cid, tok = os.environ.get('TWITCH_CLIENT_ID'), os.environ.get('TWITCH_APP_TOKEN')
if not (cid and tok): sys.exit('set TWITCH_CLIENT_ID and TWITCH_APP_TOKEN')
rows = []
for i in range(0, len(ids), 100):
    q = '&'.join('id=' + x for x in ids[i:i + 100])
    r = urllib.request.Request('https://api.twitch.tv/helix/users?' + q, headers={'Client-Id': cid, 'Authorization': 'Bearer ' + tok})
    rows += json.load(urllib.request.urlopen(r)).get('data', [])
json.dump({'data': [{'id': x['id'], 'login': x['login']} for x in rows]},
          open(os.path.join(root, 'Data', 'namehistory', 'helix_ids.json'), 'w'), indent=1)
print(len(rows), 'users saved')
