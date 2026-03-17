"""Station registry and market question parser for the Weather strategy.

Responsibilities:
  1. STATION_REGISTRY: ICAO-keyed dict of StationInfo for known Polymarket stations
  2. classify_weather_market(): regex parser that extracts city, date, buckets
  3. parse_temp_buckets(): outcome string → TempBucket list

All functions are pure (no side effects, no I/O). Designed to be called
from the strategy scan loop without risk of exceptions breaking the loop.
"""

import re
import logging
from datetime import datetime, timezone, date as date_type
from typing import Dict, List, Optional, Tuple

from engine.strategies.weather_models import (
    StationInfo, StationType, TempBucket, WeatherMarketClassification,
)

logger = logging.getLogger(__name__)


# ---- Station Registry ----

STATION_REGISTRY: Dict[str, StationInfo] = {
    "KLGA": StationInfo(
        station_id="KLGA", city="New York City", state="NY",
        latitude=40.7769, longitude=-73.8740, elevation_ft=22,
        timezone="America/New_York", station_type=StationType.COASTAL,
        wunderground_slug="us/ny/new-york-city/KLGA",
        aliases=["NYC", "New York", "New York City", "LaGuardia"],
    ),
    "KORD": StationInfo(
        station_id="KORD", city="Chicago", state="IL",
        latitude=41.9742, longitude=-87.9073, elevation_ft=672,
        timezone="America/Chicago", station_type=StationType.INLAND,
        wunderground_slug="us/il/chicago/KORD",
        aliases=["Chicago", "O'Hare", "ORD"],
    ),
    "KLAX": StationInfo(
        station_id="KLAX", city="Los Angeles", state="CA",
        latitude=33.9416, longitude=-118.4085, elevation_ft=128,
        timezone="America/Los_Angeles", station_type=StationType.COASTAL,
        wunderground_slug="us/ca/los-angeles/KLAX",
        aliases=["Los Angeles", "LA", "LAX"],
    ),
    "KATL": StationInfo(
        station_id="KATL", city="Atlanta", state="GA",
        latitude=33.6407, longitude=-84.4277, elevation_ft=1026,
        timezone="America/New_York", station_type=StationType.INLAND,
        wunderground_slug="us/ga/atlanta/KATL",
        aliases=["Atlanta", "ATL"],
    ),
    "KDFW": StationInfo(
        station_id="KDFW", city="Dallas", state="TX",
        latitude=32.8998, longitude=-97.0403, elevation_ft=607,
        timezone="America/Chicago", station_type=StationType.INLAND,
        wunderground_slug="us/tx/dallas/KDFW",
        aliases=["Dallas", "DFW", "Dallas-Fort Worth", "Dallas Fort Worth"],
    ),
    "KMIA": StationInfo(
        station_id="KMIA", city="Miami", state="FL",
        latitude=25.7959, longitude=-80.2870, elevation_ft=9,
        timezone="America/New_York", station_type=StationType.COASTAL,
        wunderground_slug="us/fl/miami/KMIA",
        aliases=["Miami", "MIA"],
    ),
    "KDEN": StationInfo(
        station_id="KDEN", city="Denver", state="CO",
        latitude=39.8561, longitude=-104.6737, elevation_ft=5431,
        timezone="America/Denver", station_type=StationType.INLAND,
        wunderground_slug="us/co/denver/KDEN",
        aliases=["Denver", "DEN"],
    ),
    "KSFO": StationInfo(
        station_id="KSFO", city="San Francisco", state="CA",
        latitude=37.6213, longitude=-122.3790, elevation_ft=13,
        timezone="America/Los_Angeles", station_type=StationType.COASTAL,
        wunderground_slug="us/ca/san-francisco/KSFO",
        aliases=["San Francisco", "SF", "SFO"],
    ),
}

# Build reverse lookup: lowercased alias → station_id
_ALIAS_TO_STATION: Dict[str, str] = {}
for _sid, _info in STATION_REGISTRY.items():
    _ALIAS_TO_STATION[_info.city.lower()] = _sid
    for _alias in _info.aliases:
        _ALIAS_TO_STATION[_alias.lower()] = _sid


def lookup_station(city_name: str) -> Optional[StationInfo]:
    """Resolve a city name or alias to a StationInfo. Case-insensitive."""
    sid = _ALIAS_TO_STATION.get(city_name.strip().lower())
    if sid:
        return STATION_REGISTRY.get(sid)
    return None


# Dynamic station cache for globally discovered cities
_DYNAMIC_STATIONS: Dict[str, StationInfo] = {}

# Expanded global city coordinates for common weather market cities
_GLOBAL_CITY_COORDS: Dict[str, dict] = {
    "london": {"lat": 51.5074, "lon": -0.1278, "tz": "Europe/London", "state": "UK"},
    "hong kong": {"lat": 22.3193, "lon": 114.1694, "tz": "Asia/Hong_Kong", "state": "HK"},
    "buenos aires": {"lat": -34.6037, "lon": -58.3816, "tz": "America/Argentina/Buenos_Aires", "state": "AR"},
    "tokyo": {"lat": 35.6762, "lon": 139.6503, "tz": "Asia/Tokyo", "state": "JP"},
    "sydney": {"lat": -33.8688, "lon": 151.2093, "tz": "Australia/Sydney", "state": "AU"},
    "paris": {"lat": 48.8566, "lon": 2.3522, "tz": "Europe/Paris", "state": "FR"},
    "dubai": {"lat": 25.2048, "lon": 55.2708, "tz": "Asia/Dubai", "state": "AE"},
    "singapore": {"lat": 1.3521, "lon": 103.8198, "tz": "Asia/Singapore", "state": "SG"},
    "toronto": {"lat": 43.6532, "lon": -79.3832, "tz": "America/Toronto", "state": "CA"},
    "mumbai": {"lat": 19.0760, "lon": 72.8777, "tz": "Asia/Kolkata", "state": "IN"},
    "berlin": {"lat": 52.5200, "lon": 13.4050, "tz": "Europe/Berlin", "state": "DE"},
    "moscow": {"lat": 55.7558, "lon": 37.6173, "tz": "Europe/Moscow", "state": "RU"},
    "seoul": {"lat": 37.5665, "lon": 126.9780, "tz": "Asia/Seoul", "state": "KR"},
    "bangkok": {"lat": 13.7563, "lon": 100.5018, "tz": "Asia/Bangkok", "state": "TH"},
    "houston": {"lat": 29.7604, "lon": -95.3698, "tz": "America/Chicago", "state": "TX"},
    "phoenix": {"lat": 33.4484, "lon": -112.0740, "tz": "America/Phoenix", "state": "AZ"},
    "philadelphia": {"lat": 39.9526, "lon": -75.1652, "tz": "America/New_York", "state": "PA"},
    "san antonio": {"lat": 29.4241, "lon": -98.4936, "tz": "America/Chicago", "state": "TX"},
    "san diego": {"lat": 32.7157, "lon": -117.1611, "tz": "America/Los_Angeles", "state": "CA"},
    "seattle": {"lat": 47.6062, "lon": -122.3321, "tz": "America/Los_Angeles", "state": "WA"},
    "boston": {"lat": 42.3601, "lon": -71.0589, "tz": "America/New_York", "state": "MA"},
    "nashville": {"lat": 36.1627, "lon": -86.7816, "tz": "America/Chicago", "state": "TN"},
    "washington": {"lat": 38.9072, "lon": -77.0369, "tz": "America/New_York", "state": "DC"},
    "washington dc": {"lat": 38.9072, "lon": -77.0369, "tz": "America/New_York", "state": "DC"},
    "las vegas": {"lat": 36.1699, "lon": -115.1398, "tz": "America/Los_Angeles", "state": "NV"},
    "portland": {"lat": 45.5155, "lon": -122.6789, "tz": "America/Los_Angeles", "state": "OR"},
    "minneapolis": {"lat": 44.9778, "lon": -93.2650, "tz": "America/Chicago", "state": "MN"},
    "detroit": {"lat": 42.3314, "lon": -83.0458, "tz": "America/Detroit", "state": "MI"},
    "austin": {"lat": 30.2672, "lon": -97.7431, "tz": "America/Chicago", "state": "TX"},
    "charlotte": {"lat": 35.2271, "lon": -80.8431, "tz": "America/New_York", "state": "NC"},
    "el paso": {"lat": 31.7619, "lon": -106.4850, "tz": "America/Denver", "state": "TX"},
    "memphis": {"lat": 35.1495, "lon": -90.0490, "tz": "America/Chicago", "state": "TN"},
    "new orleans": {"lat": 29.9511, "lon": -90.0715, "tz": "America/Chicago", "state": "LA"},
    "tampa": {"lat": 27.9506, "lon": -82.4572, "tz": "America/New_York", "state": "FL"},
    "orlando": {"lat": 28.5383, "lon": -81.3792, "tz": "America/New_York", "state": "FL"},
    "st. louis": {"lat": 38.6270, "lon": -90.1994, "tz": "America/Chicago", "state": "MO"},
    "st louis": {"lat": 38.6270, "lon": -90.1994, "tz": "America/Chicago", "state": "MO"},
    "pittsburgh": {"lat": 40.4406, "lon": -79.9959, "tz": "America/New_York", "state": "PA"},
    "milwaukee": {"lat": 43.0389, "lon": -87.9065, "tz": "America/Chicago", "state": "WI"},
    "sacramento": {"lat": 38.5816, "lon": -121.4944, "tz": "America/Los_Angeles", "state": "CA"},
}


def get_or_create_station(city_name: str) -> Optional[StationInfo]:
    """Look up station in registry or create a dynamic one for global cities.

    Priority: STATION_REGISTRY > _DYNAMIC_STATIONS > _GLOBAL_CITY_COORDS > None
    """
    # Check static registry first
    station = lookup_station(city_name)
    if station:
        return station

    # Check dynamic cache
    key = city_name.strip().lower()
    if key in _DYNAMIC_STATIONS:
        return _DYNAMIC_STATIONS[key]

    # Check global coordinates table
    coords = _GLOBAL_CITY_COORDS.get(key)
    if coords:
        station_id = f"DYN_{key.upper().replace(' ', '_')[:10]}"
        info = StationInfo(
            station_id=station_id,
            city=city_name.strip().title(),
            state=coords["state"],
            latitude=coords["lat"],
            longitude=coords["lon"],
            elevation_ft=0,
            timezone=coords["tz"],
            station_type=StationType.COASTAL,
            wunderground_slug="",
            aliases=[city_name.strip()],
        )
        _DYNAMIC_STATIONS[key] = info
        # Also register in STATION_REGISTRY so forecasts can find it
        STATION_REGISTRY[station_id] = info
        _ALIAS_TO_STATION[key] = station_id
        logger.info(f"Dynamic station created: {station_id} ({city_name}) @ {coords['lat']},{coords['lon']}")
        return info

    return None


def get_all_stations() -> List[StationInfo]:
    """Return all registered stations (static + dynamic)."""
    return list(STATION_REGISTRY.values())


# ---- Date Parsing ----

# Month name/abbreviation → number
_MONTH_MAP: Dict[str, int] = {
    "january": 1, "jan": 1, "february": 2, "feb": 2,
    "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6,
    "july": 7, "jul": 7, "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def _parse_date(text: str) -> Optional[date_type]:
    """Extract a date from question text.

    Supports:
      - "March 13, 2026"  / "March 13 2026"
      - "Mar 13, 2026"
      - "March 13" (assumes current or next year)
      - "3/13/2026" / "3-13-2026"
    """
    # Pattern 1: "Month DD, YYYY" or "Month DD YYYY" or "Month DD"
    # Use finditer to try all matches (avoid false match on "be 43" before "March 14")
    for m in re.finditer(
        r'\b(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2})(?:\s*,?\s*(?P<year>\d{4}))?\b',
        text,
    ):
        month_str = m.group("month").lower()
        month_num = _MONTH_MAP.get(month_str)
        if month_num:
            day = int(m.group("day"))
            year = int(m.group("year")) if m.group("year") else None
            if year is None:
                now = datetime.now(timezone.utc)
                year = now.year
                try:
                    candidate = date_type(year, month_num, day)
                except ValueError:
                    continue
                if candidate < now.date():
                    year += 1
            try:
                return date_type(year, month_num, day)
            except ValueError:
                continue

    # Pattern 2: "M/D/YYYY" or "M-D-YYYY"
    m = re.search(r'\b(?P<m>\d{1,2})[/\-](?P<d>\d{1,2})[/\-](?P<y>\d{4})\b', text)
    if m:
        try:
            return date_type(int(m.group("y")), int(m.group("m")), int(m.group("d")))
        except ValueError:
            return None

    return None


# ---- City/Location Extraction ----

# Build sorted alias list (longest first for greedy matching)
_SORTED_ALIASES: List[Tuple[str, str]] = sorted(
    [(alias.lower(), sid) for sid, info in STATION_REGISTRY.items() for alias in [info.city] + info.aliases],
    key=lambda x: -len(x[0]),
)


def _extract_city(text: str) -> Optional[str]:
    """Find the best-matching city/alias in the question text. Case-insensitive.

    Returns the station_id if found, None otherwise.
    Longest-match-first prevents "New York" matching before "New York City".
    """
    text_lower = text.lower()
    for alias, sid in _SORTED_ALIASES:
        if alias in text_lower:
            return sid
    return None


# ---- Bucket Parsing ----

# Patterns for individual bucket outcome strings
_BUCKET_PATTERNS = [
    # "40F or below" / "40 F or below" / "40°F or below" / "40 or below"
    re.compile(
        r'^(?P<val>\d+)\s*°?\s*[Ff]?\s*or\s+(?:below|lower|less)',
        re.IGNORECASE,
    ),
    # "47F or higher" / "47 F or above" / "47°F or higher" / "47 or above"
    re.compile(
        r'^(?P<val>\d+)\s*°?\s*[Ff]?\s*or\s+(?:above|higher|more|greater)',
        re.IGNORECASE,
    ),
    # "41-42F" / "41 - 42 F" / "41-42°F" / "41 to 42 F" / "41–42F" (en-dash)
    re.compile(
        r'^(?P<lo>\d+)\s*°?\s*[Ff]?\s*[\-–to]+\s*(?P<hi>\d+)\s*°?\s*[Ff]?$',
        re.IGNORECASE,
    ),
    # "41-42" (no F, just numbers with dash)
    re.compile(
        r'^(?P<lo>\d+)\s*[\-–]\s*(?P<hi>\d+)$',
    ),
]


def parse_single_bucket(outcome: str, token_id: str) -> Optional[TempBucket]:
    """Parse one outcome string into a TempBucket.

    Returns None if the outcome string doesn't match any known bucket pattern.
    """
    outcome = outcome.strip()

    # Pattern: "X or below"
    m = _BUCKET_PATTERNS[0].match(outcome)
    if m:
        return TempBucket(
            label=outcome,
            token_id=token_id,
            lower_bound=None,
            upper_bound=float(m.group("val")),
        )

    # Pattern: "X or higher"
    m = _BUCKET_PATTERNS[1].match(outcome)
    if m:
        return TempBucket(
            label=outcome,
            token_id=token_id,
            lower_bound=float(m.group("val")),
            upper_bound=None,
        )

    # Pattern: "X-Y F" or "X to Y"
    m = _BUCKET_PATTERNS[2].match(outcome)
    if m:
        lo, hi = float(m.group("lo")), float(m.group("hi"))
        return TempBucket(
            label=outcome, token_id=token_id,
            lower_bound=min(lo, hi), upper_bound=max(lo, hi),
        )

    # Pattern: "X-Y" (bare numbers)
    m = _BUCKET_PATTERNS[3].match(outcome)
    if m:
        lo, hi = float(m.group("lo")), float(m.group("hi"))
        return TempBucket(
            label=outcome, token_id=token_id,
            lower_bound=min(lo, hi), upper_bound=max(lo, hi),
        )

    return None


def parse_temp_buckets(
    outcomes: List[str],
    token_ids: List[str],
) -> Tuple[List[TempBucket], List[str]]:
    """Parse all outcome strings for a weather market into TempBuckets.

    Returns:
      (buckets, errors) — buckets is the successfully parsed list,
      errors lists unparseable outcome strings.
    """
    if len(outcomes) != len(token_ids):
        return [], [f"outcome/token count mismatch: {len(outcomes)} vs {len(token_ids)}"]

    buckets = []
    errors = []
    for outcome, tid in zip(outcomes, token_ids):
        bucket = parse_single_bucket(outcome, tid)
        if bucket:
            buckets.append(bucket)
        else:
            errors.append(f"unparseable: {outcome!r}")

    return buckets, errors


def validate_buckets(buckets: List[TempBucket]) -> Optional[str]:
    """Validate that a set of buckets forms a coherent, contiguous set.

    Checks:
      1. At least 2 buckets
      2. One lower-open bucket (e.g. "40F or below")
      3. One upper-open bucket (e.g. "47F or higher")
      4. No duplicate token_ids
      5. Contiguous coverage: each bucket's upper_bound + 1 == next bucket's lower_bound

    Returns None if valid, or an error string describing the problem.
    """
    if len(buckets) < 2:
        return f"too_few_buckets ({len(buckets)})"

    has_lower_open = any(b.is_lower_open for b in buckets)
    has_upper_open = any(b.is_upper_open for b in buckets)
    if not has_lower_open:
        return "missing_lower_open_bucket"
    if not has_upper_open:
        return "missing_upper_open_bucket"

    # Check for duplicate token_ids
    tids = [b.token_id for b in buckets]
    if len(tids) != len(set(tids)):
        return "duplicate_token_ids"

    # Contiguous coverage check: sort by effective lower bound, verify gaps
    def sort_key(b: TempBucket) -> float:
        if b.lower_bound is None:
            return -1e9
        return b.lower_bound

    sorted_b = sorted(buckets, key=sort_key)
    for i in range(len(sorted_b) - 1):
        cur = sorted_b[i]
        nxt = sorted_b[i + 1]
        # Current bucket must have an upper bound (except it shouldn't be the last)
        if cur.upper_bound is None:
            # upper-open bucket should be last after sorting; if it's not, overlap
            return f"bucket_overlap: upper-open bucket {cur.label!r} is not last"
        if nxt.lower_bound is None:
            # lower-open bucket should be first; if it appears later, overlap
            return f"bucket_overlap: lower-open bucket {nxt.label!r} is not first"
        # For whole-degree Fahrenheit buckets: upper + 1 == next lower
        gap = nxt.lower_bound - cur.upper_bound
        if gap > 1:
            return f"bucket_gap: {cur.label!r} ends at {cur.upper_bound}, {nxt.label!r} starts at {nxt.lower_bound}"
        if gap < 1:
            return f"bucket_overlap: {cur.label!r} upper={cur.upper_bound} overlaps {nxt.label!r} lower={nxt.lower_bound}"

    return None


# ---- Market Question Classification ----

# Patterns to detect weather/temperature markets
_WEATHER_PATTERNS = [
    # "Highest temperature in NYC on March 13, 2026?"
    re.compile(
        r'(?:highest|high|max|maximum)\s+temp(?:erature)?\s+in\s+(?P<city>.+?)\s+on\s+',
        re.IGNORECASE,
    ),
    # "What will the high temperature be in Chicago on March 15?"
    re.compile(
        r'(?:what\s+will\s+(?:the\s+)?)?high\s+temp(?:erature)?\s+(?:be\s+)?in\s+(?P<city>.+?)\s+on\s+',
        re.IGNORECASE,
    ),
    # "NYC high temperature March 13"
    re.compile(
        r'(?P<city>[A-Za-z\s\'.]+?)\s+high\s+temp(?:erature)?\s+',
        re.IGNORECASE,
    ),
    # "Temperature in NYC on March 13" (less specific)
    re.compile(
        r'temp(?:erature)?\s+in\s+(?P<city>.+?)\s+on\s+',
        re.IGNORECASE,
    ),
    # "What will the temperature be in Denver on March 18, 2026?"
    re.compile(
        r'(?:what\s+will\s+(?:the\s+)?)?temp(?:erature)?\s+(?:be\s+)?in\s+(?P<city>.+?)\s+on\s+',
        re.IGNORECASE,
    ),
    # "NYC daily high on March 13"
    re.compile(
        r'(?P<city>[A-Za-z\s\'.]+?)\s+daily\s+high\s+',
        re.IGNORECASE,
    ),
]


def classify_weather_market(
    question: str,
    condition_id: str,
    outcomes: List[str],
    token_ids: List[str],
) -> Tuple[Optional[WeatherMarketClassification], Optional[str]]:
    """Attempt to classify a Polymarket question as a weather temperature market.

    Args:
        question: the market question text
        condition_id: Polymarket condition ID
        outcomes: list of outcome strings (e.g. ["40F or below", "41-42F", ...])
        token_ids: list of corresponding token IDs

    Returns:
        (classification, None) on success
        (None, rejection_reason) on failure

    Pure function — no side effects, no I/O. Safe to call in scan loops.
    """
    # Step 1: Quick keyword filter — reject non-weather markets fast
    q_lower = question.lower()
    if not any(kw in q_lower for kw in ("temperature", "temp ", "high temp", "highest temp")):
        return None, "no_weather_keyword"

    # Step 2: Extract city via regex patterns
    city_from_regex = None
    for pattern in _WEATHER_PATTERNS:
        m = pattern.search(question)
        if m:
            city_from_regex = m.group("city").strip().rstrip("?.,!")
            break

    # Also try the "in <city> be" pattern for real Polymarket format
    if not city_from_regex:
        m = re.search(
            r'temp(?:erature)?\s+in\s+(?P<city>[A-Za-z\s\'\.\-]+?)\s+be\s+',
            question, re.IGNORECASE,
        )
        if m:
            city_from_regex = m.group("city").strip()

    # Step 3: Resolve station
    station_id = None
    if city_from_regex:
        station_id = _extract_city(city_from_regex)

    # Fallback: scan the entire question for known city aliases
    if not station_id:
        station_id = _extract_city(question)

    if not station_id:
        # Try dynamic station creation for global cities
        city_text = city_from_regex or ""
        if city_text:
            station = get_or_create_station(city_text)
            if station:
                station_id = station.station_id
        if not station_id:
            return None, f"unknown_city: {city_from_regex or '(none extracted)'}"

    station = STATION_REGISTRY[station_id]

    # Step 4: Extract date
    target_date = _parse_date(question)
    if target_date is None:
        return None, "no_date_found"

    # Validate date is not in the past
    today = datetime.now(timezone.utc).date()
    if target_date < today:
        return None, f"date_in_past: {target_date.isoformat()}"

    # Step 5: Parse buckets
    buckets, parse_errors = parse_temp_buckets(outcomes, token_ids)
    if parse_errors and len(buckets) < 2:
        return None, f"bucket_parse_failed: {'; '.join(parse_errors)}"

    # Step 6: Validate bucket set
    bucket_error = validate_buckets(buckets)
    if bucket_error:
        return None, f"invalid_buckets: {bucket_error}"

    # Success
    return WeatherMarketClassification(
        condition_id=condition_id,
        station_id=station_id,
        city=station.city,
        target_date=target_date.isoformat(),
        resolution_type="daily_high",
        buckets=buckets,
        question=question,
    ), None


# ---- Real Polymarket Binary-Bucket Question Parsing ----
# On Polymarket, each temperature bucket is a separate binary (Yes/No) market.
# The event groups them. Each question looks like:
#   "Will the highest temperature in New York City be 43°F or below on March 14?"
#   "Will the highest temperature in New York City be between 44-45°F on March 14?"
#   "Will the highest temperature in New York City be 58°F or higher on March 14?"

# Regex patterns for extracting bucket from full binary questions
_BINARY_BUCKET_PATTERNS = [
    # "be 43°F or below on" / "be 9°C or below on"
    re.compile(
        r'be\s+(?P<val>\d+)\s*°?\s*[FfCc]?\s*or\s+(?:below|lower|less)\s+on\s+',
        re.IGNORECASE,
    ),
    # "be 58°F or higher on" / "be 18°C or higher on"
    re.compile(
        r'be\s+(?P<val>\d+)\s*°?\s*[FfCc]?\s*or\s+(?:above|higher|more|greater)\s+on\s+',
        re.IGNORECASE,
    ),
    # "be between 44-45°F on" / "be between 10-11°C on"
    re.compile(
        r'be\s+between\s+(?P<lo>\d+)\s*°?\s*[FfCc]?\s*[\-–]\s*(?P<hi>\d+)\s*°?\s*[FfCc]?\s+on\s+',
        re.IGNORECASE,
    ),
    # Exact value: "be 9°C on March 17?" (London format)
    re.compile(
        r'be\s+(?P<val>\d+)\s*°\s*[CcFf]\s+on\s+',
        re.IGNORECASE,
    ),
]


def parse_bucket_from_question(
    question: str,
    yes_token_id: str,
) -> Optional[TempBucket]:
    """Extract a temperature bucket from a Polymarket binary question.

    Handles both °F and °C markets. For °C, values are converted to °F for
    consistent internal representation.
    """
    is_celsius = "°c" in question.lower() or "°C" in question

    def _to_f(val: float) -> float:
        return val * 9.0 / 5.0 + 32.0 if is_celsius else val

    unit = "°C" if is_celsius else "°F"

    # Pattern: "be X°F or below on"
    m = _BINARY_BUCKET_PATTERNS[0].search(question)
    if m:
        val = float(m.group("val"))
        return TempBucket(
            label=f"{int(val)}{unit} or below",
            token_id=yes_token_id,
            lower_bound=None,
            upper_bound=_to_f(val),
        )

    # Pattern: "be X°F or higher on"
    m = _BINARY_BUCKET_PATTERNS[1].search(question)
    if m:
        val = float(m.group("val"))
        return TempBucket(
            label=f"{int(val)}{unit} or higher",
            token_id=yes_token_id,
            lower_bound=_to_f(val),
            upper_bound=None,
        )

    # Pattern: "be between X-Y°F on"
    m = _BINARY_BUCKET_PATTERNS[2].search(question)
    if m:
        lo, hi = float(m.group("lo")), float(m.group("hi"))
        return TempBucket(
            label=f"{int(min(lo,hi))}-{int(max(lo,hi))}{unit}",
            token_id=yes_token_id,
            lower_bound=_to_f(min(lo, hi)),
            upper_bound=_to_f(max(lo, hi)),
        )

    # Pattern: exact value "be 9°C on" (London format)
    m = _BINARY_BUCKET_PATTERNS[3].search(question)
    if m:
        val = float(m.group("val"))
        return TempBucket(
            label=f"{int(val)}{unit}",
            token_id=yes_token_id,
            lower_bound=_to_f(val - 0.5),
            upper_bound=_to_f(val + 0.5),
        )

    return None


def classify_binary_weather_markets(
    markets: List[Dict],
) -> Tuple[List[WeatherMarketClassification], List[str]]:
    """Classify a list of binary Polymarket weather markets into grouped events.

    Each market dict should have:
      - question: str
      - condition_id: str
      - yes_token_id: str  (the YES token for the binary market)
      - mid_price: float  (YES price)

    Groups markets by (station_id, target_date) to form events.
    Each event becomes a WeatherMarketClassification with multiple buckets.

    Returns (classifications, errors).
    """
    # Group by (station, date) → list of (bucket, condition_id, price)
    events: Dict[str, List[Tuple[TempBucket, str, float]]] = {}
    questions_by_event: Dict[str, str] = {}
    errors = []

    for mkt in markets:
        question = mkt.get("question", "")
        condition_id = mkt.get("condition_id", "")
        yes_token_id = mkt.get("yes_token_id", "")
        mid_price = mkt.get("mid_price", 0)

        # Quick keyword filter
        q_lower = question.lower()
        if "temperature" not in q_lower and "temp " not in q_lower:
            continue

        # Extract city
        station_id = _extract_city(question)
        if not station_id:
            # Pattern for real Polymarket: "temperature in <city> be ..."
            import re as _re
            city_m = _re.search(
                r'temp(?:erature)?\s+in\s+(?P<city>[A-Za-z\s\'\.\-]+?)\s+be\s+',
                question, _re.IGNORECASE,
            )
            if city_m:
                city_text = city_m.group("city").strip()
                # Try known aliases first
                station_id = _extract_city(city_text)
                if not station_id:
                    station_obj = get_or_create_station(city_text)
                    if station_obj:
                        station_id = station_obj.station_id
            # Fallback: try _WEATHER_PATTERNS
            if not station_id:
                for pattern in _WEATHER_PATTERNS:
                    pm = pattern.search(question)
                    if pm:
                        city_text = pm.group("city").strip().rstrip("?.,!")
                        station_obj = get_or_create_station(city_text)
                        if station_obj:
                            station_id = station_obj.station_id
                        break
        if not station_id:
            errors.append(f"unknown_city: {question[:60]}")
            continue

        # Extract date
        target_date = _parse_date(question)
        if not target_date:
            errors.append(f"no_date: {question[:60]}")
            continue

        today = datetime.now(timezone.utc).date()
        if target_date < today:
            continue  # silently skip past dates

        # Extract bucket from question
        bucket = parse_bucket_from_question(question, yes_token_id)
        if not bucket:
            errors.append(f"no_bucket: {question[:60]}")
            continue

        event_key = f"{station_id}:{target_date.isoformat()}"
        if event_key not in events:
            events[event_key] = []
            questions_by_event[event_key] = question
        events[event_key].append((bucket, condition_id, mid_price))

    # Build classifications from grouped events
    classifications = []
    for event_key, bucket_list in events.items():
        station_id, date_str = event_key.split(":", 1)
        station = STATION_REGISTRY.get(station_id)
        if not station:
            continue

        buckets = [b for b, _, _ in bucket_list]

        # Use a synthetic event-level condition_id
        event_condition_id = f"weather-event:{event_key}"

        # Validate bucket set (skip contiguous check for now — real markets may have gaps)
        if len(buckets) < 2:
            errors.append(f"too_few_buckets: {event_key} ({len(buckets)})")
            continue

        has_lower = any(b.is_lower_open for b in buckets)
        has_upper = any(b.is_upper_open for b in buckets)
        if not has_lower or not has_upper:
            errors.append(f"missing_boundary: {event_key}")
            continue

        classifications.append(WeatherMarketClassification(
            condition_id=event_condition_id,
            station_id=station_id,
            city=station.city,
            target_date=date_str,
            resolution_type="daily_high",
            buckets=buckets,
            question=questions_by_event.get(event_key, ""),
        ))

    return classifications, errors
