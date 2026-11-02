"""US place lookup and local NOAA reference selection. No weather keys needed."""

from __future__ import annotations
import datetime as dt
import json
import math
import re
import threading
import time
from urllib.parse import urlencode
from timezones import local_date, validate_zone


def distance_km(lat, lon, other_lat, other_lon):
    a, b = math.radians(lat), math.radians(other_lat)
    dlat, dlon = b - a, math.radians(other_lon - lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


def coordinates(lat, lon):
    if isinstance(lat, bool) or isinstance(lon, bool):
        raise ValueError("Choose a valid location.")
    try:
        lat, lon = float(lat), float(lon)
    except (ValueError, TypeError):
        raise ValueError("Choose a valid location.") from None
    if (
        not math.isfinite(lat)
        or not math.isfinite(lon)
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
    ):
        raise ValueError("Choose valid latitude and longitude.")
    return lat, lon


def grid_center(value):
    value = value.strip().upper()
    if not re.fullmatch(r"[A-R]{2}[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?", value):
        raise ValueError("Use a 4-, 6- or 8-character Maidenhead grid square.")
    lon, lat = (ord(value[0]) - 65) * 20 - 180, (ord(value[1]) - 65) * 10 - 90
    lon += int(value[2]) * 2
    lat += int(value[3])
    width, height = 2, 1
    if len(value) >= 6:
        width, height = 2 / 24, 1 / 24
        lon += (ord(value[4]) - 65) * width
        lat += (ord(value[5]) - 65) * height
    if len(value) == 8:
        width, height = width / 10, height / 10
        lon += int(value[6]) * width
        lat += int(value[7]) * height
    return lat + height / 2, lon + width / 2


def _normal(value):
    if isinstance(value, list):
        value = value[0] if value else None
    try:
        return value == "T" or math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


class LocationResolver:
    def __init__(self, fetch):
        self.fetch = fetch
        self.points = {}
        self.tide_stations = None
        self.lock = threading.Lock()

    def search(self, query):
        if (
            not isinstance(query, str)
            or not 2 <= len(query.strip()) <= 100
            or any(ord(c) < 32 for c in query)
        ):
            raise ValueError("Enter a US ZIP code, city and state, or Maidenhead grid square.")
        query = query.strip()
        if re.fullmatch(r"[A-Za-z]{2}\d{2}(?:[A-Za-z]{2}(?:\d{2})?)?", query):
            lat, lon = grid_center(query)
            return {
                "matches": [
                    {
                        "name": query.upper() + " · grid-square center",
                        "latitude": lat,
                        "longitude": lon,
                    }
                ]
            }
        raw = self.fetch(
            "https://geocoding-api.open-meteo.com/v1/search?"
            + urlencode(
                {"name": query, "count": 8, "countryCode": "US", "language": "en", "format": "json"}
            )
        )
        matches = []
        seen = set()
        results = raw.get("results", []) if isinstance(raw, dict) else []
        populated = [
            r
            for r in results
            if isinstance(r, dict) and str(r.get("feature_code", "")).startswith("PPL")
        ]
        for row in populated or results:
            if not isinstance(row, dict) or row.get("country_code") != "US":
                continue
            try:
                lat, lon = coordinates(row.get("latitude"), row.get("longitude"))
            except ValueError:
                continue
            name = ", ".join(dict.fromkeys(str(row[k]) for k in ("name", "admin1") if row.get(k)))
            if not name or (name, lat, lon) in seen:
                continue
            seen.add((name, lat, lon))
            matches.append({"name": name[:100], "latitude": lat, "longitude": lon})
        return {
            "matches": matches,
            "message": (
                None if matches else "No US match found. Try a five-digit ZIP or City, State."
            ),
        }

    def point(self, lat, lon):
        key = f"{lat:.4f},{lon:.4f}"
        with self.lock:
            cached = self.points.get(key)
        if cached and time.monotonic() - cached[0] < 86400:
            return dict(cached[1])
        raw = self.fetch("https://api.weather.gov/points/" + key)
        p = raw.get("properties", {}) if isinstance(raw, dict) else {}
        if not p.get("timeZone") or not re.fullmatch(
            r"https://api\.weather\.gov/gridpoints/[A-Z]{3,4}/[0-9]+,[0-9]+/stations",
            str(p.get("observationStations", "")),
        ):
            raise ValueError(
                "NOAA weather coverage is unavailable for this location. This release supports US locations."
            )
        validate_zone(p["timeZone"])
        with self.lock:
            self.points[key] = (time.monotonic(), dict(p))
        return dict(p)

    def climate(self, lat, lon, zone, office):
        today = local_date(zone=zone)
        sites = []
        for radius in (1.0, 3.0):
            span = radius / max(0.25, math.cos(math.radians(lat)))
            params = {
                "bbox": f"{max(-180,lon-span):.4f},{max(-90,lat-radius):.4f},{min(180,lon+span):.4f},{min(90,lat+radius):.4f}",
                "meta": "name,state,ll,sids,uid,valid_daterange",
                "elems": "maxt,mint,pcpn",
                "sdate": (today - dt.timedelta(days=60)).isoformat(),
                "edate": today.isoformat(),
            }
            raw = self.fetch(
                "https://data.rcc-acis.org/StnMeta?"
                + urlencode({"params": json.dumps(params, separators=(",", ":"))})
            )
            for row in raw.get("meta", []) if isinstance(raw, dict) else []:
                try:
                    ranges = row.get("valid_daterange", [])
                    if len(ranges) != 3 or not all(
                        isinstance(r, list)
                        and len(r) == 2
                        and dt.date.fromisoformat(r[0]) <= dt.date(1991, 1, 1)
                        and dt.date.fromisoformat(r[1]) >= today - dt.timedelta(days=90)
                        for r in ranges
                    ):
                        continue
                    other_lon, other_lat = row["ll"]
                    d = distance_km(lat, lon, other_lat, other_lon)
                    ids = [
                        s
                        for s in row.get("sids", [])
                        if re.fullmatch(r"[A-Za-z0-9]{3,20} (?:6|2|1)", s)
                    ]
                    ids.sort(key=lambda s: 0 if s.endswith(" 6") else 1)
                    if ids and d <= 400:
                        sites.append((d, row, ids[0]))
                except (ValueError, TypeError, KeyError, OverflowError):
                    continue
            if sites:
                break
        for d, row, sid in sorted(sites, key=lambda v: v[0])[:4]:
            params = {
                "sid": sid,
                "date": today.isoformat(),
                "meta": "name",
                "elems": [
                    {"name": n, "normal": 91, "prec": 3} for n in ("maxt", "mint", "avgt", "pcpn")
                ],
            }
            raw = self.fetch(
                "https://data.rcc-acis.org/StnData?"
                + urlencode({"params": json.dumps(params, separators=(",", ":"))})
            )
            data = raw.get("data", []) if isinstance(raw, dict) else []
            if (
                raw.get("meta", {}).get("name") != row["name"]
                or not data
                or len(data[0]) != 5
                or not all(_normal(v) for v in data[0][1:])
            ):
                continue
            return {
                "id": sid.split()[0],
                "sid": sid,
                "name": str(row["name"])[:100],
                "label": str(row["name"]).title()[:100],
                "timezone": zone,
                "distanceKm": round(d, 1),
                "sourceUrl": "https://www.weather.gov/wrh/Climate?wfo=" + office.lower(),
                "available": True,
                "periods": row["valid_daterange"],
            }
        return {
            "id": "unavailable",
            "sid": "unavailable",
            "name": "Local climate unavailable",
            "label": "Local climate",
            "timezone": zone,
            "available": False,
            "sourceUrl": "https://www.weather.gov/wrh/Climate?wfo=" + office.lower(),
        }

    def tide(self, lat, lon):
        try:
            if self.tide_stations is None:
                raw = self.fetch(
                    "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=tidepredictions"
                )
                self.tide_stations = raw.get("stations", [])
            sites = []
            for row in self.tide_stations:
                if not re.fullmatch(r"\d{7}", str(row.get("id", ""))):
                    continue
                try:
                    d = distance_km(lat, lon, float(row["lat"]), float(row["lng"]))
                except (ValueError, TypeError, KeyError):
                    continue
                if d <= 100:
                    sites.append((d, row))
            if sites:
                row = min(sites, key=lambda v: v[0])[1]
                return {"tideStation": row["id"], "tideName": str(row["name"])[:100]}
        except Exception:
            pass
        return {"tideStation": "", "tideName": ""}

    def resolve(self, lat, lon, name=""):
        lat, lon = coordinates(lat, lon)
        p = self.point(lat, lon)
        office = p.get("cwa", "")
        if not re.fullmatch(r"[A-Z]{3,4}", office):
            raise ValueError("NOAA did not return a local forecast office.")
        rel = p.get("relativeLocation", {}).get("properties", {})
        label = str(
            name or ", ".join(str(rel[k]) for k in ("city", "state") if rel.get(k))
        ).strip()[:100]
        radar = p.get("radarStation", "")
        if not re.fullmatch(r"[A-Z][A-Z0-9]{3}", radar):
            raise ValueError("NOAA did not return a local radar station.")
        try:
            climate = self.climate(lat, lon, p["timeZone"], office)
        except Exception:
            climate = {
                "id": "unavailable",
                "sid": "unavailable",
                "name": "Local climate unavailable",
                "label": "Local climate",
                "timezone": p["timeZone"],
                "available": False,
                "sourceUrl": "https://www.weather.gov/wrh/Climate?wfo=" + office.lower(),
            }
        return {
            "latitude": lat,
            "longitude": lon,
            "location": label or "Your location",
            "timezone": p["timeZone"],
            "radarStation": radar,
            "climateStation": climate,
            "locationConfigured": True,
            **self.tide(lat, lon),
        }
