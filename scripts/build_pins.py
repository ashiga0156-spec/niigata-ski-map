#!/usr/bin/env python3
"""Look up place coordinates in OpenStreetMap (Overpass API) and write data/pins.json.

Input : data/places.json  (names, categories, descriptions curated by hand)
Output: data/pins.json    (what the map loads)
        data/build-report.md  (what matched, what did not)

Only three Overpass requests are made (ski, sake, access); matching happens
locally. Python 3 standard library only. Meant to run in GitHub Actions.
"""
import json
import math
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLACES = ROOT / "data" / "places.json"
OUT = ROOT / "data" / "pins.json"
CANDIDATE = ROOT / "data" / "pins.candidate.json"
REPORT = ROOT / "data" / "build-report.md"

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# south, west, north, east: Joetsu/Myoko, Yuzawa, Nagaoka and Niigata City.
BBOX = (36.55, 137.95, 38.05, 139.45)

# Rough town centres, used to break ties between places that share a name.
ANCHORS = {
    "yuzawa": (36.9333, 138.8100),
    "minamiuonuma": (37.0600, 138.8800),
    "uonuma": (37.2300, 138.9600),
    "tsunan": (37.0000, 138.6500),
    "myoko": (37.0300, 138.2700),
    "joetsu": (37.1500, 138.2400),
    "nagaoka": (37.4500, 138.8500),
    "niigata": (37.9100, 139.0600),
}

MAX_DIST_KM = 30.0       # farther than this from the anchor: reject
VERIFIED_DIST_KM = 25.0  # and score must also be high enough
VERIFIED_SCORE = 6
MIN_SHARE = 0.6          # write pins.json only if this share of places resolved
REQUEST_TIMEOUT = 150     # seconds per HTTP attempt


def log(msg):
    print(msg, flush=True)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def overpass(query):
    """Run one Overpass query, trying each endpoint a couple of times."""
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(2):
        for url in ENDPOINTS:
            started = time.time()
            try:
                log("  request to %s (attempt %d)" % (url.split("/")[2], attempt + 1))
                req = urllib.request.Request(
                    url, data=body, headers={"User-Agent": "niigata-ski-map-build/1.2"})
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
                    data = json.load(res)
                log("  ok: %d elements in %.0fs" % (len(data.get("elements", [])), time.time() - started))
                return data
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
                last = e
                log("  failed after %.0fs: %s" % (time.time() - started, e))
                time.sleep(4)
    raise RuntimeError("Overpass failed: %s" % last)


def bbox_str():
    return "(%.3f,%.3f,%.3f,%.3f)" % BBOX


def category_query(category, literals):
    """Cheap, tag-indexed queries (no name regex over the whole bbox).
    Names are matched locally afterwards."""
    b = bbox_str()
    if category == "ski":
        parts = [
            'nwr["landuse"="winter_sports"]%s;' % b,
            'nwr["sport"="skiing"]["name"]%s;' % b,
            'nwr["aerialway"="station"]["name"]%s;' % b,
            'nwr["tourism"="resort"]["name"]%s;' % b,
        ]
    elif category == "sake":
        parts = [
            'nwr["craft"~"brewery|sake_brewery"]%s;' % b,
            'nwr["industrial"="brewery"]%s;' % b,
            'nwr["shop"="alcohol"]["name"]%s;' % b,
            'nwr["tourism"~"attraction|museum"]["name"~"酒|蔵"]%s;' % b,
        ]
    else:
        parts = [
            'nwr["railway"="station"]["name"]%s;' % b,
            'nwr["aeroway"="aerodrome"]["name"]%s;' % b,
        ]
    return "[out:json][timeout:120];(" + "".join(parts) + ");out center tags;"


def fetch_all(places):
    """One request per category. Returns ({category: elements}, {category: error})."""
    elements, errors = {}, {}
    for category in ("ski", "sake", "access"):
        literals = [s for p in places if p["category"] == category for s in p["search"]]
        if not literals:
            continue
        log("Fetching %s (%d search terms)" % (category, len(literals)))
        try:
            elements[category] = overpass(category_query(category, literals)).get("elements", [])
        except RuntimeError as e:
            errors[category] = str(e)
            elements[category] = []
        time.sleep(3)
    return elements, errors


def center_of(el):
    if "lat" in el and "lon" in el:
        return el["lat"], el["lon"]
    c = el.get("center")
    if c:
        return c["lat"], c["lon"]
    return None


def score(tags, category, literals, name):
    s = 0
    if category == "ski":
        if tags.get("landuse") == "winter_sports":
            s += 10
        if "ski" in tags.get("sport", ""):
            s += 6
        if "piste:type" in tags:
            s += 2
        if tags.get("aerialway"):
            s += 2
        if tags.get("natural") in ("peak", "volcano", "ridge", "saddle"):
            s -= 6
        if tags.get("tourism") in ("hotel", "guest_house", "hostel", "apartment", "motel"):
            s -= 6
        if tags.get("amenity") in ("restaurant", "cafe", "fast_food", "bus_station"):
            s -= 4
        if tags.get("place"):
            s -= 4
        if "スキー" in name or "スノー" in name:
            s += 2
    elif category == "sake":
        if tags.get("craft") in ("brewery", "sake_brewery"):
            s += 10
        if tags.get("industrial") == "brewery":
            s += 8
        if tags.get("shop") in ("alcohol", "wine"):
            s += 4
        if tags.get("tourism") in ("attraction", "museum"):
            s += 3
        if tags.get("amenity") in ("restaurant", "cafe", "pub"):
            s += 1
        if "building" in tags:
            s += 1
        if tags.get("place"):
            s -= 4
    else:  # access
        if tags.get("railway") == "station":
            s += 10
        if tags.get("aeroway") == "aerodrome":
            s += 10
        if tags.get("public_transport") == "station":
            s += 6
        if tags.get("railway") == "halt":
            s += 4
        if tags.get("amenity") == "bus_station":
            s += 3
        if tags.get("place"):
            s -= 4
    exact = set(literals) | {l + "駅" for l in literals}
    if name in exact:
        s += 3
    return s


def match_place(place, elements):
    """Pick the best element for one place. Returns (best_or_None, candidate_count)."""
    lat, lon = ANCHORS[place["area"]]
    literals = place["search"]
    lowered = [l.lower() for l in literals]
    cands, seen = [], set()
    for el in elements:
        key = (el.get("type"), el.get("id"))
        if key in seen:
            continue
        seen.add(key)
        tags = el.get("tags", {})
        name = tags.get("name", "")
        if not any(l in name.lower() for l in lowered):
            continue
        if place["category"] == "access" and name not in set(literals) | {l + "駅" for l in literals}:
            continue  # e.g. reject 北長岡 when looking for 長岡
        c = center_of(el)
        if not c:
            continue
        dist = haversine_km(lat, lon, c[0], c[1])
        if dist > MAX_DIST_KM:
            continue
        cands.append({
            "ref": "%s/%s" % (el.get("type"), el.get("id")),
            "name": name,
            "lat": c[0],
            "lon": c[1],
            "dist": dist,
            "score": score(tags, place["category"], literals, name),
        })
    if not cands:
        return None, 0
    cands.sort(key=lambda x: (-x["score"], x["dist"]))
    return cands[0], len(cands)


NOMINATIM = "https://nominatim.openstreetmap.org/search"


def nominatim(place):
    """Fallback geocoder for places the Overpass tag search missed."""
    lat, lon = ANCHORS[place["area"]]
    s, w, n, e = BBOX
    params = urllib.parse.urlencode({
        "q": place.get("name_ja") or place["search"][0],
        "format": "jsonv2", "limit": 5, "countrycodes": "jp",
        "accept-language": "ja", "viewbox": "%s,%s,%s,%s" % (w, n, e, s), "bounded": 1,
    })
    try:
        req = urllib.request.Request(NOMINATIM + "?" + params,
                                     headers={"User-Agent": "niigata-ski-map-build/1.3"})
        with urllib.request.urlopen(req, timeout=40) as res:
            rows = json.load(res)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as ex:
        log("  nominatim failed for %s: %s" % (place["id"], ex))
        return None
    for r in rows:
        d = haversine_km(lat, lon, float(r["lat"]), float(r["lon"]))
        if d <= MAX_DIST_KM:
            text = r.get("display_name", "")
            hit = any(l in text for l in place["search"])
            if not hit:
                continue  # wrong place with a similar name: skip
            return {"ref": "nominatim/%s" % r.get("osm_id"), "name": text.split(",")[0],
                    "lat": float(r["lat"]), "lon": float(r["lon"]), "dist": d,
                    "score": VERIFIED_SCORE if hit else 0}
    return None


def make_pin(p, lat, lon, verified, source):
    return {
        "id": p["id"],
        "name": p["name"],
        "name_ja": p.get("name_ja", ""),
        "category": p["category"],
        "lat": round(lat, 5),
        "lng": round(lon, 5),
        "desc": p.get("desc", ""),
        "links": p.get("links", []),
        "verified": bool(verified),
        "source": source,
    }


def build(places, elements, errors=None, extra=None):
    errors = errors or {}
    pins, lines = [], []
    resolved = {}
    stats = {"ok": 0, "weak": 0, "missing": 0, "copied": 0}

    for p in places:
        if p.get("coords_from"):
            continue
        if p["category"] in errors and not (extra and p["id"] in extra):
            stats["missing"] += 1
            lines.append("| %s | ERROR | %s |" % (p["id"], errors[p["category"]]))
            continue
        if p.get("manual"):
            mlat, mlon = p["manual"]
            stats["ok"] += 1
            resolved[p["id"]] = (mlat, mlon)
            lines.append("| %s | manual coordinates | from places.json |" % p["id"])
            pins.append(make_pin(p, mlat, mlon, p.get("manual_verified", True), "manual"))
            continue
        best, n = match_place(p, elements.get(p["category"], []))
        if not best and extra and p["id"] in extra:
            best, n = extra[p["id"]], 0
        if not best:
            stats["missing"] += 1
            lines.append("| %s | not found in OSM | skipped |" % p["id"])
            continue
        ok = best["score"] >= VERIFIED_SCORE and best["dist"] <= VERIFIED_DIST_KM
        stats["ok" if ok else "weak"] += 1
        resolved[p["id"]] = (best["lat"], best["lon"])
        lines.append("| %s | %s (%s) | score %d, %.1f km from anchor, %d candidates%s |" % (
            p["id"], best["name"], best["ref"], best["score"], best["dist"], n,
            "" if ok else " **CHECK**"))
        pins.append(make_pin(p, best["lat"], best["lon"], ok, "osm:" + best["ref"]))

    for p in places:
        src = p.get("coords_from")
        if not src:
            continue
        if src in resolved:
            lat, lon = resolved[src]
            stats["copied"] += 1
            lines.append("| %s | copied from %s | offset slightly |" % (p["id"], src))
            pins.append(make_pin(p, lat + 0.0004, lon + 0.0004, True, "copy:" + src))
        else:
            stats["missing"] += 1
            lines.append("| %s | %s missing | skipped |" % (p["id"], src))

    order = {p["id"]: i for i, p in enumerate(places)}
    pins.sort(key=lambda x: order[x["id"]])
    return pins, lines, stats


def main():
    places = json.loads(PLACES.read_text(encoding="utf-8"))
    elements, errors = fetch_all(places)
    pins, lines, stats = build(places, elements, errors)
    placed_ids = {x["id"] for x in pins}
    extra = {}
    for p in places:
        if p["id"] in placed_ids or p.get("coords_from") or p.get("manual"):
            continue
        log("Nominatim fallback: %s" % p["id"])
        r = nominatim(p)
        if r:
            extra[p["id"]] = r
        time.sleep(1.2)
    if extra:
        pins, lines, stats = build(places, elements, errors, extra)
    total = len(places)
    placed = len(pins)

    head = ["# Pin build report", "",
            "Placed %d of %d places. OK: %d, to check: %d, missing: %d, copied: %d." % (
                placed, total, stats["ok"], stats["weak"], stats["missing"], stats["copied"]),
            "", "| id | match | detail |", "|---|---|---|"]
    REPORT.write_text("\n".join(head + lines) + "\n", encoding="utf-8")

    target = OUT if total and placed / total >= MIN_SHARE else CANDIDATE
    target.write_text(json.dumps(pins, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(REPORT.read_text(encoding="utf-8"))
    if target is CANDIDATE:
        log("Too few places resolved; wrote %s instead of %s" % (CANDIDATE.name, OUT.name))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
