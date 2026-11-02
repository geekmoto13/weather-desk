"""Location identity, US date boundaries, missing public fields and daily comparisons."""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfoNotFoundError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import timezones
from climate import BOSTON, BostonClimate, daily_almanac
from climate_rain import rainfall_records
from historical_days import day_bounds
from historical_days import summarize_station
from public_weather import normalize_public, PublicWeather
from temperature_calendar import TemperatureCalendar, temperature_class, station_temperature
from weather_location import LocationResolver, grid_center
from test_climate import series, records

UTC=dt.timezone.utc
SITE={'id':'USW00093134','sid':'USW00093134 6','name':'LOS ANGELES DOWNTOWN',
      'label':'Los Angeles Downtown','timezone':'America/Los_Angeles','available':True,
      'sourceUrl':'https://www.weather.gov/wrh/Climate?wfo=lox'}

def point(zone='America/Los_Angeles',office='LOX',radar='KSOX'):
    return {'timeZone':zone,'cwa':office,'radarStation':radar,
            'observationStations':'https://api.weather.gov/gridpoints/'+office+'/155,45/stations',
            'relativeLocation':{'properties':{'city':'Los Angeles','state':'CA'}}}

def wait_calendar(calendar):
    deadline=time.monotonic()+3
    while any(s['loading'] for s in calendar.states.values()) and time.monotonic()<deadline:time.sleep(.005)
    assert not any(s['loading'] for s in calendar.states.values())

class LocationTests(unittest.TestCase):
    def test_grid_centers_and_invalid_input(self):
        self.assertEqual(grid_center('fn42'),(42.5,-71.0))
        lat,lon=grid_center('FN42lg');self.assertAlmostEqual(lat,42.2708333333);self.assertAlmostEqual(lon,-71.0416666667)
        lat8,lon8=grid_center('FN42lg12');self.assertTrue(42.25<lat8<42.30);self.assertTrue(-71.084<lon8<-71.0)
        for value in ('ZZ99','FN4','FN42yy','FN42lg1234'):
            with self.assertRaises(ValueError):grid_center(value)

    def test_us_search_preserves_zip_and_excludes_other_countries(self):
        fetch=Mock(return_value={'results':[{'country_code':'US','name':'Lynn','admin1':'Massachusetts','latitude':42.4,'longitude':-70.9},
                                           {'country_code':'GB','name':'Lynn','latitude':52,'longitude':0}]})
        result=LocationResolver(fetch).search('01902')
        self.assertEqual(len(result['matches']),1)
        self.assertEqual(parse_qs(urlsplit(fetch.call_args.args[0]).query)['name'],['01902'])
        self.assertEqual(result['matches'][0]['name'],'Lynn, Massachusetts')

    def test_grid_does_not_need_geocoder_and_ambiguous_city_returns_choices(self):
        fetch=Mock();resolver=LocationResolver(fetch)
        self.assertEqual(len(resolver.search('FN42lg')['matches']),1);fetch.assert_not_called()
        fetch.return_value={'results':[{'country_code':'US','name':'Springfield','admin1':state,'latitude':lat,'longitude':-90}
            for state,lat in [('Illinois',39.8),('Missouri',37.2)]]}
        self.assertEqual(len(resolver.search('Springfield')['matches']),2)

    def test_nearest_climate_must_have_all_elements_and_verified_normals(self):
        now=dt.date.today().isoformat()
        def row(name,sid,lat,ranges=3):
            return {'name':name,'sids':[sid],'ll':[-118.24,lat],'valid_daterange':[['1900-01-01',now]]*ranges}
        fetch=Mock(side_effect=[{'meta':[row('RAIN ONLY','USC00000001 6',34.05,1),row('MISSING NORMAL','USC00000002 6',34.052),row(SITE['name'],SITE['sid'],34.06)]},
            {'meta':{'name':'MISSING NORMAL'},'data':[[now,'M','M','M','0.1']]},
            {'meta':{'name':SITE['name']},'data':[[now,'70','50','60','0.1']]}])
        site=LocationResolver(fetch).climate(34.05,-118.24,'America/Los_Angeles','LOX')
        self.assertEqual(site['id'],SITE['id'])
        params=json.loads(parse_qs(urlsplit(fetch.call_args.args[0]).query)['params'][0])
        self.assertTrue(all(e['normal']==91 for e in params['elems']))

    def test_resolve_central_zone_radar_and_inland_tides(self):
        resolver=LocationResolver(Mock());resolver.point=Mock(return_value=point('America/Chicago','MPX','KMPX'))
        resolver.climate=Mock(return_value={**SITE,'timezone':'America/Chicago'})
        resolver.tide=Mock(return_value={'tideStation':'','tideName':''})
        profile=resolver.resolve(44.98,-93.26,'Minneapolis, Minnesota')
        self.assertEqual(profile['radarStation'],'KMPX');self.assertEqual(profile['timezone'],'America/Chicago')
        self.assertEqual(profile['tideStation'],'');self.assertTrue(profile['locationConfigured'])

    def test_public_coverage_requires_noaa_grid_url(self):
        resolver=LocationResolver(Mock(return_value={'properties':{**point(),'observationStations':'https://other.example/stations'}}))
        with self.assertRaises(ValueError):resolver.point(34,-118)

class LocalDateTests(unittest.TestCase):
    def test_stock_windows_handles_midnight_and_dst_in_three_regions(self):
        with patch.object(timezones,'ZoneInfo',side_effect=ZoneInfoNotFoundError):
            stamp=dt.datetime(2026,10,23,5,tzinfo=UTC).timestamp()
            self.assertEqual(timezones.local_date(stamp,'America/New_York'),dt.date(2026,10,23))
            self.assertEqual(timezones.local_date(stamp,'America/Chicago'),dt.date(2026,10,23))
            self.assertEqual(timezones.local_date(stamp,'America/Los_Angeles'),dt.date(2026,10,22))
            for zone in ('America/New_York','America/Chicago','America/Los_Angeles'):
                a,b=day_bounds(dt.date(2026,3,8),zone);self.assertEqual(b-a,23*3600)
                a,b=day_bounds(dt.date(2026,11,1),zone);self.assertEqual(b-a,25*3600)
            a,b=day_bounds(dt.date(2026,3,8),'America/Phoenix');self.assertEqual(b-a,24*3600)

    def test_calendar_climate_and_rain_keep_selected_station_identity(self):
        day=dt.date(2026,1,4);raw=series(day);rec=records()
        raw['meta']['name']=rec['meta']['name']=SITE['name']
        result=daily_almanac(raw,rec,day,SITE)
        self.assertEqual(result['stationId'],SITE['id']);self.assertEqual(result['timezone'],SITE['timezone'])
        with self.assertRaises(ValueError):daily_almanac(raw,rec,day)
        rain={'meta':{'name':SITE['name']},'data':[['2000',[['1.20',0]],[['2.40',0]]]]}
        self.assertEqual(rainfall_records(rain,day,SITE)['stationId'],SITE['id'])

class PublicObservationTests(unittest.TestCase):
    def test_units_and_missing_fields_do_not_turn_into_calm_or_zero_rain(self):
        raw={'properties':{'timestamp':dt.datetime.now(UTC).isoformat(),
              'temperature':{'value':20,'unitCode':'wmoUnit:degC'},'dewpoint':{'value':10,'unitCode':'wmoUnit:degC'},
              'windSpeed':{'value':None,'unitCode':'wmoUnit:km_h-1'},'windGust':{'value':38.88,'unitCode':'wmoUnit:km_h-1'},
              'relativeHumidity':{'value':40,'unitCode':'wmoUnit:percent'},
              'barometricPressure':{'value':102000,'unitCode':'wmoUnit:Pa'}}}
        result=normalize_public(raw,server.feels_like)
        self.assertEqual(result['tempF'],68);self.assertIsNone(result['windMph']);self.assertIsNone(result['windDeg'])
        self.assertAlmostEqual(result['gustMph'],24.158912,places=5)
        self.assertIsNone(result['pressureHpa']);self.assertIsNone(result['rainDayMm']);self.assertIsNone(result['maxGustMph'])
        raw['properties']['seaLevelPressure']={'value':102000,'unitCode':'wmoUnit:Pa'}
        self.assertEqual(normalize_public(raw,server.feels_like)['pressureHpa'],1020)
        raw['properties']['temperature']['qualityControl']='qc:Z'
        self.assertIsNone(normalize_public(raw,server.feels_like)['tempF'])

    def test_fallback_skips_nearest_station_without_recent_temperature(self):
        now=dt.datetime.now(UTC).isoformat()
        stations={'features':[{'properties':{'stationIdentifier':sid,'name':sid},'geometry':{'coordinates':[-118,lat]}}
                              for sid,lat in [('KONE',34),('KTWO',34.1)]]}
        def observation(temp):return {'features':[{'properties':{'timestamp':now,'temperature':{'value':temp,'unitCode':'wmoUnit:degC'},'precipitationLastHour':{'value':0,'unitCode':'wmoUnit:mm','qualityControl':'V'}}}]}
        resolver=Mock();resolver.point.return_value=point()
        fetch=Mock(side_effect=[stations,observation(None),observation(20)])
        with tempfile.TemporaryDirectory() as folder:
            public=PublicWeather(folder,fetch,resolver,server.feels_like,server.pressure_trend)
            public.snapshot({'latitude':34,'longitude':-118})
            deadline=time.monotonic()+3
            while next(iter(public.states.values()))['loading'] and time.monotonic()<deadline:time.sleep(.005)
            result=public.snapshot({'latitude':34,'longitude':-118})
            self.assertEqual(result['stationId'],'KTWO');self.assertFalse(result['demo']);self.assertEqual(result['staleAfterSeconds'],5400)

class TemperatureCalendarTests(unittest.TestCase):
    def test_threshold_is_inclusive_and_missing_never_near_normal(self):
        for mean,normal,expected in [(61,60,'at'),(59,60,'at'),(61.1,60,'above'),(58.9,60,'below'),(0,0,'at'),(None,60,'missing'),(60,None,'missing')]:
            self.assertEqual(temperature_class(mean,normal)[0],expected)

    def test_partial_station_span_cannot_make_a_temperature_color(self):
        summary={'coverage':{'fullSpan':False},'high':{'value':80},'low':{'value':60},'points':[]}
        high,low,mean,note=station_temperature(summary)
        self.assertIsNone(mean);self.assertIn('incomplete',note)

    def test_noaa_month_uses_daily_mean_explicit_normal_and_pending_today(self):
        raw={'meta':{'name':SITE['name']},'data':[['2026-10-01',['70',' '],['50',' '],'58'],
            ['2026-10-02',['60',' '],['40',' '],'52'],['2026-10-03',['M',' '],['40',' '],'52']]}
        fetch=Mock(return_value=raw)
        with tempfile.TemporaryDirectory() as folder,patch('temperature_calendar.local_date',return_value=dt.date(2026,10,4)):
            cal=TemperatureCalendar(folder,fetch);cal.snapshot('2026-10',SITE,SITE['timezone']);wait_calendar(cal)
            result=cal.snapshot('2026-10',SITE,SITE['timezone'])
            self.assertEqual([d['status'] for d in result['days'][:5]],['above','below','missing','pending','future'])
            self.assertEqual(result['days'][0]['meanF'],60)
            params=json.loads(parse_qs(urlsplit(fetch.call_args.args[0]).query)['params'][0])
            self.assertEqual(params['elems'][2],{'name':'avgt','normal':91,'prec':3})
            restarted=TemperatureCalendar(folder,Mock(side_effect=AssertionError('cache should prevent fetch')))
            restarted.snapshot('2026-10',SITE,SITE['timezone']);wait_calendar(restarted)
            self.assertFalse(restarted.snapshot('2026-10',SITE,SITE['timezone'])['error'])

    def test_changed_location_does_not_reuse_other_station_normals(self):
        fetch=Mock(side_effect=[{'meta':{'name':SITE['name']},'data':[['2026-01-01',['60',' '],['40',' '],'50']]},
                               {'meta':{'name':'Minnesota'},'data':[['2026-01-01',['20',' '],['0',' '],'0']]}])
        with tempfile.TemporaryDirectory() as folder,patch('temperature_calendar.local_date',return_value=dt.date(2026,2,1)):
            cal=TemperatureCalendar(folder,fetch);cal.snapshot('2026-01',SITE,SITE['timezone']);wait_calendar(cal)
            other={**SITE,'id':'USC00218450','sid':'USC00218450 6','name':'Minnesota','timezone':'America/Chicago'}
            cal.snapshot('2026-01',other,other['timezone']);wait_calendar(cal)
            result=cal.snapshot('2026-01',other,other['timezone'])
            self.assertEqual(result['stationId'],other['id']);self.assertEqual(result['days'][0]['normalF'],0)

    def test_future_and_invalid_months_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            cal=TemperatureCalendar(folder,Mock())
            for value in ('2026-13','1969-12','3000-01','../../private','2026-1'):
                with self.assertRaises(ValueError):cal.snapshot(value,SITE,SITE['timezone'])

    def test_personal_daily_temperature_is_saved_and_reused_after_restart(self):
        date=dt.date(2026,1,1);start,end=day_bounds(date,SITE['timezone'])
        points=[{'timestamp':start+i*300,'tempF':50+(i%25)/10} for i in range(288)]
        raw={'meta':{'name':SITE['name']},'data':[['2026-01-01',['80',' '],['40',' '],'50']]}
        fetch=Mock(return_value=raw);page=Mock(return_value=points)
        with tempfile.TemporaryDirectory() as folder,patch('temperature_calendar.local_date',return_value=dt.date(2026,1,2)):
            cal=TemperatureCalendar(folder,fetch)
            cal.snapshot('2026-01',SITE,SITE['timezone'],'AA:BB:CC:DD:EE:FF',page);wait_calendar(cal)
            result=cal.snapshot('2026-01',SITE,SITE['timezone'],'AA:BB:CC:DD:EE:FF',page)
            self.assertEqual(result['days'][0]['meanF'],51.2);self.assertEqual(result['days'][0]['status'],'above')
            page.assert_called_once()
            restarted=TemperatureCalendar(folder,Mock(side_effect=AssertionError('Normals already cached')))
            no_import=Mock(side_effect=AssertionError('Completed station day already saved'))
            restarted.snapshot('2026-01',SITE,SITE['timezone'],'AA:BB:CC:DD:EE:FF',no_import);wait_calendar(restarted)
            result=restarted.snapshot('2026-01',SITE,SITE['timezone'],'AA:BB:CC:DD:EE:FF',no_import)
            self.assertEqual(result['days'][0]['meanF'],51.2);no_import.assert_not_called()

    def test_saved_colors_remain_visible_when_noaa_is_unavailable_after_restart(self):
        raw={'meta':{'name':SITE['name']},'data':[['2026-01-01',['60',' '],['40',' '],'45']]}
        with tempfile.TemporaryDirectory() as folder,patch('temperature_calendar.local_date',return_value=dt.date(2026,1,2)):
            cal=TemperatureCalendar(folder,Mock(return_value=raw))
            cal.snapshot('2026-01',SITE,SITE['timezone']);wait_calendar(cal)
            raw_path=Path(folder)/'temperature-calendar'/f"{SITE['id']}-2026-01-noaa.json"
            saved=json.loads(raw_path.read_text());saved['fetchedAt']=0;raw_path.write_text(json.dumps(saved))
            restarted=TemperatureCalendar(folder,Mock(side_effect=OSError('offline')))
            restarted.snapshot('2026-01',SITE,SITE['timezone']);wait_calendar(restarted)
            result=restarted.snapshot('2026-01',SITE,SITE['timezone'])
            self.assertTrue(result['error']);self.assertEqual(result['days'][0]['status'],'above')
            self.assertEqual(result['days'][0]['meanF'],50);self.assertEqual(result['days'][1]['status'],'pending')

class SourceAndPersistenceTests(unittest.TestCase):
    def test_ambient_pacific_alias_uses_matching_local_annual_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            desk=server.Desk(folder);desk.settings['timezone']='America/Los_Angeles'
            desk.api_key='example-api';desk.app_key='example-app';desk.mac='AA:BB:CC:DD:EE:FF'
            desk.cache={'timestamp':time.time(),'stationTimezone':'US/Pacific','rainYearMm':None,'rainMonthMm':0}
            with patch.object(desk.annual_rain,'ensure') as ensure,patch.object(desk.annual_rain,'result',return_value={'status':'building'}):
                self.assertEqual(desk.annual()['status'],'building');ensure.assert_called_once()
            desk.db.close()

    def test_default_no_key_uses_noaa_and_source_selection_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            desk=server.Desk(folder)
            with patch.object(desk.public_weather,'snapshot',return_value={'source':'noaa','demo':False}) as public:
                self.assertEqual(desk.weather()['source'],'noaa');public.assert_called_once()
            desk.api_key='saved-api';desk.app_key='saved-app';self.assertEqual(desk.weather_mode(),'ambient')
            desk.settings_update({'weatherSource':'noaa'});self.assertEqual(desk.weather_mode(),'noaa')
            other=server.Desk(folder);self.assertEqual(other.settings['weatherSource'],'noaa')
            self.assertEqual(desk.annual()['status'],'public')
            desk.settings_update({'weatherSource':'demo'});self.assertTrue(desk.weather()['demo'])
            desk.db.close();other.db.close()

    def test_resolved_profile_saves_local_climate_and_invalidates_old_state(self):
        with tempfile.TemporaryDirectory() as folder:
            desk=server.Desk(folder)
            profile={'latitude':34.05,'longitude':-118.24,'location':'Los Angeles, California','timezone':SITE['timezone'],
                     'radarStation':'KSOX','climateStation':SITE,'locationConfigured':True,'tideStation':'','tideName':''}
            desk.location_resolver.resolve=Mock(return_value=profile)
            result=desk.location_resolve({'latitude':34.05,'longitude':-118.24})
            desk.settings_update({**profile,'locationToken':result['locationToken']})
            other=server.Desk(folder)
            self.assertEqual(other.climate.station['id'],SITE['id']);self.assertEqual(other.rain_records.station['id'],SITE['id'])
            self.assertEqual(other.past_days.climate_station['id'],SITE['id']);self.assertEqual(other.settings['radarStation'],'KSOX')
            self.assertEqual(desk.location_resolver.resolve.call_count,1)
            desk.db.close();other.db.close()

if __name__=='__main__':unittest.main()
