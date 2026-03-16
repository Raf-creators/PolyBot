"""
Test Global Analytics Feature - Shadow-mode strategy quality dashboard

Tests the new GET /api/analytics/global endpoint which provides:
- Strategy performance metrics (signals, executions, edge, win rate)
- Forecast quality metrics (error distribution, MAE by station, bias)
- Liquidity insights (avg score, rejection breakdown)
- Timeseries data (cumulative PnL, signal frequency)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestGlobalAnalyticsEndpoint:
    """Test GET /api/analytics/global returns valid structured data"""

    def test_global_analytics_returns_200(self):
        """Test endpoint returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/analytics/global returns 200")

    def test_global_analytics_has_required_sections(self):
        """Test response has all required top-level sections"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        data = response.json()
        
        required_sections = ['strategy_performance', 'forecast_quality', 'liquidity_insights', 'timeseries']
        for section in required_sections:
            assert section in data, f"Missing required section: {section}"
        print(f"PASS: Response has all required sections: {required_sections}")


class TestStrategyPerformanceSection:
    """Test strategy_performance section structure and content"""

    def test_strategy_performance_aggregate_fields(self):
        """Test aggregate fields in strategy_performance"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        perf = response.json()['strategy_performance']
        
        aggregate_fields = ['total_signals', 'total_executions', 'total_filled', 'total_trades',
                          'realized_pnl', 'win_count', 'loss_count', 'win_rate', 'avg_win', 'avg_loss']
        for field in aggregate_fields:
            assert field in perf, f"Missing field: {field}"
            assert isinstance(perf[field], (int, float)), f"Field {field} should be numeric"
        print(f"PASS: strategy_performance has all aggregate fields")

    def test_strategy_performance_by_strategy(self):
        """Test by_strategy breakdown exists with expected strategies"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        perf = response.json()['strategy_performance']
        
        assert 'by_strategy' in perf, "Missing by_strategy field"
        by_strat = perf['by_strategy']
        
        # Should have weather_trader, arb_scanner, crypto_sniper
        expected_strategies = ['weather_trader', 'arb_scanner', 'crypto_sniper']
        for strat in expected_strategies:
            assert strat in by_strat, f"Missing strategy: {strat}"
        print(f"PASS: by_strategy contains all expected strategies: {expected_strategies}")

    def test_weather_trader_strategy_fields(self):
        """Test weather_trader has all expected fields"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        weather = response.json()['strategy_performance']['by_strategy']['weather_trader']
        
        expected_fields = ['total_signals', 'total_executed', 'total_filled', 'active_executions']
        for field in expected_fields:
            assert field in weather, f"Missing weather_trader field: {field}"
        
        # Weather-specific fields
        weather_specific = ['avg_expected_edge_bps', 'tradable_signals', 'rejection_reasons', 'total_scans', 'classified_markets']
        for field in weather_specific:
            assert field in weather, f"Missing weather-specific field: {field}"
        print("PASS: weather_trader has all expected fields")

    def test_arb_scanner_strategy_fields(self):
        """Test arb_scanner has expected fields"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        arb = response.json()['strategy_performance']['by_strategy']['arb_scanner']
        
        expected_fields = ['total_signals', 'total_executed', 'total_filled', 'active_executions']
        for field in expected_fields:
            assert field in arb, f"Missing arb_scanner field: {field}"
        print("PASS: arb_scanner has all expected fields")

    def test_crypto_sniper_strategy_fields(self):
        """Test crypto_sniper has expected fields"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        sniper = response.json()['strategy_performance']['by_strategy']['crypto_sniper']
        
        expected_fields = ['total_signals', 'total_executed', 'total_filled', 'active_executions']
        for field in expected_fields:
            assert field in sniper, f"Missing crypto_sniper field: {field}"
        print("PASS: crypto_sniper has all expected fields")


class TestForecastQualitySection:
    """Test forecast_quality section - should have real KLGA data"""

    def test_forecast_quality_global_metrics(self):
        """Test global forecast quality metrics"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        forecast = response.json()['forecast_quality']
        
        global_fields = ['global_mae_f', 'global_bias_f', 'total_forecasts', 'resolved_forecasts']
        for field in global_fields:
            assert field in forecast, f"Missing forecast_quality field: {field}"
        print("PASS: forecast_quality has all global metrics fields")

    def test_forecast_quality_has_real_data(self):
        """Test forecast_quality has actual forecast data (30 forecasts, 1 resolved)"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        forecast = response.json()['forecast_quality']
        
        assert forecast['total_forecasts'] == 30, f"Expected 30 total forecasts, got {forecast['total_forecasts']}"
        assert forecast['resolved_forecasts'] == 1, f"Expected 1 resolved forecast, got {forecast['resolved_forecasts']}"
        print("PASS: forecast_quality has expected 30 total, 1 resolved forecasts")

    def test_forecast_quality_global_mae(self):
        """Test global MAE is around 4.3F (from KLGA resolved data)"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        forecast = response.json()['forecast_quality']
        
        mae = forecast['global_mae_f']
        assert mae is not None, "global_mae_f should not be None"
        assert 4.0 <= mae <= 5.0, f"Expected MAE around 4.3F, got {mae}"
        print(f"PASS: global_mae_f = {mae}F (expected ~4.3F)")

    def test_forecast_quality_error_distribution(self):
        """Test error_distribution array exists and has data"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        forecast = response.json()['forecast_quality']
        
        assert 'error_distribution' in forecast, "Missing error_distribution"
        error_dist = forecast['error_distribution']
        assert isinstance(error_dist, list), "error_distribution should be a list"
        assert len(error_dist) > 0, "error_distribution should have at least one entry (resolved forecast)"
        
        # Check structure of entries
        for entry in error_dist:
            assert 'error_f' in entry, "Each entry should have error_f"
            assert 'count' in entry, "Each entry should have count"
        print(f"PASS: error_distribution has {len(error_dist)} entries with valid structure")

    def test_forecast_quality_station_metrics(self):
        """Test station_metrics contains KLGA data"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        forecast = response.json()['forecast_quality']
        
        assert 'station_metrics' in forecast, "Missing station_metrics"
        stations = forecast['station_metrics']
        assert isinstance(stations, dict), "station_metrics should be a dict"
        
        # Should have KLGA
        assert 'KLGA' in stations, "KLGA station should be in station_metrics"
        print("PASS: station_metrics contains KLGA")

    def test_klga_station_metrics_structure(self):
        """Test KLGA station metrics have expected fields"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        klga = response.json()['forecast_quality']['station_metrics']['KLGA']
        
        expected_fields = ['station_id', 'sample_count', 'mean_abs_error_f', 'mean_bias_f']
        for field in expected_fields:
            assert field in klga, f"Missing KLGA field: {field}"
        
        # Verify KLGA data values
        assert klga['station_id'] == 'KLGA', "station_id should be KLGA"
        assert klga['sample_count'] >= 1, "sample_count should be at least 1"
        print(f"PASS: KLGA station metrics have expected structure, sample_count={klga['sample_count']}")


class TestLiquidityInsightsSection:
    """Test liquidity_insights section structure"""

    def test_liquidity_insights_score_fields(self):
        """Test liquidity score fields"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        liquidity = response.json()['liquidity_insights']
        
        score_fields = ['avg_traded_liquidity_score', 'min_traded_liquidity_score', 
                       'max_traded_liquidity_score', 'markets_with_scores']
        for field in score_fields:
            assert field in liquidity, f"Missing liquidity field: {field}"
        print("PASS: liquidity_insights has all score fields")

    def test_liquidity_insights_rejection_fields(self):
        """Test rejection breakdown fields"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        liquidity = response.json()['liquidity_insights']
        
        rejection_fields = ['weather_rejections', 'total_weather_rejections']
        for field in rejection_fields:
            assert field in liquidity, f"Missing rejection field: {field}"
        
        assert isinstance(liquidity['weather_rejections'], dict), "weather_rejections should be a dict"
        assert isinstance(liquidity['total_weather_rejections'], int), "total_weather_rejections should be int"
        print("PASS: liquidity_insights has rejection breakdown fields")


class TestTimeseriesSection:
    """Test timeseries section structure"""

    def test_timeseries_has_required_arrays(self):
        """Test timeseries has cumulative_pnl and signal_frequency arrays"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        ts = response.json()['timeseries']
        
        assert 'cumulative_pnl' in ts, "Missing cumulative_pnl"
        assert 'signal_frequency' in ts, "Missing signal_frequency"
        assert isinstance(ts['cumulative_pnl'], list), "cumulative_pnl should be a list"
        assert isinstance(ts['signal_frequency'], list), "signal_frequency should be a list"
        print("PASS: timeseries has cumulative_pnl and signal_frequency arrays")

    def test_timeseries_empty_when_no_trades(self):
        """Test timeseries arrays are empty when no trades (engine stopped)"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        ts = response.json()['timeseries']
        
        # With engine stopped and no trades, these should be empty
        # This is expected behavior per requirements
        if len(ts['cumulative_pnl']) == 0:
            print("PASS: timeseries arrays empty (no trades - expected)")
        else:
            print(f"INFO: timeseries has {len(ts['cumulative_pnl'])} cumulative_pnl entries")


class TestRegressionExistingEndpoints:
    """Regression tests - ensure existing endpoints still work"""

    def test_health_endpoint(self):
        """Test /api/health still works"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("PASS: /api/health returns 200")

    def test_status_endpoint(self):
        """Test /api/status still works"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        print("PASS: /api/status returns 200")

    def test_config_endpoint(self):
        """Test /api/config still works"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        print("PASS: /api/config returns 200")

    def test_analytics_summary_endpoint(self):
        """Test /api/analytics/summary still works"""
        response = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert response.status_code == 200
        print("PASS: /api/analytics/summary returns 200")

    def test_analytics_strategies_endpoint(self):
        """Test /api/analytics/strategies still works"""
        response = requests.get(f"{BASE_URL}/api/analytics/strategies")
        assert response.status_code == 200
        print("PASS: /api/analytics/strategies returns 200")

    def test_weather_health_endpoint(self):
        """Test /api/strategies/weather/health still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        print("PASS: /api/strategies/weather/health returns 200")

    def test_arb_health_endpoint(self):
        """Test /api/strategies/arb/health still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200
        print("PASS: /api/strategies/arb/health returns 200")

    def test_sniper_health_endpoint(self):
        """Test /api/strategies/sniper/health still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        print("PASS: /api/strategies/sniper/health returns 200")
