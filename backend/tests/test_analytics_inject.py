"""Inject synthetic trades via a temporary API endpoint for analytics testing."""
import requests
import sys
import json

API_BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001/api"

# Step 1: Inject test trades
resp = requests.post(f"{API_BASE}/test/inject-trades")
if resp.status_code != 200:
    print(f"FAIL: inject-trades returned {resp.status_code}: {resp.text}")
    sys.exit(1)
inject_data = resp.json()
print(f"Injected {inject_data['count']} trades")

# Step 2: Test summary endpoint
resp = requests.get(f"{API_BASE}/analytics/summary")
assert resp.status_code == 200, f"summary failed: {resp.status_code}"
summary = resp.json()
print(f"\n--- SUMMARY ---")
print(f"trade_count: {summary['trade_count']}")
print(f"total_pnl: {summary['total_pnl']}")
print(f"win_rate: {summary['win_rate']}")
print(f"profit_factor: {summary['profit_factor']}")
print(f"sharpe_ratio: {summary['sharpe_ratio']}")
print(f"max_drawdown: {summary['max_drawdown']}")
print(f"expectancy: {summary['expectancy']}")

assert summary['trade_count'] > 0, "Expected trades"
assert summary['win_rate'] is not None, "Expected win_rate"
assert summary['sharpe_ratio'] is not None, "Expected sharpe_ratio"

# Step 3: Test strategies endpoint
resp = requests.get(f"{API_BASE}/analytics/strategies")
assert resp.status_code == 200, f"strategies failed: {resp.status_code}"
strategies = resp.json()
print(f"\n--- STRATEGIES ---")
for sid, m in strategies.items():
    print(f"  {sid}: pnl={m['pnl']}, trades={m['trade_count']}, win_rate={m['win_rate']}")
assert len(strategies) >= 2, "Expected at least 2 strategies"

# Step 4: Test execution quality endpoint
resp = requests.get(f"{API_BASE}/analytics/execution-quality")
assert resp.status_code == 200, f"exec-quality failed: {resp.status_code}"
eq = resp.json()
print(f"\n--- EXECUTION QUALITY ---")
print(f"total_orders: {eq['total_orders']}")
print(f"filled_count: {eq['filled_count']}")
print(f"fill_ratio: {eq['fill_ratio']}")

# Step 5: Test timeseries endpoint
resp = requests.get(f"{API_BASE}/analytics/timeseries")
assert resp.status_code == 200, f"timeseries failed: {resp.status_code}"
ts = resp.json()
print(f"\n--- TIMESERIES ---")
print(f"daily_pnl entries: {len(ts['daily_pnl'])}")
print(f"equity_curve entries: {len(ts['equity_curve'])}")
print(f"drawdown_curve entries: {len(ts['drawdown_curve'])}")
print(f"rolling_7d_pnl: {ts['rolling_7d_pnl']}")
print(f"rolling_30d_pnl: {ts['rolling_30d_pnl']}")
print(f"executions_by_strategy keys: {list(ts['executions_by_strategy'].keys())}")

assert len(ts['daily_pnl']) > 0, "Expected daily_pnl data"
assert len(ts['equity_curve']) > 0, "Expected equity_curve data"
assert len(ts['drawdown_curve']) > 0, "Expected drawdown_curve data"
assert ts['rolling_7d_pnl'] is not None, "Expected rolling_7d_pnl"

# Step 6: Clean up
resp = requests.post(f"{API_BASE}/test/clear-trades")
print(f"\nCleanup: {resp.json()}")

print("\n=== ALL ANALYTICS TESTS PASSED ===")
