"""NWS precipitation units, QC, station ordering and old-cache rejection."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from public_weather import PublicWeather, normalize_public
from rain_observations import has_measured_rain
from server import feels_like, pressure_trend

SETTINGS = {"latitude": 42.46, "longitude": -70.95}


def observation(amount=0, unit="wmoUnit:mm", qc="V"):
    return {"properties": {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "temperature": {"value": 12, "unitCode": "wmoUnit:degC"},
        "precipitationLastHour": {"value": amount, "unitCode": unit, "qualityControl": qc},
    }}


class PublicRainTests(unittest.TestCase):
    def test_nws_supported_units_are_converted_to_mm_without_calendar_totals(self):
        for amount, unit, expected in [(0, "wmoUnit:mm", 0), (.002, "wmoUnit:m", 2), (1, "wmoUnit:in", 25.4)]:
            with self.subTest(unit=unit):
                current = normalize_public(observation(amount, unit), feels_like)
                self.assertEqual(current["rainLastHourMm"], expected)
                self.assertTrue(has_measured_rain(current))
                self.assertIsNone(current["rainDayMm"])
                self.assertIsNone(current["rainYearMm"])
                self.assertIsNone(current["rainRateMmHr"])

    def test_rejected_questioned_unchecked_and_missing_rain_cannot_qualify(self):
        for qc in ("X", "Q", "B", "Z", "T", "", None):
            with self.subTest(qc=qc):
                self.assertFalse(has_measured_rain(normalize_public(observation(qc=qc), feels_like)))
        for amount in (None, True, -1, float("nan"), float("inf")):
            with self.subTest(amount=amount):
                self.assertFalse(has_measured_rain(normalize_public(observation(amount), feels_like)))
        self.assertFalse(has_measured_rain(normalize_public(observation(0, "unknown"), feels_like)))

    def test_three_and_six_hour_reports_keep_their_own_period(self):
        raw = observation(None)
        raw["properties"]["precipitationLast3Hours"] = {"value": 2, "unitCode": "wmoUnit:mm", "qualityControl": "qc:C"}
        raw["properties"]["precipitationLast6Hours"] = {"value": 3, "unitCode": "wmoUnit:mm", "qualityControl": "S"}
        current = normalize_public(raw, feels_like)
        self.assertEqual(current["rainLast3hMm"], 2)
        self.assertEqual(current["rainLast6hMm"], 3)
        self.assertIsNone(current["rainDayMm"])

    def test_nearer_temperature_only_station_is_skipped(self):
        stations = {"features": [
            {"properties": {"stationIdentifier": name, "name": name}, "geometry": {"coordinates": [-70.95, lat]}}
            for name, lat in [("KONE", 42.46), ("KTWO", 42.48)]
        ]}
        resolver = Mock()
        resolver.point.return_value = {"observationStations": "stations"}
        fetch = Mock(side_effect=[stations, {"features": [observation(None)]}, {"features": [observation(0)]}])
        with tempfile.TemporaryDirectory() as folder:
            public = PublicWeather(folder, fetch, resolver, feels_like, pressure_trend)
            state = {"payload": None, "loading": True}
            public._load(public._key(SETTINGS), SETTINGS, state)
            self.assertEqual(state["payload"]["stationId"], "KTWO")
            self.assertEqual(state["payload"]["current"]["rainLastHourMm"], 0)

    def test_old_cache_without_rain_is_never_shown_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            key = "42.4600,-70.9500"
            path = Path(folder) / "public-weather" / (hashlib.sha256(key.encode()).hexdigest()[:20] + ".json")
            path.parent.mkdir()
            path.write_text(json.dumps({"locationKey": key, "stationId": "KOLD", "current": {"timestamp": time.time(), "tempF": 60}, "points": []}))
            provider = PublicWeather(folder, Mock(), Mock(), feels_like, pressure_trend)
            with patch("public_weather.threading.Thread"):
                result = provider.snapshot(SETTINGS)
            self.assertFalse(result.get("current"))
            self.assertIsNone(result.get("stationId"))


if __name__ == "__main__":
    unittest.main()
