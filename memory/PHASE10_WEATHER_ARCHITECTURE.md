# Phase 10: Weather Strategy Architecture

## Overview

A production-grade weather trading strategy for Polymarket daily temperature markets. Uses forecast data from multiple sources, probabilistic distribution modeling over temperature buckets, and expected-value-based signal generation — fully integrated with Edge OS engine components.

---

## 1. Data Sources

### Primary: Open-Meteo Forecast API

**Why Open-Meteo?**
- **No API key required** — zero provisioning friction, no key rotation
- **Hourly temperature forecasts** up to 16 days out
- **Sub-10ms response times** — suitable for frequent polling
- **Sources from NOAA GFS + HRRR** (1.5km resolution in North America) — same underlying NWP models that NWS uses
- **Historical data from 1940** — essential for calibration
- **Fahrenheit output** via `&temperature_unit=fahrenheit` — matches Polymarket resolution units directly
- **Free for non-commercial use** with generous rate limits (10k calls/day)

**Endpoints used:**
```
# Hourly forecast (next 7 days)
GET https://api.open-meteo.com/v1/forecast
  ?latitude={lat}&longitude={lon}
  &hourly=temperature_2m
  &temperature_unit=fahrenheit
  &timezone=America/New_York
  &forecast_days=3

# Historical observations (for calibration)
GET https://archive-api.open-meteo.com/v1/archive
  ?latitude={lat}&longitude={lon}
  &start_date=2024-01-01&end_date=2024-12-31
  &hourly=temperature_2m
  &temperature_unit=fahrenheit
  &timezone=America/New_York
```

### Secondary (Verification): NWS API

**Why NWS as secondary?**
- **Official source** — METAR observations from airport stations are the gold standard
- **Free, no key needed**
- Used to **verify Open-Meteo forecasts** and to get **latest actual observations** for stations used in Polymarket resolution
- **Caveat**: NWS hourly forecast requires a 2-step lookup (points → gridpoint forecast), making it slower for bulk queries

**Endpoints used:**
```
# Latest observation (actual temperature at station)
GET https://api.weather.gov/stations/{ICAO}/observations/latest

# Station metadata
GET https://api.weather.gov/stations/{ICAO}
```

### Resolution Source: Weather Underground

**Critical**: Polymarket daily temperature markets resolve using **Weather Underground daily history** for the specified station (e.g., KLGA for NYC). The resolution URL pattern is:
```
https://www.wunderground.com/history/daily/us/{state}/{city}/{ICAO}/date/{YYYY-M-D}
```

The finalized **highest temperature to the nearest whole degree Fahrenheit** is the resolution value. Post-finalization revisions are ignored.

We do **not** need to scrape Weather Underground in real-time (forecasts come from Open-Meteo/NWS). We only need to understand that resolution is based on WU's reported daily high, which in turn comes from the ASOS/AWOS sensor at the specified airport station.

### Source Priority Matrix

| Purpose              | Source          | Frequency    | Latency |
|----------------------|-----------------|--------------|---------|
| Forecast (primary)   | Open-Meteo      | Every 30min  | <100ms  |
| Observation (verify) | NWS METAR       | Every 15min  | ~500ms  |
| Historical calibration | Open-Meteo Archive | On startup + daily | ~1s |
| Resolution truth     | Weather Underground | Post-market | N/A    |

---

## 2. Market Resolution Mapping

### Station Registry

Polymarket weather markets reference specific airport weather stations by ICAO code. The strategy needs a registry mapping:

```
StationRegistry:
  station_id: str          # ICAO code, e.g. "KLGA"
  city: str                # "New York City"
  state: str               # "NY"
  latitude: float          # 40.7769
  longitude: float         # -73.8740
  elevation_ft: float      # 22
  timezone: str            # "America/New_York"
  wunderground_slug: str   # "us/ny/new-york-city/KLGA"
  nws_wfo: str             # "OKX" (Weather Forecast Office)
  aliases: List[str]       # ["NYC", "New York", "LaGuardia"]
```

### Initial Station Set

Based on active and historical Polymarket weather markets:

| ICAO  | City          | Lat      | Lon       | TZ                  |
|-------|---------------|----------|-----------|---------------------|
| KLGA  | New York      | 40.7769  | -73.8740  | America/New_York    |
| KORD  | Chicago       | 41.9742  | -87.9073  | America/Chicago     |
| KLAX  | Los Angeles   | 33.9416  | -118.4085 | America/Los_Angeles |
| KATL  | Atlanta       | 33.6407  | -84.4277  | America/New_York    |
| KDFW  | Dallas        | 32.8998  | -97.0403  | America/Chicago     |
| KMIA  | Miami         | 25.7959  | -80.2870  | America/New_York    |
| KDEN  | Denver        | 39.8561  | -104.6737 | America/Denver      |
| KSFO  | San Francisco | 37.6213  | -122.3790 | America/Los_Angeles |

### Market-to-Station Matching

Polymarket market questions follow patterns like:
- "Highest temperature in NYC on March 13, 2026?"
- "What will the high temperature be in Chicago on March 15?"

The strategy needs a **question parser** (similar to CryptoSniper's regex classification) that extracts:

```
WeatherMarketClassification:
  condition_id: str
  station_id: str           # resolved ICAO code
  target_date: date         # the date for which temp is being predicted
  resolution_type: str      # "daily_high" (always for these markets)
  buckets: List[TempBucket] # parsed from market outcomes
  yes_token_id: str
  no_token_id: str
  question: str
```

**Matching logic:**
1. Regex-parse city name from question → lookup in station registry aliases
2. Parse date from question text (or from market's `endDate` field)
3. Validate: station found, date is in the future, within forecast horizon (1-7 days)

### Bucket Parsing

Polymarket temperature markets have multiple outcomes (not binary YES/NO). Each outcome is a temperature bucket. Example market with 5 outcomes:

```
Outcome 1: "40F or below"    → TempBucket(lower=-inf, upper=40)
Outcome 2: "41-42F"          → TempBucket(lower=41, upper=42)
Outcome 3: "43-44F"          → TempBucket(lower=43, upper=44)
Outcome 4: "45-46F"          → TempBucket(lower=45, upper=46)
Outcome 5: "47F or higher"   → TempBucket(lower=47, upper=+inf)
```

**Important architectural difference from ArbScanner/CryptoSniper**: Weather markets are **multi-outcome** (5+ buckets), not binary. Each outcome has its own token. The strategy evaluates ALL buckets simultaneously and may trade multiple buckets in the same market.

---

## 3. Probability Model

### Distribution-Based Approach

The core insight: **a point forecast of 44F does not mean P(43-44F) = 100%**. Forecast error is non-trivial and must be modeled.

We model the daily high temperature as a **normal distribution** centered on the forecast mean with **calibrated variance**:

```
T_high ~ Normal(mu, sigma^2)

Where:
  mu    = forecast high temperature (from Open-Meteo)
  sigma = calibrated forecast standard deviation
```

### Sigma Calibration

The forecast error (sigma) depends on:

1. **Lead time** (hours until resolution date):
   - 0-24h lead: sigma ~ 1.5-2.0 F
   - 24-48h lead: sigma ~ 2.5-3.0 F
   - 48-72h lead: sigma ~ 3.0-4.0 F
   - 72-120h lead: sigma ~ 4.0-5.5 F
   - 120-168h lead: sigma ~ 5.0-7.0 F

2. **Season** (winter has higher variance due to frontal systems):
   - Summer: base_sigma * 0.85
   - Spring/Fall: base_sigma * 1.0
   - Winter: base_sigma * 1.20

3. **Station-specific factors** (coastal vs inland):
   - Coastal (KLGA, KLAX, KMIA, KSFO): base_sigma * 0.90
   - Inland (KORD, KATL, KDFW, KDEN): base_sigma * 1.10

4. **Ensemble spread** (if available from Open-Meteo ensemble API):
   - If ensemble_spread > historical_avg: increase sigma proportionally
   - Acts as real-time uncertainty signal

### Calibration Bootstrap (startup)

On first run and then daily:
1. Fetch 365 days of historical hourly data from Open-Meteo Archive for each station
2. Extract daily max temperature from hourly data
3. Fetch the forecast that was available N days before each date (using Open-Meteo Previous Runs API)
4. Compute forecast error distribution: `error = observed_high - forecast_high`
5. Fit sigma by lead time bucket (0-24h, 24-48h, etc.)
6. Store calibration parameters in MongoDB for persistence

If historical forecast data is unavailable, use the **default sigma table** above (based on NWS MOS published accuracy data: ~2F at 1 day, ~3.5F at 3 days, ~5F at 5 days).

### Bucket Probability Calculation

For a market with buckets B_1, B_2, ..., B_n:

```
P(B_i) = Phi((upper_i + 0.5 - mu) / sigma) - Phi((lower_i - 0.5 - mu) / sigma)

Where:
  Phi     = standard normal CDF (using math.erf, same as sniper_pricing.py)
  mu      = forecast daily high
  sigma   = calibrated forecast std dev
  +0.5/-0.5 = continuity correction (resolution is to nearest whole degree)
```

For boundary buckets:
```
P("40F or below")  = Phi((40.5 - mu) / sigma)
P("47F or higher") = 1 - Phi((46.5 - mu) / sigma)
```

**Constraint**: All bucket probabilities must sum to 1.0 (enforced by normalization after computation).

### Multi-Forecast Blending

When multiple forecast sources are available:

```
mu_blended = w1 * mu_openmeteo + w2 * mu_nws
sigma_blended = sqrt(w1 * sigma_om^2 + w2 * sigma_nws^2 + w1*w2*(mu_om - mu_nws)^2)

Default weights: w1 = 0.70 (Open-Meteo/HRRR), w2 = 0.30 (NWS)
```

The inter-model disagreement term `w1*w2*(mu_om - mu_nws)^2` naturally inflates sigma when models disagree — a valuable real-time uncertainty signal.

---

## 4. Expected Value Calculation

### Per-Bucket EV

For each bucket i with market price `p_i` and model probability `P_i`:

```
EV_i = P_i * (1.0 - p_i) - (1 - P_i) * p_i
     = P_i - p_i

(Simplified because payout is $1 on correct bucket, $0 otherwise)
```

In basis points:
```
edge_bps_i = (P_i - p_i) * 10000
```

### When is there an opportunity?

A bucket is tradable when:
1. **Positive EV**: `P_i > p_i` (model thinks bucket is underpriced)
2. **Sufficient edge**: `edge_bps_i >= min_edge_bps` (default: 300bps / 3%)
3. **The edge is meaningful relative to sigma uncertainty**: Kelly-adjusted sizing

### Kelly-Inspired Position Sizing

```
kelly_fraction = (P_i - p_i) / (1 - p_i)
adjusted_size = min(base_size * kelly_fraction * kelly_scale, max_size)

Where kelly_scale = 0.25 (quarter-Kelly for safety)
```

This naturally sizes larger on high-confidence edges and smaller on marginal ones.

### Cross-Bucket Consistency Check

Before trading any bucket, verify the **implied probability sum**:

```
sum_market = sum(p_i for all buckets)
```

If `sum_market` deviates significantly from 1.0, the market may be mispriced structurally (vig, or genuine inefficiency). Track this as a market health metric.

---

## 5. Signal Generation Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    WEATHER STRATEGY SCAN LOOP                │
│                     (every 60 seconds)                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Stage 1: CLASSIFICATION (every 5 min)                      │
│    - Scan all markets for weather keywords                  │
│    - Regex parse: city, date, bucket structure               │
│    - Map city → station via StationRegistry                 │
│    - Cache classifications (refresh on new markets)          │
│                                                             │
│  Stage 2: FORECAST INGESTION (every 30 min)                 │
│    - For each classified station, fetch Open-Meteo forecast  │
│    - Optionally fetch NWS observation for verification       │
│    - Extract daily high forecast for target dates            │
│    - Store in forecast cache with timestamp                  │
│                                                             │
│  Stage 3: PROBABILITY MODELING (every scan)                  │
│    - For each classified market:                             │
│      a. Get latest forecast (mu) from cache                  │
│      b. Look up calibrated sigma (lead_time, season, station)│
│      c. Compute P(bucket_i) for all buckets                  │
│      d. Normalize to sum = 1.0                               │
│                                                             │
│  Stage 4: EV EVALUATION (every scan)                         │
│    - For each bucket in each market:                         │
│      a. Get market price p_i from StateManager               │
│      b. Compute edge_bps = (P_i - p_i) * 10000              │
│      c. Apply risk filters (Section 6)                       │
│      d. If tradable: generate WeatherSignal                  │
│                                                             │
│  Stage 5: EXECUTION (async)                                  │
│    - Submit through RiskEngine.check_order()                 │
│    - Route through ExecutionEngine.submit_order()            │
│    - Track fills via EventBus ORDER_UPDATE                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Timing Rationale

- **Classification**: Every 5 min (markets change rarely, expensive regex)
- **Forecast fetch**: Every 30 min (API rate limits; forecasts update hourly at most)
- **Probability + EV scan**: Every 60 sec (market prices change, need fresh EV calc)
- **This is intentionally slower than CryptoSniper** (5s scan) because:
  - Weather forecasts update hourly, not every second
  - Markets are less liquid, less time-sensitive
  - Fewer markets to scan (10-30 vs 100s of crypto markets)

---

## 6. Risk Filters

### Per-Signal Filters

| Filter                    | Default        | Rationale                                                    |
|---------------------------|----------------|--------------------------------------------------------------|
| `min_edge_bps`            | 300            | 3% minimum edge — higher than crypto (2%) due to lower frequency |
| `min_liquidity`           | 200            | Weather markets are less liquid than crypto                    |
| `max_spread`              | 0.15           | Allow wider spreads (weather markets are thinner)              |
| `min_confidence`          | 0.40           | Composite confidence score threshold                           |
| `max_stale_forecast_min`  | 120            | Don't trade on forecasts older than 2 hours                    |
| `max_stale_market_sec`    | 120            | Market data freshness                                          |
| `min_hours_to_resolution` | 4              | Don't trade within 4h of resolution (obs data already known)   |
| `max_hours_to_resolution` | 168            | Don't trade beyond 7-day forecast horizon                      |
| `forecast_update_cooldown`| 1800 (30 min)  | Don't re-trade same market within 30 min of last signal        |
| `max_buckets_per_market`  | 2              | Limit exposure: trade at most 2 buckets per market             |
| `max_concurrent_signals`  | 8              | Total open weather positions                                   |
| `max_sigma_uncertainty`   | 8.0            | Skip markets where calibrated sigma > 8F (too uncertain)       |

### Forecast Staleness Guard

```
if (now - forecast_timestamp) > max_stale_forecast_min * 60:
    reject("stale_forecast")
```

If the forecast cache is stale (API down, rate limited), the strategy goes idle rather than trading on outdated information.

### Observation Contradiction Guard

If NWS current observation is available and the resolution date is today:
```
if abs(current_observed_high - forecast_high) > sigma * 2:
    # Forecast significantly wrong — skip or use observation-adjusted mu
    mu_adjusted = 0.5 * forecast_high + 0.5 * current_observed_high
    sigma_adjusted = sigma * 0.7  # tighter since we have partial observation
```

### Confidence Score

```
WeatherConfidence = weighted sum of:
  - Liquidity depth       (0 - 0.20)
  - Market data freshness (0 - 0.20)
  - Forecast freshness    (0 - 0.20)
  - Lead time quality     (0 - 0.20)  # sweet spot: 12-72h
  - Sigma quality         (0 - 0.20)  # lower sigma = higher confidence
```

---

## 7. Integration with Edge OS

### Engine Component Integration

```
                    TradingEngine
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ArbScanner    CryptoSniper    WeatherTrader   ← new
         │               │               │
         └───────────────┼───────────────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
          RiskEngine  ExecEngine  EventBus
```

### Registration (server.py lifespan)

```python
# Phase 10: Weather trader strategy
weather_trader = WeatherTrader()
engine.register_strategy(weather_trader)
state.strategies["weather_trader"].enabled = True
weather_trader_ref = weather_trader
```

### StateManager Extensions

```python
# Add to StateManager.__init__:
self.weather_forecasts: Dict[str, dict] = {}    # station_id → latest forecast
self.weather_calibration: Dict[str, dict] = {}  # station_id → sigma params
```

### EventBus Usage

- **Listens to**: `EventType.ORDER_UPDATE` (fill tracking, same as other strategies)
- **Emits**: `EventType.SIGNAL` (for Telegram alerts, analytics, dashboard)

Signal event data format:
```python
{
    "strategy": "WEATHER",
    "asset": "KLGA",           # station
    "strike": "43-44F",        # bucket label
    "fair_price": 0.35,        # model probability
    "market_price": 0.22,      # Polymarket price
    "edge_bps": 1300,
    "side": "BUY",
    "forecast_high": 44,
    "sigma": 2.5,
    "lead_hours": 36,
}
```

### Analytics Integration

The weather strategy uses `strategy_id = "weather_trader"`. The existing analytics service (`analytics_service.py`) already computes per-strategy metrics dynamically from `state.trades` and `state.orders`, keyed by `strategy_id`. **No changes needed** — weather trades automatically appear in:
- `GET /api/analytics/strategies` → `strategies["weather_trader"]`
- `GET /api/analytics/timeseries` → `executions_by_strategy["weather_trader"]`
- `GET /api/analytics/summary` → included in portfolio totals

### API Endpoints

```
GET  /api/strategies/weather/signals          → recent signals (tradable + rejected)
GET  /api/strategies/weather/executions       → active + completed executions
GET  /api/strategies/weather/health           → metrics, forecast status, calibration
GET  /api/strategies/weather/forecasts        → current forecast cache per station
GET  /api/strategies/weather/stations         → station registry
POST /api/test/inject-weather-market          → inject synthetic weather market (testing)
```

### Config Persistence (Phase 7)

Weather config stored alongside arb/sniper config in `config_service.py`:
```python
weather_config = {
    "scan_interval": 60,
    "forecast_refresh_interval": 1800,
    "min_edge_bps": 300,
    "min_liquidity": 200,
    # ... all WeatherConfig fields
}
```

---

## 8. Mode Progression

### Paper Mode (default)

- Full pipeline active: classification, forecast fetch, probability modeling, EV calculation, signal generation
- Orders executed through PaperAdapter (instant simulated fills)
- Track P&L, win rate, calibration accuracy
- **Goal**: Validate model accuracy over 2+ weeks of daily markets

### Shadow Mode

- Full pipeline active, including signal generation
- Orders logged but NOT submitted to CLOB
- Log messages: `[SHADOW] Would submit: BUY bucket "43-44F" @ 0.22 size=3`
- **Goal**: Verify execution logic without financial risk, compare shadow P&L to paper

### Live Mode

- Full pipeline active
- Orders submitted through LiveAdapter to Polymarket CLOB
- All Phase 8/8A/8B safeguards apply:
  - Kill switch check
  - Preflight: auth + mode + kill switch + size cap + slippage
  - Conservative sizing (max_order=2, max_position=5 per bucket)
  - Slippage protection: reject orders > max_live_slippage_bps
  - Partial fill tracking
- **Prerequisites**: Paper mode P&L positive over 14+ days, calibration verified

---

## 9. File Structure

```
backend/engine/strategies/
  weather_models.py          # Pydantic models: WeatherConfig, StationInfo,
                             # WeatherMarketClassification, TempBucket,
                             # WeatherSignal, WeatherExecution, ForecastCache
  weather_pricing.py         # Pure functions: compute_bucket_probabilities,
                             # calibrate_sigma, compute_ev, normal_cdf (reuse),
                             # blend_forecasts, kelly_size
  weather_feeds.py           # WeatherFeedManager: Open-Meteo + NWS API clients,
                             # forecast caching, observation fetching,
                             # historical calibration bootstrap
  weather_trader.py          # WeatherTrader(BaseStrategy): main strategy class,
                             # classification, scan loop, signal gen, execution
```

---

## 10. Step-by-Step Implementation Plan

### Step 1: Models (`weather_models.py`)
- Define WeatherConfig with all tunable parameters
- Define StationInfo, STATION_REGISTRY dict
- Define TempBucket, WeatherMarketClassification
- Define WeatherSignal, WeatherExecution
- Define ForecastSnapshot (cached forecast for a station/date)
- **Test**: Import all models, instantiate with defaults, verify JSON serialization

### Step 2: Station Registry + Market Parser
- Implement STATION_REGISTRY as a dict in weather_models.py
- Implement `classify_weather_market()` — regex parser for market questions
- Implement `parse_temp_buckets()` — parse outcome strings into TempBucket list
- **Test**: Unit test with sample Polymarket weather market questions

### Step 3: Pricing Module (`weather_pricing.py`)
- `compute_bucket_probabilities(mu, sigma, buckets)` → List[float]
- `calibrate_sigma(lead_hours, season, station_type)` → float
- `compute_bucket_ev(probabilities, market_prices)` → List[float]
- `blend_forecasts(forecasts, weights)` → (mu, sigma)
- `kelly_size(edge, prob, base_size, scale)` → float
- Reuse `normal_cdf` from sniper_pricing.py
- **Test**: Known inputs → verify bucket probs sum to 1.0, EV calculations correct

### Step 4: Weather Feed Manager (`weather_feeds.py`)
- Open-Meteo forecast client (async aiohttp)
- NWS observation client (async aiohttp)
- Forecast cache with timestamps
- Historical calibration bootstrap (fetch + compute sigma table)
- **Test**: Fetch real forecast for KLGA, verify response parsing

### Step 5: Strategy Class (`weather_trader.py`)
- Extend BaseStrategy with 5-stage scan loop
- Wire classification, forecast, probability, EV, execution stages
- Implement fill tracking via EventBus
- API data accessors: get_signals, get_health, get_forecasts
- **Test**: Inject synthetic weather market → verify full pipeline

### Step 6: Server Integration
- Register WeatherTrader in server.py lifespan
- Add 6 API endpoints
- Add test injection endpoint
- Wire config persistence
- **Test**: curl all endpoints, verify 200 responses

### Step 7: Dashboard Page
- New `/weather` page in frontend
- Station map / forecast table
- Signal feed with bucket probabilities
- Execution history
- Calibration status (sigma per station)
- **Test**: Screenshot verification, data-testid attributes

### Step 8: Testing + Calibration Validation
- Backend pytest suite
- Frontend UI tests via testing agent
- Paper mode validation with real market data
- Calibration accuracy check: compare model probs to actual outcomes

---

## Appendix A: Multi-Outcome Market Handling

Unlike ArbScanner (binary YES/NO pairs) and CryptoSniper (binary above/below), weather markets have **N outcomes** (typically 5-7 buckets). This requires:

1. **Market grouping**: Group all tokens by condition_id (same as arb_scanner)
2. **Outcome parsing**: Each token's outcome string maps to a TempBucket
3. **Simultaneous evaluation**: All buckets evaluated together (probabilities must sum to 1)
4. **Independent execution**: Each bucket trade is independent (separate OrderRecord per bucket)
5. **Portfolio-aware**: Track total exposure across all buckets in same market

### Example Market State

```
condition_id: "0x1234..."
question: "Highest temperature in NYC on March 15, 2026?"

Token A: "40F or below"  → market_price=0.05, model_prob=0.03, edge=-200bps (skip)
Token B: "41-42F"        → market_price=0.10, model_prob=0.12, edge=+200bps (below min)
Token C: "43-44F"        → market_price=0.22, model_prob=0.35, edge=+1300bps (TRADE)
Token D: "45-46F"        → market_price=0.35, model_prob=0.30, edge=-500bps (skip)
Token E: "47F or higher" → market_price=0.28, model_prob=0.20, edge=-800bps (skip)
```

Only Token C would generate a signal in this example.

## Appendix B: Calibration Data Schema (MongoDB)

```json
{
    "station_id": "KLGA",
    "calibrated_at": "2026-03-13T...",
    "sample_count": 365,
    "sigma_by_lead_hours": {
        "0_24": 1.8,
        "24_48": 2.7,
        "48_72": 3.4,
        "72_120": 4.8,
        "120_168": 6.2
    },
    "seasonal_factors": {
        "winter": 1.15,
        "spring": 1.0,
        "summer": 0.88,
        "fall": 1.02
    },
    "mean_bias": -0.3,
    "data_period": "2024-03-13 to 2025-03-13"
}
```
