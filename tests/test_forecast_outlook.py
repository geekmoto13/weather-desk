import datetime as dt
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class NWSOutlookTests(unittest.TestCase):
    def test_full_horizon_temperature_conversion_and_cached_request(self):
        with tempfile.TemporaryDirectory() as folder:
            desk=server.Desk(folder);desk.settings['weatherSource']='noaa'
            now=dt.datetime.now(server.UTC)
            raw={'properties':{'updateTime':now.isoformat(),'periods':[
                {'startTime':(now+dt.timedelta(hours=i)).isoformat(),'endTime':(now+dt.timedelta(hours=i+1)).isoformat(),
                 'shortForecast':'Clear','temperature':0,'temperatureUnit':'C','windSpeed':'5 to 10 mph',
                 'probabilityOfPrecipitation':{'value':0}}
                for i in range(52)]}}
            point={'properties':{'forecastHourly':'https://api.weather.gov/gridpoints/BOX/70,81/forecast/hourly'}}
            try:
                with patch.object(server,'fetch_json',side_effect=[point,raw]) as fetch:
                    f=desk.forecast();cached=desk.forecast()
                self.assertGreaterEqual(f['periods'][-1]['end'],now.timestamp()+48*3600)
                self.assertEqual(f['periods'][0]['tempF'],32)
                self.assertEqual(f['periods'][0]['windMph'],10)
                self.assertEqual(f['periods'][0]['pop'],0)
                self.assertEqual(f,cached);self.assertEqual(fetch.call_count,2)
            finally:desk.db.close()

if __name__=='__main__':unittest.main()
