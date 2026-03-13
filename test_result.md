#====================================================================================================
# Testing Data
#====================================================================================================

user_problem_statement: "Phase 5A: Crypto Sniper Strategy backend implementation. New strategy that trades fast Polymarket crypto markets (BTC/ETH 5m/15m) using Binance spot price and simplified digital option model for fair probability estimation."

backend:
  - task: "Sniper Models (sniper_models.py)"
    implemented: true
    working: true
    file: "backend/engine/strategies/sniper_models.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "SniperConfig, CryptoMarketClassification, SniperSignal, SniperExecution, SniperSignalStatus models created. All using pydantic BaseModel with new_id/utc_now conventions."

  - task: "Sniper Pricing (sniper_pricing.py)"
    implemented: true
    working: true
    file: "backend/engine/strategies/sniper_pricing.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Pure functions: normal_cdf (via math.erf), compute_fair_probability, compute_realized_volatility, compute_momentum, compute_signal_confidence, compute_edge_bps. No scipy dependency."

  - task: "Crypto Sniper Strategy (crypto_sniper.py)"
    implemented: true
    working: true
    file: "backend/engine/strategies/crypto_sniper.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Full strategy class: classification cache, price ring buffers, 5-stage scan loop, signal generation + filtering, execution via RiskEngine/ExecutionEngine, fill tracking. Full pipeline verified: inject → classify → signal → execute → fill."

  - task: "Sniper API endpoints"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "4 new endpoints: GET /api/strategies/sniper/signals, GET /api/strategies/sniper/executions, GET /api/strategies/sniper/health, POST /api/test/inject-crypto-market. All verified via curl."

  - task: "Strategy registration in engine"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "CryptoSniper registered alongside ArbScanner in lifespan. Both strategies start when engine starts."

  - task: "Existing backend APIs still work (regression)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "No changes to existing engine components. Only additions to server.py."

frontend:
  - task: "Phase 4 Dashboard (existing - no changes)"
    implemented: true
    working: true
    file: "frontend/src/App.js"
    stuck_count: 0
    priority: "low"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "No frontend changes in Phase 5A. Dashboard still works."

metadata:
  created_by: "main_agent"
  version: "2.0"
  test_sequence: 1
  run_ui: false

test_plan:
  current_focus:
    - "Sniper Pricing (sniper_pricing.py)"
    - "Crypto Sniper Strategy (crypto_sniper.py)"
    - "Sniper API endpoints"
    - "Strategy registration in engine"
    - "Existing backend APIs still work (regression)"
  stuck_tasks: []
  test_all: true
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Phase 5A fully implemented. Full pipeline verified manually: engine start → inject synthetic BTC market → classification (regex parse question) → fair probability computation (math.erf CDF) → signal generation (5003bps edge) → risk check → execution → paper fill. All 4 new API endpoints working. No changes to existing engine components. Test the pricing module unit-test style and the full pipeline integration. Previous test reports at /app/test_reports/iteration_5.json."
