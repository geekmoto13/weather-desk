"""Nearby public NOAA observations, separate from Ambient station data."""

from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlencode
from weather_location import distance_km
from local_store import write_private_json
from rain_observations import has_measured_rain


def value(field, units):
    if not isinstance(field, dict) or str(field.get("qualityControl", "")).split(":")[-1] in (
        "X",
        "Z",
    ):
        return None
    number = field.get("value")
    if (
        isinstance(number, bool)
        or not isinstance(number, (int, float))
        or not math.isfinite(number)
    ):
        return None
    return units.get(field.get("unitCode"), lambda n: None)(number)


def normalize_public(raw, feels_like):
    p = raw.get("properties", {})
    try:
        stamp = dt.datetime.fromisoformat(p.get("timestamp", "").replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None
    if not math.isfinite(stamp) or stamp > time.time() + 300:
        return None
    temp = value(
        p.get("temperature"),
        {"wmoUnit:degC": lambda n: n * 9 / 5 + 32, "wmoUnit:degF": lambda n: n},
    )
    dew = value(
        p.get("dewpoint"), {"wmoUnit:degC": lambda n: n * 9 / 5 + 32, "wmoUnit:degF": lambda n: n}
    )
    mph = {
        "wmoUnit:km_h-1": lambda n: n / 1.609344,
        "wmoUnit:m_s-1": lambda n: n * 2.2369362921,
        "wmoUnit:kn": lambda n: n * 1.150779448,
        "wmoUnit:mi_h-1": lambda n: n,
    }
    wind = value(p.get("windSpeed"), mph)
    gust = value(p.get("windGust"), mph)
    humidity = value(p.get("relativeHumidity"), {"wmoUnit:percent": lambda n: n})
    pressure = value(
        p.get("seaLevelPressure"), {"wmoUnit:Pa": lambda n: n / 100, "wmoUnit:hPa": lambda n: n}
    )
    direction = value(
        p.get("windDirection"),
        {"wmoUnit:degree_(angle)": lambda n: n, "wmoUnit:degreeTrue": lambda n: n},
    )
    # Do not substitute station pressure for sea-level relative pressure.
    temp = temp if temp is not None and -150 <= temp <= 160 else None
    humidity = humidity if humidity is not None and 0 <= humidity <= 100 else None
    wind = wind if wind is not None and 0 <= wind <= 400 else None
    dew = dew if dew is not None and -200 <= dew <= 160 else None
    apparent, source = feels_like(temp, humidity, wind)
    row = {
        "timestamp": stamp,
        "tempF": temp if temp is not None and -150 <= temp <= 160 else None,
        "feelsF": apparent,
        "feelsSource": source,
        "dewF": dew,
        "dewSource": "NOAA / NWS",
        "humidity": humidity if humidity is not None and 0 <= humidity <= 100 else None,
        "windMph": wind if wind is not None and 0 <= wind <= 400 else None,
        "gustMph": gust if gust is not None and 0 <= gust <= 400 else None,
        "windDeg": direction if direction is not None and 0 <= direction <= 360 else None,
        "pressureHpa": pressure if pressure is not None and 800 <= pressure <= 1100 else None,
        "maxGustMph": None,
        "solar": None,
        "uv": None,
        "stationTimezone": None,
        "rainYearStatus": "missing",
    }
    for name in ("Day", "Event", "Week", "Month", "Year", "Total"):
        row["rain" + name + "Mm"] = None
    row["rainRateMmHr"] = None
    rain_units = {
        "wmoUnit:mm": lambda n: n,
        "wmoUnit:m": lambda n: n * 1000,
        "wmoUnit:in": lambda n: n * 25.4,
    }
    for field, target in [
        ("precipitationLastHour", "rainLastHourMm"),
        ("precipitationLast3Hours", "rainLast3hMm"),
        ("precipitationLast6Hours", "rainLast6hMm"),
    ]:
        reported = p.get(field)
        qc = (
            str(reported.get("qualityControl", "")).split(":")[-1]
            if isinstance(reported, dict)
            else ""
        )
        amount = value(reported, rain_units) if qc in ("C", "S", "V", "G") else None
        row[target] = amount if amount is not None and 0 <= amount <= 3000 else None
    return row


class PublicWeather:
    def __init__(self, directory, fetch, resolver, feels_like, trend):
        self.directory = Path(directory) / "public-weather"
        self.fetch, self.resolver, self.feels_like, self.trend = fetch, resolver, feels_like, trend
        self.lock = threading.RLock()
        self.states = {}

    def _key(self, settings):
        return f"{settings['latitude']:.4f},{settings['longitude']:.4f}"

    def snapshot(self, settings):
        key = self._key(settings)
        with self.lock:
            state = self.states.get(key)
            if state is None:
                state = {"checked": -math.inf, "loading": False, "payload": None, "error": None}
                self.states[key] = state
                try:
                    path = self.directory / (
                        hashlib.sha256(key.encode()).hexdigest()[:20] + ".json"
                    )
                    cached = json.loads(path.read_text())
                    if (
                        cached.get("locationKey") == key
                        and isinstance(cached.get("points"), list)
                        and has_measured_rain(cached.get("current"))
                    ):
                        state["payload"] = cached
                except (OSError, ValueError, TypeError):
                    pass
            if not state["loading"] and time.monotonic() - state["checked"] >= 300:
                state["loading"] = True
                state["checked"] = time.monotonic()
                threading.Thread(
                    target=self._load, args=(key, dict(settings), state), daemon=True
                ).start()
            if state["payload"] and not has_measured_rain(state["payload"].get("current")):
                state["payload"] = None
            result = copy.deepcopy(state["payload"] or {})
            current = result.get("current")
            result.update(
                {
                    "demo": False,
                    "source": "noaa",
                    "loading": state["loading"],
                    "error": state["error"],
                    "staleAfterSeconds": 5400,
                    "rainGaugeRequired": True,
                    "stationName": result.get("stationName", "Nearby NOAA station"),
                    "stale": bool(
                        state["error"] or not current or time.time() - current["timestamp"] > 5400
                    ),
                }
            )
            return result

    def history(self, settings):
        result = self.snapshot(settings)
        return {
            "demo": False,
            "points": result.get("points", []),
            "error": result.get("error"),
            "trend": result.get("trend"),
        }

    def _load(self, key, settings, state):
        try:
            point = self.resolver.point(settings["latitude"], settings["longitude"])
            raw = self.fetch(point["observationStations"])
            stations = []
            for feature in raw.get("features", []) if isinstance(raw, dict) else []:
                try:
                    p = feature["properties"]
                    sid = p["stationIdentifier"]
                    if not re.fullmatch(r"[A-Z0-9]{3,8}", sid):
                        continue
                    lon, lat = feature["geometry"]["coordinates"][:2]
                    d = distance_km(settings["latitude"], settings["longitude"], lat, lon)
                    stations.append((d, sid, p.get("name", sid)))
                except (KeyError, TypeError, ValueError):
                    continue
            chosen = None
            for d, sid, name in sorted(stations)[:6]:
                try:
                    start = dt.datetime.fromtimestamp(
                        time.time() - 27 * 3600, dt.timezone.utc
                    ).isoformat()
                    raw = self.fetch(
                        "https://api.weather.gov/stations/"
                        + sid
                        + "/observations?"
                        + urlencode({"start": start, "limit": 500})
                    )
                    points = [normalize_public(f, self.feels_like) for f in raw.get("features", [])]
                    points = sorted(
                        (p for p in points if p is not None), key=lambda p: p["timestamp"]
                    )
                    usable = [
                        p
                        for p in points
                        if p["tempF"] is not None
                        and time.time() - p["timestamp"] <= 5400
                        and has_measured_rain(p)
                    ]
                    if not usable:
                        continue
                    current = usable[-1]
                    chosen = {
                        "locationKey": key,
                        "current": current,
                        "points": points,
                        "stationName": str(name)[:150],
                        "stationId": sid,
                        "distanceKm": round(d, 1),
                        "trend": self.trend(current, points),
                        "sourceUrl": "https://www.weather.gov/wrh/timeseries?site=" + sid,
                        "fetchedAt": time.time(),
                    }
                    break
                except Exception:
                    continue
            if chosen is None:
                raise ValueError(
                    "No nearby NOAA station has a recent temperature and quality-checked rainfall report. Retrying automatically."
                )
            try:
                self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                write_private_json(
                    self.directory / (hashlib.sha256(key.encode()).hexdigest()[:20] + ".json"),
                    chosen,
                )
            except OSError:
                pass
            with self.lock:
                state["payload"], state["error"] = chosen, None
        except Exception as exc:
            with self.lock:
                state["error"] = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "Nearby NOAA observations could not refresh. Retrying automatically."
                )
        finally:
            with self.lock:
                state["loading"] = False
