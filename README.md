This build includes an Easter egg. Can you find it?

# Shannon's Weather Desk — version 1.3.0 (build 36-test)
screenshot: ![Screenshot](docs/screenshot.png)

A local weather postcard, radar, forecast beacon, climate calendar, historical
comparisons, sky times, tides and Radio & Space. Use an Ambient-connected personal
station or nearby public observations. The layout and data features are retained.

## What's new in 1.3.0

- **Network access is back.** Start the dashboard with `START-WEATHER-DESK-LAN.bat` (or add `--lan`)
  to open it from a phone or tablet on your home network. See **Network access
  (optional)** at the end of this file. The normal start files remain local-only.
- **Radio & Space has been rewritten.** It uses the full page width, with compact
  HF and reception panels, a large propagation map, NOAA solar imagery and
  measurement plots. HF forecasts are repaired, destinations can be picked by
  name or prefix without a grid, there are two prediction models (KC2G and
  VOACAP), and recent PSK Reporter reception reports are shown. Details are in
  the **Radio & Space** section.
- **Experimental temperature calendar.** Calendar colours now use the historical
  middle third for each date instead of a fixed ±1°F band. Details are in
  **Readings and comparisons**.
- **Overview layout and 48-hour outlook.** The Berkeley beacon gets a larger,
  horizontal building and text area. The smaller radar sits above a new 48-hour
  forecast made of four rolling 12-hour windows. Each shows the prevailing
  description, the range of hourly temperatures in °F/°C, the highest hourly
  precipitation chance and the highest hourly wind speed. This is not a 12-hour
  rain probability or a gust forecast. Missing numbers stay unavailable and
  incomplete windows withhold ranges. The outlook is separate from station
  readings and from the 12-hour beacon calculation. It uses NOAA/NWS hourly forecasts in the US, Open-Meteo / DWD ICON for UK locations and Met Éireann for Ireland. Met Éireann's current point feed has no probability field, so its precipitation chance stays unavailable.
  The same cached feed serves the beacon and the outlook; no extra key is
  needed. Large warnings or long source descriptions can make the page scroll
  rather than clip content.

## Berkeley Building beacon rhyme

The complete rhyme is always visible beneath the building, with the line for
the current forecast highlighted:

> Steady blue, clear view.  
> Flashing blue, clouds due.  
> Steady red, rain ahead.  
> Flashing red, snow instead.

No line is highlighted when the forecast is unavailable. The highlight remains
visible when reduced motion is enabled, so the signal is readable without
blinking. The beacon continues to use the prevailing outlook over the next
twelve hours; snow includes wintry precipitation such as freezing rain.

## Public stations must report measured rainfall

Every automatically selected public station, including explicit CWOP and
NOAA/airport modes, now needs a recent usable temperature **and a measured
precipitation amount**. The nearest qualifying CWOP station within 75 km is
preferred. Official fallbacks must meet the same requirement. An explicit dry
zero counts; missing, negative, non-finite, boolean, rejected or questioned rain
does not. Rain weather codes alone do not qualify. API precipitation reports are
the evidence used; the feeds do not provide a complete hardware inventory.

CWOP rainfall uses accepted MADIS per-sensor quality flags. US NWS precipitation
also requires an accepted quality flag and supported units. Airport METAR rain
amounts come from AWC's numerical 1/3/6/24-hour fields in inches, converted to mm.
Old saved temperature-only station choices are rejected at startup. If no
qualifying station can be found, the dashboard explains this and retries; it
does not fall back to a station without reported rainfall. Existing connected
personal Ambient stations retain their priority in Automatic mode.

The source caption shows the station's reported precipitation and its period.
Rolling totals are not converted to calendar-day, monthly or yearly counters.
A rain gauge does not guarantee that every calendar total is supplied by the
public feed. In the UK, the separately named Environment Agency gauge continues
supplying the calendar rainfall ledger where available; the selected weather
station's own reported rain remains separately labelled in the source caption.

## Start and update

1. Close the old Weather Desk console. Keep the old application folder as a backup.
2. Extract this download into a new folder. Copy the **private** folder from your
   existing **US edition** into the new application folder to keep your
   saved connection, settings and history. Keep US and UK copies separate.
3. Double-click **START-WEATHER-DESK.bat**. It prepares the included Python on the first run,
   checks the runtime, and opens **http://127.0.0.1:8765/**. Keep the console open.
4. On a fresh installation, choose your location in Settings. Leave readings on
   **Automatic**, or connect your Ambient station with its API key, application
   key and optional MAC. **Remember this station** saves the connection locally.

The bundled option is for **Windows 10/11, Intel/AMD x64**. No pip, Node or extra
Python packages are needed. If you prefer your existing Python 3.10+, use
**START-WITH-INSTALLED-PYTHON.bat**. These are explicit choices; the app prints
which Python it is using.

**CHECK-WEATHER-DESK-RUNTIME.bat** verifies bundled files and tests app imports,
TLS and SQLite. Keep its full output if startup fails. For an installed-Python
check, run `weather-desk.bat --installed-python --diagnose` in a terminal.

On macOS/Linux/Raspberry Pi, use Python 3.10+ and run:

```sh
python3 -I -X utf8 -B launch_weather.py --installed-python --open
```

The `.command` launcher does the same on macOS. Press Ctrl+C or close the console
to stop. Internet access is needed for weather feeds; saved history stays local.

## Startup implementation

The Windows shortcuts share **weather-desk.bat**. Its built-in PowerShell
command checks/extracts the included `runtime/python-windows-x64.zip` and verifies
all 39 files before Python starts. Later launches reuse those files. Preparation
does not access the network or change system PATH, registry or PowerShell policy.
`runtime-prepare.ps1` is the readable source of that one inline command.

**launch_weather.py** adds its own application directory to Python's import path
before loading any local module. For bundled Windows Python it registers the
private DLL directory before SSL/SQLite imports and retains the handle. Python's
upstream `_pth` file is now unchanged. Runtime checksums have one implementation
in the Windows preparation step; the former `windows_runtime.py` helper is gone.
Native binaries are unchanged from the official CPython 3.14.9 x64 distribution.
The archive retains the full upstream licence and a provenance record.

## Saved data and sharing

Everything personal stays in **private/**: credentials, preferences, observations
and caches. Windows encrypts remembered keys for your Windows account with DPAPI;
other systems use an owner-only local file. A session-only connection is not
saved. **Forget station** removes the saved connection.

Share the clean application ZIP with testers. Each person chooses their location
and keys. Keep your working private folder to yourself. The server uses a public
asset allowlist and binds to loopback by default. Images and copied weather text
include the source/time and omit keys and MAC addresses.

The page checks weather every minute and radar every five minutes. Feed-specific
caches prevent each page refresh from becoming a new upstream request. Completed
monthly rain counters and historical days remain saved after restarting.

## US location, forecast and climate

Location search accepts a ZIP, city/state or 4-, 6- or 8-character Maidenhead grid.
It sets coordinates, local timezone, forecast/alert area, radar, a nearby climate
reference and a tide prediction station within 100 km. Grids use their centre.
Inland locations can leave tides off. The initial example is Lynn, Massachusetts;
existing preferences keep their selected location and Boston ThreadEx reference.

The climate reference is the nearest qualifying daily station found by the
resolver, with long temperature/precipitation records and verified 1991–2020
daily normals. **RCC-ACIS** supplies the NOAA/NWS climate archive. Normals and
historical maximum/minimum precipitation use matching to-date windows; incomplete
historical windows are excluded and record ties retain all matching years.
The official public fallback is a nearby reporting **NOAA/NWS** station.

The Berkeley Building-inspired beacon uses the separate **NWS hourly point
forecast** for saved coordinates. The condition occupying most of the next 12 h
sets the light: steady blue clear/mostly clear, blinking blue clouds, steady red
rain, blinking red snow/ice. Precipitation needs ≥30% chance when supplied.
Exact ties prefer snow/ice, rain, cloud, then clear. Frost can use the NWS sky
icon for clear/cloud cover and does not imply snowfall. Missing, stale or
incomplete 12-hour coverage leaves the beacon unlit. The source/office and link
are shown. Reduced-motion settings are respected.

The top alert strip uses active NOAA/NWS point warnings, watches and advisories.
It removes expired/cancelled/test notices and labels outages. NOAA radar refreshes
every five minutes. Coastal tides are **predicted** high/low times and feet above
MLLW; predictions omit weather-driven water-level changes. Astronomical rise/set
times are approximate. Music is not included.

## Readings and comparisons

- Air temperature, feels like, dew point and humidity retain their existing
  calculations. Missing readings stay unavailable. A solar reading does not
  establish cloud cover; day/night colours use calculated solar altitude.
- The wind compass shows direction around its outer ring and speed in its centre.
  Beaufort is an equivalent of the reported speed. The formal scale's averaging
  and installation requirements can differ from a home station. Daily max gust
  uses a reported daily maximum; it is not inferred from a single gust.
- Pressure tendency compares an observation about three hours earlier, within
  30 minutes. A net change beyond ±0.5 hPa is rising/falling; otherwise steady.
  That neutral band is a display choice. QNH is labelled separately from sea-level
  pressure; different stations/datums are not combined into a trend.
- Ambient's annual rain counter is preferred. If missing, YTD adds each completed
  monthly station counter to the current month-to-date counter. Missing months
  are requested individually and saved. Missing data never contributes zero.
  The ledger's observed, normal and record windows all use the same cutoff date:
  month-to-date and **January 1 through today**. No June-to-June season is mixed in.
- The completed-day temperature mean is **(daily high + daily low) / 2**.
  The experimental calendar compares it with same-date 1991–2020 empirical
  thirds: red above the 66⅔ percentile, blue below the 33⅓ percentile, green
  between them (inclusive). Click a date for both cutoffs in °F/°C, the
  reference-year count, the observed mean, the normal/calculated average and the
  exact departure. This is an adaptation of
  [NOAA CPC's outlook categories](https://www.cpc.ncep.noaa.gov/products/predictions/erf_info.php?outlook=814&var=t),
  **not an official NOAA daily tolerance or a weather forecast**. For each
  reference station and month/day, paired highs and lows give one daily mean per
  year; the 1/3 and 2/3 quantiles use linear interpolation at `(n - 1) * p`
  (Hyndman–Fan type 7). Ties can narrow the band, and neighbouring dates are
  never substituted. At least 80% of the possible years need valid pairs: 24/30
  ordinarily, 7/8 for February 29 (a smaller sample, explicitly labelled). That
  threshold is our choice. Missing or accumulated observations, reversed
  high/low pairs and duplicate dates are excluded. Colours use unrounded values;
  the popup rounds for readability. Today, incomplete days and dates with
  insufficient historical coverage stay uncoloured, and a positive departure
  from normal can still be green, because a normal is a mean while the green
  range describes the historical distribution. The first calendar load reads
  the 30-year reference in the background and saves derived cutoffs in
  `private/temperature-calendar/terciles`, isolated by station and method;
  restarts reuse them and failed loads retry after five minutes. Colours from
  the old ±1°F method are never imported, and history is never filled with
  zeros. US records come from [RCC-ACIS](https://docs.rcc-acis.org/acisws/).
- Climate references and live observation stations are named separately. Nearby
  sites and reporting-day conventions can differ. NOAA precipitation includes
  liquid water and melted snow; an unheated personal gauge can miss snowfall.
- **Past days** compares the selected historical date with the same climate date.
  A connected personal station's history is fetched at the normal API pace and
  saved. In public mode, historical daily observations come from the named
  climate archive, not a reconstruction from sparse live reports.

Automatic mode uses a connected Ambient station first. Otherwise it tries the
nearest usable **CWOP/APRSWXNET** report within 75 km via **NOAA MADIS**, then the
edition's official public provider. An explicit CWOP or official-provider choice
can override saved Ambient keys. Actual station, distance and observation time
are shown. Personal readings are stale after 15 minutes; public reports after
90 minutes. CWOP checks are cached for ten minutes with outage backoff.

MADIS quality checks apply independently to each sensor. Accepted descriptors
are C/S/V/G; rejected/questioned/bad or unchecked values stay unavailable. Rolling
24-hour rain is labelled separately and never added into calendar rain counters.
Public stations often omit solar, UV, daily max gust and monthly/yearly counters.
The MADIS guest route has no service guarantee; larger deployments should arrange
an appropriate distribution feed instead of increasing viewer polling.

## Radio & Space

The Radio & Space screen uses the available width: compact HF and reception
panels, a large propagation map, and solar imagery and NOAA measurement plots.

**NOAA SWPC** supplies SFI, daily sunspot number, planetary A, Kp, observed
geomagnetic scale, solar-wind speed, Bz/Bt, GOES X-ray class, R/S/G scales,
bulletins and D-layer absorption. Daily values show their observation date; they
commonly describe the previous UTC day. Missing or stale values remain labelled,
never converted to zero or an all-clear. **KC2G** supplies the MUF/grey-line and
foF2/NVIS maps. MUF is for 3000 km hops; foF2 is a critical frequency for
near-vertical paths. D-RAP shows absorption, not a continuous LUF. Map
timestamps and legends remain intact.

- **HF forecasts repaired:** KC2G's live response has 25 columns. The previous
  parser demanded exactly 24 and rejected every band. The 24 UTC positions are
  now retained, with model-generation checks. Errors appear next to the table
  instead of being hidden inside the model notes.
- **No grid required for a listed destination:** 340 current DXCC entities and
  511 regional locations are searchable by name or prefix. DXCC locations are
  representative points; choose a city for a more specific path. Only the
  Custom Maidenhead choice requires a locator. Your TX location is taken from
  saved weather-station settings; the dashboard calculates its grid for you.
- **Two automated prediction models:** KC2G uses its current ionospheric model
  for circuit predictions on 10/12/15/17/20/30/40/60/80/160 m. VOACAP, via
  HamClock.com's compatible service, gives typical monthly planning
  probabilities. Select the model above the table or in Path setup. Context and
  caches are kept separate by station, destination, mode, power and provider.
  KC2G recalculates at most every 15 minutes per path; VOACAP once per hour.
  Restarting can reuse fresh saved predictions.
- **KC2G assumptions:** path setup saves destination, mode, power, antenna gains
  and receiving-noise environment. Reliability columns cover now, +3 h and +6 h;
  SNR describes the first displayed hour. SSB assumptions are 3000 Hz/6 dB, CW
  500 Hz/0 dB and FT8 50 Hz/−3 dB. The lowest usable band is the lowest tested
  frequency reaching 50% predicted circuit reliability, not a measured
  continuous lowest usable frequency.
- **VOACAP assumptions:** this backend requires whole-watt power (1–1500 W);
  fractional watts remain available in KC2G. The nine-band protocol covers
  80, 60, 40, 30, 20, 17, 15, 12 and 10 m, with fixed 0 dBi isotropic antennas
  and a 3° minimum takeoff angle. Backend noise and mode SNR thresholds apply.
  The service returns reliability, not SNR, and does not provide 160 m; those
  fields stay blank with an explanation. KC2G's gain and noise controls are
  disabled for VOACAP. Neither model guarantees a contact. Green/amber/red band
  cells mean ≥75%, 50–74% and <50% modelled reliability; grey means unavailable.
  These display bands are separate from NOAA's storm-severity colours.
- **NOAA colours:** level 0 green, 1 yellow, 2 gold, 3 orange, 4 red, 5 dark red.
  Current R/S/G, 24-hour maximums, forecast probabilities and forecast G are
  separate. Missing or stale data is grey. Kp colours follow the G thresholds;
  X-ray colours follow the corresponding instantaneous flare thresholds. SFI,
  sunspots, solar wind and Bz keep their physical units rather than inventing
  NOAA severity scales for them. The Kp forecast says partial when few forecast
  intervals are available.
- **NOAA imagery and plots:** switch between SUVI 195 Å, northern aurora and
  CCOR-1 corona imagery (five-minute checks; original image times retained).
  X-ray and proton plots use six hours of actual NOAA observations; Kp shows the
  past 24 hours. Charts are plotted locally from NOAA JSON data, keep gaps, use
  logarithmic axes for flux and show sample values on pointer hover. Unavailable
  images or data have a clear status and an official product link.
- **PSK Reporter:** recent digital reception reports for your station callsign,
  or an override in Path setup. Shows receiving stations, band/mode and time,
  with receiver grid, frequency and reported SNR in the tooltip. At most 100
  reports from the last hour are requested. Queries are paced across callsigns
  to at least five minutes, and the pacing survives restarts. This reads
  reports; it does not transmit or submit spots. No reports does not mean a
  band is closed, and digital reception is not proof of an SSB opening.

The tab checks locally once a minute while open. Source caches range from two
minutes to an hour; KC2G maps refresh at 15 minutes and D-RAP at five minutes.
Small public-feed caches and path preferences persist in private/radio/. The
selected HF provider receives approximate TX/RX coordinates and station model
settings; PSK Reporter receives only the requested callsign. Ambient credentials
and weather-station identifiers are never sent to radio providers. VOACAP
Online's website is not scraped: its full controls open separately, with
copyable generated grids for the same path. The automatic table uses a
HamClock-compatible backend. For a self-hosted compatible service, optionally
set `WEATHER_DESK_VOACAP_URL` to its HTTPS endpoint, or HTTP on localhost. Use
community services for personal reference and respect their availability.

Sources: [NOAA SWPC](https://www.spaceweather.gov/),
[KC2G](https://prop.kc2g.com/hfprop/planner) ([acknowledgments](https://prop.kc2g.com/acknowledgments/)),
[NOAA D-RAP](https://www.spaceweather.gov/products/d-region-absorption-predictions-d-rap),
[HamClock.com](https://www.hamclock.com/credits.html) ([terms](https://www.hamclock.com/terms.html)),
[HamClock backend protocol](https://github.com/openhamclock/hamclock-standards),
[PSK Reporter developer documentation](https://pskreporter.info/pskdev.html),
[AD1C Country Files](https://www.country-files.com/cty/cty.dat) and the
[VOACAP regional-location catalogue](https://www.voacap.com/hf/).
Destination facts were retrieved November 8, 2026 UTC. No third-party app or
propagation engine code is bundled.

## Maintenance and verification

This cleanup consolidates startup, fixes the isolated-Python application path,
removes duplicate runtime checks and obsolete styles, and formats Python/JS for
maintenance. Old release-by-release setup notes and the unused sample image have
been removed. Existing private data formats and dashboard features are retained.

See **VALIDATION.md** for checks and their limits. A native Windows launch cannot
be exercised in the Linux build environment. Local tests include isolated import
and real server startup; they are not a claim of Windows execution.

Primary references: https://docs.python.org/3.14/using/windows.html ·
https://ambientweather.docs.apiary.io/ · https://www.weather.gov/documentation/services-web-api ·
https://www.rcc-acis.org/ · https://madis.ncep.noaa.gov/madis_cwop.shtml ·
https://madis.ncep.noaa.gov/madis_sfc_qc.shtml · https://api.tidesandcurrents.noaa.gov/api/prod/

## Free satellite lightning

NOAA GOES lightning is automatic in the US edition. No account or API key is needed. GOES-East or GOES-West is selected for your location.

Sun and Moon share one card, preserving all previous sky readings. The
Lightning nearby card uses official satellite flash positions and UTC times.
Distance (mi/km) and bearing are calculated from your saved dashboard location.
The closest accepted flash is selected within 75 km, over a 45-minute
observation window **ending at the displayed satellite data time**. Satellite
flashes can be inside clouds and do not establish exact ground-strike points.

NOAA GOES-19 supplies eastern locations and GOES-18 western locations, selected
at 105°W. The US adapter's supported area is within 52° north/south and between
180°W and 45°W. Areas outside that support remain map-only. NOAA's catalogue
is checked every minute; data older than five minutes are marked delayed.
The first load downloads a full observation window (typically tens of MB),
with progress visible. Later polls download new 20-second granules and reuse
old files; restarts reuse the local raw-file cache.

UK/Ireland uses EUMETSAT LI Level-2 Lightning Flashes, EO:EUM:DAT:0691, via
the Data Store's ten-minute archive body files. In Settings, enter a free
account's consumer key and secret from https://api.eumetsat.int/api-key/ .
These are separate from Ambient keys and may be saved with the same Windows
account encryption or private-file protection. OAuth bearer tokens remain in
server memory and renew automatically; no credentials reach the browser or
external map. The catalogue is checked every five minutes. Actual observation
time is shown; files older than 30 minutes are marked delayed. There is no
paid lightning subscription. Old Weatherbit credentials, if present in a copied
private folder, are ignored; no Weatherbit calls are made.

All NetCDF processing uses a locally bundled h5wasm worker, version 0.10.3.
No extra Python packages, DLLs, CDN scripts or changes to the bundled runtime
are needed. CF scale/offset, fill values, UTC units and quality flags are read.
NOAA quality flag zero is accepted. EUMETSAT flash confidence above 0.5 is
excluded (zero is highest confidence); missing/geolocation/radiometric input
warnings keep empty results provisional. Files with missing columns or invalid
arrays fail visibly. A partial window says nearest loaded flash. No detections
requires all window files decoded, complete catalogue coverage and no quality
warnings, with fresh data. Failures and old observations remain explicit.

Raw satellite files are cached privately, with a 160 MiB/three-hour retention
target. The server limits simultaneous downloads to three, accepts only
catalogue-registered IDs and bounds each file to 32 MiB. It never fetches
arbitrary URLs supplied by the browser.

The Blitzortung map remains a separately attributed live embed; its activity
can differ from the satellite observations. Its restricted raw feed is never
scraped. Third-party notices are in third-party/h5wasm-LICENSE.txt.

Sources: https://www.ncei.noaa.gov/products/goes-terrestrial-weather-abi-glm
and https://user.eumetsat.int/resources/user-guides/mtg-li-level-2-data-guide .
Contains modified EUMETSAT Meteosat data, 2026, under CC BY 4.0; see
https://www.eumetsat.int/legal-framework/data-policy .

## Nearby personal stations and recalled pressure

Settings → More nearby personal stations accepts an optional **Weather
Underground data API key**, separately from an Ambient key or a WU station
upload key. Use your own appropriately entitled WU account. Public observation
mode checks the closest qualifying WU station against qualifying CWOP stations
within 75 km. A connected Ambient station retains priority in Automatic mode;
Official mode does not query either personal-station network.

WU location metadata and observations must pass the provider's QC flag.
Current readings must be no more than 60 minutes old and include a usable
measured daily precipitation total. Zero is valid; missing rain is not zero.
The directory returns up to ten candidates and is cached for one hour;
observations are checked every ten minutes. A provider failure retains other
available sources. A WU key does not prove station calibration or exposure.
No cross-network identity match is assumed from a similar name or location.

CWOP now requests an earlier, QC-accepted pressure observation from MADIS when
its local history cannot supply the three-hour comparison. The request is
relative to the current observation's timestamp, and accepts a point within
30 minutes of the target. Station ID, coordinates and pressure type must
match; QNH and sea-level pressure are not mixed. Current weather remains
visible while the history request runs. Archive failures preserve current
readings, collect local history and retry after 30 minutes. Cached comparisons
survive app restarts. No personal weather station connection is necessary.

WU can retrieve its selected station's recent rapid history with the same
key. Interval pressure ranges are labelled approximate (≈); if the range
crosses a direction threshold, the tendency is labelled uncertain. Saved
instantaneous observations take priority over interval summaries. A missing
history response is not replaced by another station's pressure.

Today's WU rain is the station's midnight-to-current counter. It is never
relabelled as a rolling 24-hour, monthly or yearly amount. The UK/Ireland
calendar rain ledger continues using its separate named official rain gauge.
Complete monthly/YTD WU rain reconstruction is not part of this integration.
Saved WU keys use the app's existing private credential store (Windows DPAPI
on Windows). Keys are not returned by APIs or included in cards and exports.
Forgetting the key disables WU selection and invalidates pending results.

Official API references:
- https://www.wunderground.com/pws-api/utility/search/near
- https://www.wunderground.com/pws-api/observations/current-conditions
- https://developer.weather.com/docs/openapi/pws-recent-history-1-day-rapid-2-0
- https://madis.ncep.noaa.gov/madis_cwop.shtml

## Twilight, time since rain, and ten-minute Beaufort

The Sun & Moon card now shows the current sky stage: Daylight, Civil twilight,
Nautical twilight, Astronomical twilight, or Night. Twilight also says dawn or
dusk. Stages use the calculated geometric solar altitude at the saved location
and the current time: apparent sunrise/set at approximately −0.833°, then
−6°, −12° and −18°. Cloud cover does not change the astronomical stage. The
calculation works when a weather station is disconnected and at polar locations.

The rainfall heading shows elapsed 24-hour days since recorded rain. A connected
Ambient station uses its reported lastRain timestamp when available. A native
rain timestamp may include seconds while an Ambient observation is rounded to
the minute. Public UK/Ireland ledgers use their same named EA or Met Éireann
rain gauge and validated interval history. Other public sources retain observed
wet bounds and continuous dry coverage per station in the private folder.
Any positive measured amount counts at that source's reporting resolution;
forecast/radar rain and missing observations do not count as measured rainfall.

An approximate sign means the last rain was bounded by a reporting interval.
A ≥ sign means only a minimum dry period is supported; earlier rainfall or gaps
prevent an exact date. The counter ends at its observation/gauge coverage time,
so it does not accumulate unobserved dry days while a source is offline. Hover
or focus the rain-age badge for its source, last wet time and coverage. Cached
station choices and source changes never share rain histories.

Beaufort now uses a ten-minute scalar mean, excluding gusts, with no correction
for sensor height. The compass continues showing the latest reported wind.
Ambient's windspdmph_avg10m is preferred. Weather Underground's documented
current ten-minute mean and UK/Ireland METAR ten-minute convention are used
where supplied. The Met Éireann hourly wind_speed_mean is a one-hour mean;
its Beaufort input is separately calculated from ten complete, consecutive
one-minute wind_speed means at the selected station. A missing/rejected minute
prevents that calculation. Its source and window end are retained.

Where there is no native ten-minute mean, a time-weighted scalar estimate may
be calculated from at least three actual reports covering the whole ten-minute
window, with no gap over 5½ minutes. It is explicitly labelled an estimate.
CWOP requests a small 20-minute history only around the selected station, with
per-variable QC and station/location checks. A station reporting every fifteen
minutes cannot establish a ten-minute mean: Beaufort stays unavailable rather
than using its instantaneous wind or gust. Screen, copied report and PNG use
the same mean-based Beaufort calculation.

References:
- https://aa.usno.navy.mil/faq/RST_defs
- https://www.met.ie/forecasts/marine-inland-lakes/beaufort-scale
- https://ambientweather.com/support/aw-misc/
- https://www.caa.co.uk/publication/download/12602
- https://opendata2.met.ie/edr/collections/observations-swob-nrt-1min?f=json
- https://opendata2.met.ie/edr/collections/observations-swob-nrt-60min?f=json

## Network access (optional)

By default the dashboard listens on this computer only. To open it from a phone or
tablet on your home network, start it with `START-WEATHER-DESK-LAN.bat` (or add `--lan`). The console
lists addresses such as `http://192.168.1.50:8765/`. There is no password, so use
this only on a network you trust, and allow Python through Windows Firewall on
Private networks only. `--allow-host NAME` adds an extra computer name.

If you use your own installed Python 3.10+, start `START-WITH-INSTALLED-PYTHON-LAN.bat`
instead, which does the same with that Python.
