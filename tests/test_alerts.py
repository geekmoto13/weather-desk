import concurrent.futures
import copy
import datetime as dt
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nws_alerts
import server

NOW = dt.datetime(2026, 10, 22, 20, tzinfo=dt.timezone.utc).timestamp()


def iso(seconds):
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).isoformat()


def alert(identifier='a', event='Coastal Flood Advisory', **overrides):
    props = {'id': identifier, 'status': 'Actual', 'messageType': 'Alert', 'event': event,
             'sent': iso(NOW-300), 'effective': iso(NOW-300), 'onset': iso(NOW+900),
             'expires': iso(NOW+3600), 'ends': None, 'severity': 'Moderate',
             'urgency': 'Expected', 'certainty': 'Likely', 'references': [],
             'headline': 'SYNTHETIC TEST NOTICE', 'description': 'Test description.',
             'instruction': 'Test instruction.', 'areaDesc': 'Eastern Essex',
             'senderName': 'NWS Boston/Norton MA'}
    props.update(overrides)
    return {'id': 'https://api.weather.gov/alerts/'+identifier, 'properties': props}


def collection(*features):
    return {'type': 'FeatureCollection', 'features': list(features)}


class ParseTests(unittest.TestCase):
    def test_verified_empty_collection_is_valid(self):
        self.assertEqual(nws_alerts.parse_alerts(collection(), NOW), [])

    def test_warnings_before_watches_and_future_onset_is_retained(self):
        data = nws_alerts.parse_alerts(collection(alert(), alert('watch', 'Tornado Watch', severity='Extreme'),
                                                  alert('warning', 'Severe Thunderstorm Warning', severity='Severe')), NOW)
        self.assertEqual([a['kind'] for a in data], ['warning', 'watch', 'advisory'])
        self.assertEqual(data[0]['instruction'], 'Test instruction.')
        self.assertGreater(data[0]['onsetAt'], NOW)

    def test_expired_or_ended_notices_are_removed(self):
        data = collection(alert('expired', expires=iso(NOW)), alert('ended', ends=iso(NOW-1)), alert('active'))
        self.assertEqual([a['id'] for a in nws_alerts.parse_alerts(data, NOW)], ['active'])

    def test_tests_exercises_and_cancellations_are_not_live_hazards(self):
        data = collection(alert('test', status='Test'), alert('exercise', status='Exercise'),
                          alert('system', status='System'), alert('cancel', messageType='Cancel'))
        self.assertEqual(nws_alerts.parse_alerts(data, NOW), [])

    def test_cancel_and_update_references_remove_superseded_notices(self):
        cancel = alert('cancel', messageType='Cancel', references=[{'identifier': 'old'}])
        self.assertEqual(nws_alerts.parse_alerts(collection(alert('old'), cancel), NOW), [])
        update = alert('new', messageType='Update', references=[{'@id': 'https://api.weather.gov/alerts/old'}])
        self.assertEqual([a['id'] for a in nws_alerts.parse_alerts(collection(alert('old'), update), NOW)], ['new'])

    def test_duplicates_do_not_hide_distinct_alerts_for_same_event(self):
        data = nws_alerts.parse_alerts(collection(alert('one'), alert('one', sent=iso(NOW-1)), alert('two')), NOW)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['sentAt'], NOW-1)

    def test_unreadable_or_partial_response_cannot_be_an_all_clear(self):
        for raw in ({}, {'features': []}, collection({}), collection(alert(expires=None)),
                    {**collection(), 'pagination': {'next': 'https://api.weather.gov/alerts?cursor=next'}}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                nws_alerts.parse_alerts(raw, NOW)

    def test_timezone_aware_dates_and_nullable_fields(self):
        raw = collection(alert(sent='2026-10-22T16:00:00-04:00', onset=None, headline=None, instruction=None))
        data = nws_alerts.parse_alerts(raw, NOW)[0]
        self.assertEqual(data['sentAt'], NOW)
        self.assertIsNone(data['onsetAt'])
        self.assertEqual(data['instruction'], '')
        self.assertIsNone(nws_alerts.timestamp('2026-10-22T16:00:00'))


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.clock = NOW
        self.mono = 100.
        self.wall_patch = patch.object(nws_alerts.time, 'time', side_effect=lambda: self.clock)
        self.mono_patch = patch.object(nws_alerts.time, 'monotonic', side_effect=lambda: self.mono)
        self.wall_patch.start()
        self.mono_patch.start()
        self.fetch = Mock(return_value=collection(alert()))
        self.feed = nws_alerts.NWSAlerts(self.fetch)

    def tearDown(self):
        self.wall_patch.stop()
        self.mono_patch.stop()

    def get(self):
        return self.feed.get(42.4668, -70.9495)

    def advance(self, seconds):
        self.clock += seconds
        self.mono += seconds

    def test_single_point_request_and_one_minute_cache(self):
        first = self.get()
        self.advance(59)
        self.assertEqual(self.get(), first)
        self.fetch.assert_called_once()
        query = parse_qs(urlsplit(self.fetch.call_args.args[0]).query)
        self.assertEqual(query, {'point': ['42.4668,-70.9495'], 'status': ['actual']})
        self.assertFalse(first['stale'])
        self.advance(1)
        self.get()
        self.assertEqual(self.fetch.call_count, 2)

    def test_failure_preserves_unexpired_notices_with_stale_status(self):
        first = self.get()
        self.advance(60)
        self.fetch.side_effect = RuntimeError('offline')
        result = self.get()
        self.assertTrue(result['stale'])
        self.assertTrue(result['error'])
        self.assertEqual(result['checkedAt'], first['checkedAt'])
        self.assertEqual(len(result['alerts']), 1)
        self.get()
        self.assertEqual(self.fetch.call_count, 2)
        self.advance(3600)
        self.assertEqual(self.get()['alerts'], [])
        self.assertTrue(self.get()['error'])

    def test_failure_without_history_is_unavailable_not_empty_success(self):
        self.fetch.side_effect = RuntimeError('offline')
        result = self.get()
        self.assertTrue(result['stale'])
        self.assertIsNone(result['checkedAt'])
        self.assertTrue(result['error'])

    def test_recovery_clears_error_and_removes_old_hazards(self):
        self.get()
        self.advance(60)
        self.fetch.side_effect = RuntimeError('offline')
        self.get()
        self.advance(60)
        self.fetch.side_effect = None
        self.fetch.return_value = collection()
        result = self.get()
        self.assertFalse(result['stale'])
        self.assertIsNone(result['error'])
        self.assertEqual(result['alerts'], [])

    def test_new_coordinates_never_borrow_previous_locations_notices(self):
        self.get()
        self.fetch.return_value = collection()
        result = self.feed.get(42.36, -71.06)
        self.assertEqual(result['alerts'], [])
        self.assertEqual(result['point'], {'latitude': 42.36, 'longitude': -71.06})
        self.assertEqual(len(self.get()['alerts']), 1)
        self.assertEqual(self.fetch.call_count, 2)

    def test_concurrent_clients_share_a_single_fetch(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.get(), range(4)))
        self.fetch.assert_called_once()
        self.assertEqual([r['alerts'] for r in results], [results[0]['alerts']]*4)

    def test_callers_cannot_modify_the_cached_alerts(self):
        result = self.get()
        result['alerts'][0]['event'] = 'changed'
        self.assertEqual(self.get()['alerts'][0]['event'], 'Coastal Flood Advisory')

    def test_alerts_do_not_need_ambient_keys_and_do_not_send_them(self):
        with tempfile.TemporaryDirectory() as folder:
            desk = server.Desk(folder)
            try:
                with patch.object(server, 'fetch_json', return_value=collection()) as fetch:
                    result = desk.alerts()
                self.assertFalse(result['stale'])
                self.assertEqual(desk.api_key, '')
                self.assertEqual(set(parse_qs(urlsplit(fetch.call_args.args[0]).query)), {'point', 'status'})
            finally:
                desk.db.close()


if __name__ == '__main__':
    unittest.main()
