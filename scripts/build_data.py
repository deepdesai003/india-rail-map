"""Build the map's data files from the DataMeet Indian Railways dataset.

Usage: python scripts/build_data.py <path-to-datameet-railways> <output-dir>

Writes network.json, trains.json, stidx.json and stops/s0..s31.json.
"""
import collections
import heapq
import json
import math
import os
import sys

SRC, OUT = sys.argv[1], sys.argv[2]
os.makedirs(os.path.join(OUT, 'stops'), exist_ok=True)
SHARDS = 32


def dump(obj, name):
    with open(os.path.join(OUT, name), 'w') as f:
        json.dump(obj, f, separators=(',', ':'))


def hav(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(d))


def in_india(p):
    return 67 < p[0] < 98 and 6 < p[1] < 37.5


def clean(coords):
    """Drop points outside India and geocoding spikes far off the line."""
    pts = [c for c in coords if c and len(c) >= 2 and in_india(c)]
    changed = True
    while changed and len(pts) > 2:
        changed = False
        out = [pts[0]]
        for i in range(1, len(pts) - 1):
            a, b, c = out[-1], pts[i], pts[i + 1]
            if hav(a, b) + hav(b, c) > 2.5 * hav(a, c) + 80:
                changed = True
                continue
            out.append(b)
        out.append(pts[-1])
        pts = out
    if len(pts) > 2 and hav(pts[0], pts[1]) > 3 * hav(pts[1], pts[2]) + 250:
        pts = pts[1:]
    if len(pts) > 2 and hav(pts[-1], pts[-2]) > 3 * hav(pts[-2], pts[-3]) + 250:
        pts = pts[:-1]
    return pts


def hhmm_to_min(t):
    if not t or t == 'None':
        return ''
    h, m = t[:5].split(':')
    return str(int(h) * 60 + int(m))


# ---------- stations ----------
st = {}
for f in json.load(open(os.path.join(SRC, 'stations.json')))['features']:
    p, g = f['properties'], f.get('geometry')
    c = g['coordinates'] if g else None
    st[p['code']] = [(p.get('name') or '').title(), p.get('state') or ''] + (
        [round(c[0], 4), round(c[1], 4)] if c and in_india(c) else [])

# ---------- schedules ----------
stops = collections.defaultdict(list)
for r in json.load(open(os.path.join(SRC, 'schedules.json'))):
    stops[r['train_number']].append(r)

# ---------- trains + network ----------
edges, trains, stop_str = {}, [], {}
for f in json.load(open(os.path.join(SRC, 'trains.json')))['features']:
    p, g = f['properties'], f.get('geometry')
    if not g or not g.get('coordinates'):
        continue
    pts = clean(g['coordinates'])
    if len(pts) < 2:
        continue
    pts = [[round(x, 4), round(y, 4)] for x, y in pts]
    for a, b in zip(pts, pts[1:]):
        if a == b or hav(a, b) > 160:
            continue
        k = (tuple(a), tuple(b)) if a < b else (tuple(b), tuple(a))
        edges[k] = edges.get(k, 0) + 1
    flat, px, py = [], 0, 0
    for x, y in pts:
        ix, iy = round(x * 1e4), round(y * 1e4)
        flat += [ix - px, iy - py]
        px, py = ix, iy
    no = p['number']
    rows = sorted(stops.get(no, []), key=lambda r: (r.get('day') or 0, r.get('id') or 0))
    stop_str[no] = ';'.join(
        f"{r['station_code']},{hhmm_to_min(r.get('arrival'))},{hhmm_to_min(r.get('departure'))},{r.get('day') or 1}"
        for r in rows)
    trains.append({'no': no, 'nm': p.get('name') or '', 'ty': p.get('type') or '',
                   'fr': (p.get('from_station_name') or '').title(), 'to': (p.get('to_station_name') or '').title(),
                   'fc': p.get('from_station_code'), 'tc': p.get('to_station_code'),
                   'dp': (p.get('departure') or '')[:5], 'ar': (p.get('arrival') or '')[:5],
                   'km': p.get('distance'), 'z': p.get('zone') or '', 'g': flat})

net = []
for (a, b), n in edges.items():
    net += [round(a[0] * 1e4), round(a[1] * 1e4), round(b[0] * 1e4), round(b[1] * 1e4), min(n, 255)]

# ---------- station traffic counts + station index ----------
count = collections.Counter()
stidx = collections.defaultdict(list)
for no, s in stop_str.items():
    if not s:
        continue
    for x in s.split(';'):
        c = x.split(',')[0]
        count[c] += 1
        if no not in stidx[c]:
            stidx[c].append(no)
for code, v in st.items():
    if len(v) >= 4:
        v.append(count.get(code, 0))

# ---------- estimated track speed ----------
# Fastest scheduled speed between consecutive stops (2nd fastest when 3+ trains,
# to damp timetable errors), with express non-stop runs folded onto the
# station-to-station segments they pass over.
samples = collections.defaultdict(list)
for no, s in stop_str.items():
    if not s:
        continue
    rows = [x.split(',') for x in s.split(';')]
    for (c1, a1, d1, y1), (c2, a2, d2, y2) in zip(rows, rows[1:]):
        v1, v2 = st.get(c1), st.get(c2)
        if not v1 or not v2 or len(v1) < 4 or len(v2) < 4:
            continue
        t0, t1 = d1 or a1, a2 or d2
        if t0 == '' or t1 == '':
            continue
        t = (int(y2) * 1440 + int(t1)) - (int(y1) * 1440 + int(t0))
        km = hav(v1[2:4], v2[2:4]) * 1.12
        if km < 2 or km > 200 or t < 1:
            continue
        k = (c1, c2) if c1 < c2 else (c2, c1)
        v = km / t * 60
        samples[k].append(v if t >= 5 and v <= 165 else None)

E = {}
for (a, b), vs in samples.items():
    good = sorted([v for v in vs if v is not None], reverse=True)
    v = (good[1] if len(good) >= 3 else good[0]) if good else None
    A, B = st[a], st[b]
    ka, kb = (round(A[2] * 1e4), round(A[3] * 1e4)), (round(B[2] * 1e4), round(B[3] * 1e4))
    if ka == kb:
        continue
    k = (ka, kb) if ka < kb else (kb, ka)
    if v is None:
        E.setdefault(k, None)
    else:
        E[k] = max(E.get(k) or 0, v)


def seg_len(a, b):
    dx = (a[0] - b[0]) * math.cos(math.radians(a[1] / 1e4))
    return math.hypot(dx, a[1] - b[1]) / 1e4 * 111


adj = collections.defaultdict(dict)
for a, b in E:
    adj[a][b] = adj[b][a] = seg_len(a, b)
removed = set()
for k in sorted(E, key=lambda k: -seg_len(*k)):
    a, c = k
    lim = seg_len(a, c) * 1.15
    dist, prev, pq, found = {a: 0}, {}, [(0, a)], False
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18):
            continue
        if u == c:
            found = True
            break
        for v, w in adj[u].items():
            if {u, v} == {a, c}:
                continue
            nd = d + w
            if nd <= lim and nd < dist.get(v, 1e18):
                dist[v], prev[v] = nd, u
                heapq.heappush(pq, (nd, v))
    if not found:
        continue
    u, path = c, []
    while u != a:
        path.append((prev[u], u))
        u = prev[u]
    if len(path) < 2:
        continue
    if E[k] is not None:
        for x, y in path:
            kk = (x, y) if x < y else (y, x)
            E[kk] = max(E[kk] or 0, E[k])
    del adj[a][c], adj[c][a]
    removed.add(k)

for _ in range(3):
    for k, v in list(E.items()):
        if v is not None or k in removed:
            continue
        nb = []
        for i in (0, 1):
            for x in adj[k[i]]:
                kk = (min(k[i], x), max(k[i], x))
                if kk != k and E.get(kk) is not None:
                    nb.append(E[kk])
        if nb:
            E[k] = sorted(nb)[len(nb) // 2]

speed = []
for k, v in E.items():
    if k in removed or v is None:
        continue
    speed += [k[0][0], k[0][1], k[1][0], k[1][1], round(v)]

# ---------- write ----------
dump({'net': net, 'st': st, 'speed': speed}, 'network.json')
dump({'t': trains}, 'trains.json')
dump(stidx, 'stidx.json')
shards = collections.defaultdict(dict)
for no, s in stop_str.items():
    shards[int(''.join(c for c in no if c.isdigit()) or 0) % SHARDS][no] = s
for i in range(SHARDS):
    dump(shards.get(i, {}), f'stops/s{i}.json')
print(f'{len(trains)} trains, {len(edges)} track segments, {len(speed) // 5} speed segments, '
      f'{sum(1 for v in st.values() if len(v) >= 4)} located stations')
