import datetime as dt
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.desk=server.Desk(self.temp.name)

    def tearDown(self):
        self.desk.db.close()
        self.temp.cleanup()

    def test_demo_is_explicit_and_does_not_query_nws(self):
        self.desk.settings['weatherSource']='demo'
        with patch.object(server,'fetch_json') as fetch:
            data=self.desk.forecast()
        self.assertTrue(data['demo'])
        self.assertEqual(len(data['periods']),25)
        fetch.assert_not_called()

    def test_live_hourly_periods_and_cache(self):
        self.desk.api_key='test-session-key'
        now=dt.datetime.now(server.UTC)
        point={'properties':{'forecastHourly':'https://api.weather.gov/gridpoints/BOX/70,81/forecast/hourly'}}
        raw={'properties':{'updateTime':now.isoformat(),'periods':[
            {'startTime':(now-dt.timedelta(minutes=20)).isoformat(),'endTime':(now+dt.timedelta(minutes=40)).isoformat(),
             'shortForecast':'Chance Rain Showers','probabilityOfPrecipitation':{'value':40}},
            {'startTime':(now-dt.timedelta(hours=4)).isoformat(),'endTime':(now-dt.timedelta(hours=3)).isoformat(),
             'shortForecast':'Snow','probabilityOfPrecipitation':{'value':90}}]}}
        with patch.object(server,'fetch_json',side_effect=[point,raw]) as fetch:
            data=self.desk.forecast()
            cached=self.desk.forecast()
        self.assertFalse(data['demo'])
        self.assertFalse(data['stale'])
        self.assertEqual(data['periods'][0]['pop'],40)
        self.assertEqual(len(data['periods']),1)
        self.assertEqual(data,cached)
        self.assertEqual(fetch.call_count,2)

    def test_extra_hours_keep_a_full_rolling_window_available_between_fetches(self):
        self.desk.api_key='test-session-key'
        now=dt.datetime.now(server.UTC)
        point={'properties':{'forecastHourly':'https://api.weather.gov/gridpoints/BOX/70,81/forecast/hourly'}}
        periods=[{'startTime':(now+dt.timedelta(hours=h)).isoformat(),
                  'endTime':(now+dt.timedelta(hours=h+1)).isoformat(),
                  'shortForecast':'Mostly Clear','probabilityOfPrecipitation':{'value':0}}
                 for h in (0,13,25)]
        raw={'properties':{'updateTime':now.isoformat(),'periods':periods}}
        with patch.object(server,'fetch_json',side_effect=[point,raw]) as fetch:
            data=self.desk.forecast()
            cached=self.desk.forecast()
        self.assertEqual(len(data['periods']),2)
        self.assertGreater(data['periods'][-1]['end'],now.timestamp()+13*3600)
        self.assertEqual(data,cached)
        self.assertEqual(fetch.call_count,2)

    def test_forecast_link_cannot_leave_nws(self):
        self.desk.api_key='test-session-key'
        with patch.object(server,'fetch_json',return_value={'properties':{'forecastHourly':'https://example.com/private'}}) as fetch:
            data=self.desk.forecast()
        self.assertTrue(data['stale'])
        self.assertTrue(data['error'])
        self.assertEqual(fetch.call_count,1)

    def test_network_failure_is_unavailable_not_clear(self):
        self.desk.api_key='test-session-key'
        with patch.object(server,'fetch_json',side_effect=server.WeatherError('Cannot connect')):
            data=self.desk.forecast()
        self.assertEqual(data['periods'],[])
        self.assertIsNone(data['issuedAt'])
        self.assertTrue(data['error'])

    def test_frost_keeps_nws_sky_cover_and_point_forecast_source(self):
        self.desk.settings.update(weatherSource='noaa',latitude=42.4668,longitude=-70.9495,
                                  climateStation={'id':'194601','name':'Marblehead'})
        now=dt.datetime.now(server.UTC)
        url='https://api.weather.gov/gridpoints/BOX/74,106/forecast/hourly'
        point={'properties':{'forecastHourly':url}}
        raw={'properties':{'updateTime':now.isoformat(),'periods':[
            {'startTime':now.isoformat(),'endTime':(now+dt.timedelta(hours=1)).isoformat(),
             'shortForecast':'Areas Of Frost','probabilityOfPrecipitation':{'value':0},
             'icon':'https://api.weather.gov/icons/land/day/few?size=small'}]}}
        with patch.object(server,'fetch_json',side_effect=[point,raw]) as fetch:
            data=self.desk.forecast()
        self.assertEqual(fetch.call_args_list[0].args[0],'https://api.weather.gov/points/42.4668,-70.9495')
        self.assertEqual(data['periods'][0]['summary'],'Areas Of Frost')
        self.assertEqual(data['periods'][0]['sky'],'clear')
        self.assertEqual(data['office'],'BOX');self.assertEqual(data['hourlyUrl'],url)
        self.assertFalse(data['stale'])

    def test_only_unambiguous_nws_sky_icons_supply_fallback(self):
        for code,expected in [('skc','clear'),('few','clear'),('sct','cloud'),
                              ('bkn','cloud'),('ovc','cloud'),('wind_few','clear'),
                              ('wind_ovc','cloud'),('few,0/few,0','clear'),
                              ('few/bkn',None),('rain',None),('unknown',None)]:
            with self.subTest(code=code):
                self.assertEqual(server.nws_sky_condition('https://api.weather.gov/icons/land/night/'+code+'?size=small'),expected)
        for value in [None,12,'http://api.weather.gov/icons/land/day/skc',
                      'https://example.com/icons/land/day/skc',
                      'https://api.weather.gov.evil.example/icons/land/day/skc',
                      'https://api.weather.gov/not-icons/skc',
                      'https://api.weather.gov/icons/land/day/skc#fake','https://[bad']:
            with self.subTest(icon=value):self.assertIsNone(server.nws_sky_condition(value))

    def test_sky_preference_is_validated_and_retained(self):
        self.desk.settings_update({'skyTheme':'dawn'})
        self.assertEqual(self.desk.settings['skyTheme'],'dawn')
        with self.assertRaises(server.WeatherError):
            self.desk.settings_update({'skyTheme':'invalid'})


if __name__=='__main__':unittest.main()
