"""Point-specific NWS alerts, independent of Ambient station credentials."""

from __future__ import annotations

from collections import OrderedDict
import copy
import datetime as dt
import math
import threading
import time
from urllib.parse import urlencode

REFRESH_SECONDS = 60
STALE_SECONDS = 180
SOURCE = "NOAA / National Weather Service"
UNAVAILABLE = "The NWS alert feed could not be checked. Retrying automatically."


def timestamp(value):
    try:
        date = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return date.timestamp() if date.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def text(value, limit=30000):
    return value[:limit].strip() if isinstance(value, str) else ""


def aliases(value):
    if not isinstance(value, dict):
        return set()
    result = set()
    for name in ("id", "@id", "identifier"):
        identifier = text(value.get(name), 2000)
        if identifier:
            result.update((identifier, identifier.rsplit("/", 1)[-1]))
    return result


def alert_kind(event):
    words = event.lower().split()
    return next((kind for kind in ("warning", "watch", "advisory") if kind in words), "statement")


def priority(alert):
    # Keep warnings ahead of watches/advisories, then order by CAP severity/urgency.
    return (
        {"warning": 0, "watch": 1, "advisory": 2, "statement": 3}[alert["kind"]],
        {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}.get(alert["severity"], 4),
        {"Immediate": 0, "Expected": 1, "Future": 2}.get(alert["urgency"], 3),
        -(alert["sentAt"] or 0),
    )


def parse_alerts(raw, now):
    if (
        not isinstance(raw, dict)
        or raw.get("type") != "FeatureCollection"
        or not isinstance(raw.get("features"), list)
    ):
        raise ValueError("Not an NWS alert collection")
    if raw.get("pagination", {}).get("next"):
        raise ValueError("Incomplete alert collection")
    features = raw["features"]
    superseded = set()
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            raise ValueError("Unreadable alert")
        props = feature["properties"]
        if props.get("status") == "Actual" and props.get("messageType") in ("Update", "Cancel"):
            references = props.get("references") or []
            if not isinstance(references, list):
                raise ValueError("Unreadable alert references")
            for reference in references:
                superseded.update(aliases(reference))
    result = {}
    for feature in features:
        props = feature["properties"]
        # Never show test/exercise messages or cancellation notices as live hazards.
        if props.get("status") != "Actual" or props.get("messageType") == "Cancel":
            continue
        identifiers = aliases(feature) | aliases(props)
        if identifiers & superseded:
            continue
        expires = timestamp(props.get("expires"))
        ends = timestamp(props.get("ends"))
        if expires is None:
            raise ValueError("Missing alert expiry")
        valid_until = min(expires, ends) if ends is not None else expires
        if valid_until <= now:
            continue
        event = text(props.get("event"), 200)
        identifier = text(props.get("id") or feature.get("id") or props.get("@id"), 2000)
        if not event or not identifier:
            raise ValueError("Missing alert identity")
        alert = {
            "id": identifier,
            "event": event,
            "kind": alert_kind(event),
            "headline": text(props.get("headline"), 2000),
            "description": text(props.get("description")),
            "instruction": text(props.get("instruction")),
            "area": text(props.get("areaDesc"), 4000),
            "sender": text(props.get("senderName"), 300),
            "severity": text(props.get("severity"), 30) or "Unknown",
            "urgency": text(props.get("urgency"), 30) or "Unknown",
            "certainty": text(props.get("certainty"), 30) or "Unknown",
            "sentAt": timestamp(props.get("sent")),
            "effectiveAt": timestamp(props.get("effective")),
            "onsetAt": timestamp(props.get("onset")),
            "endsAt": ends,
            "expiresAt": expires,
            "validUntil": valid_until,
        }
        previous = result.get(identifier)
        if previous is None or (alert["sentAt"] or 0) >= (previous["sentAt"] or 0):
            result[identifier] = alert
    return sorted(result.values(), key=priority)


class NWSAlerts:
    def __init__(self, fetch):
        self.fetch = fetch
        self.lock = threading.Lock()
        self.cache = OrderedDict()

    def get(self, latitude, longitude):
        lat, lon = float(latitude), float(longitude)
        if (
            not math.isfinite(lat)
            or not math.isfinite(lon)
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
        ):
            raise ValueError("Invalid alert coordinates")
        point = f"{lat:.4f},{lon:.4f}"
        with self.lock:
            entry = self.cache.get(point)
            if entry is None:
                entry = {
                    "attemptedMono": None,
                    "attemptedAt": None,
                    "checkedAt": None,
                    "alerts": [],
                    "error": None,
                }
                self.cache[point] = entry
            self.cache.move_to_end(point)
            while len(self.cache) > 4:
                self.cache.popitem(last=False)
            if (
                entry["attemptedMono"] is None
                or time.monotonic() - entry["attemptedMono"] >= REFRESH_SECONDS
            ):
                entry["attemptedMono"] = time.monotonic()
                entry["attemptedAt"] = time.time()
                try:
                    raw = self.fetch(
                        "https://api.weather.gov/alerts/active?"
                        + urlencode({"point": point, "status": "actual"})
                    )
                    checked = time.time()
                    alerts = parse_alerts(raw, checked)
                    entry.update(alerts=alerts, checkedAt=checked, error=None)
                except Exception:
                    # Retain only unexpired last-known notices, and never claim all-clear on failure.
                    entry["error"] = UNAVAILABLE
            now = time.time()
            checked = entry["checkedAt"]
            stale = (
                bool(entry["error"])
                or checked is None
                or now - checked > STALE_SECONDS
                or checked > now + 60
            )
            return {
                "source": SOURCE,
                "point": {"latitude": round(lat, 4), "longitude": round(lon, 4)},
                "officialUrl": "https://forecast.weather.gov/MapClick.php?"
                + urlencode({"lat": f"{lat:.4f}", "lon": f"{lon:.4f}"}),
                "alerts": copy.deepcopy([a for a in entry["alerts"] if a["validUntil"] > now]),
                "checkedAt": checked,
                "attemptedAt": entry["attemptedAt"],
                "stale": stale,
                "error": entry["error"],
                "refreshSeconds": REFRESH_SECONDS,
            }
