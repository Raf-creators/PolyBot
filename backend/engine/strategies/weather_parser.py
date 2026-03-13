"""Station registry and market question parser for the Weather strategy.

Responsibilities:
  1. STATION_REGISTRY: ICAO-keyed dict of StationInfo for known Polymarket stations
  2. classify_weather_market(): regex parser that extracts city, date, buckets
  3. parse_temp_buckets(): outcome string → TempBucket list

All functions are pure (no side effects, no I/O). Designed to be called
from the strategy scan loop without risk of exceptions breaking the loop.
"""

import re
from datetime import datetime, timezone, date as date_type
from typing import Dict, List, Optional, Tuple

from engine.strategies.weather_models import (
    StationInfo, StationType, TempBucket, WeatherMarketClassification,
)


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


def get_all_stations() -> List[StationInfo]:
    """Return all registered stations."""
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

    # Step 3: Resolve station
    station_id = None
    if city_from_regex:
        station_id = _extract_city(city_from_regex)

    # Fallback: scan the entire question for known city aliases
    if not station_id:
        station_id = _extract_city(question)

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
    # "be 43°F or below on"
    re.compile(
        r'be\s+(?P<val>\d+)\s*°?\s*[Ff]?\s*or\s+(?:below|lower|less)\s+on\s+',
        re.IGNORECASE,
    ),
    # "be 58°F or higher on"
    re.compile(
        r'be\s+(?P<val>\d+)\s*°?\s*[Ff]?\s*or\s+(?:above|higher|more|greater)\s+on\s+',
        re.IGNORECASE,
    ),
    # "be between 44-45°F on" / "be between 44°F-45°F on"
    re.compile(
        r'be\s+between\s+(?P<lo>\d+)\s*°?\s*[Ff]?\s*[\-–]\s*(?P<hi>\d+)\s*°?\s*[Ff]?\s+on\s+',
        re.IGNORECASE,
    ),
]


def parse_bucket_from_question(
    question: str,
    yes_token_id: str,
) -> Optional[TempBucket]:
    """Extract a temperature bucket from a Polymarket binary question.

    Real Polymarket weather markets are binary (Yes/No). Each bucket is
    a separate market. The YES token represents the bucket occurring.

    Returns TempBucket using the YES token_id, or None if not a bucket question.
    """
    # Pattern: "be X°F or below on"
    m = _BINARY_BUCKET_PATTERNS[0].search(question)
    if m:
        val = float(m.group("val"))
        return TempBucket(
            label=f"{int(val)}°F or below",
            token_id=yes_token_id,
            lower_bound=None,
            upper_bound=val,
        )

    # Pattern: "be X°F or higher on"
    m = _BINARY_BUCKET_PATTERNS[1].search(question)
    if m:
        val = float(m.group("val"))
        return TempBucket(
            label=f"{int(val)}°F or higher",
            token_id=yes_token_id,
            lower_bound=val,
            upper_bound=None,
        )

    # Pattern: "be between X-Y°F on"
    m = _BINARY_BUCKET_PATTERNS[2].search(question)
    if m:
        lo, hi = float(m.group("lo")), float(m.group("hi"))
        return TempBucket(
            label=f"{int(min(lo,hi))}-{int(max(lo,hi))}°F",
            token_id=yes_token_id,
            lower_bound=min(lo, hi),
            upper_bound=max(lo, hi),
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
