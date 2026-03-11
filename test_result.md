#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Build a professional, real-time, dark-mode trading dashboard for Polymarket Edge OS. 6 pages: Overview, Arbitrage, Positions & Trades, Risk Monitor, Markets, Settings. Single global WebSocket connection, zustand state store, REST APIs for detailed data hydration."

backend:
  - task: "API endpoints for dashboard (status, config, markets, positions, trades, orders, arb, health, ws)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "All backend APIs were built in Phase 1-3. 15+ endpoints available. Backend is stable core, not modified in Phase 4."

frontend:
  - task: "App Shell (Sidebar + TopBar + global WebSocket)"
    implemented: true
    working: "NA"
    file: "frontend/src/components/AppShell.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Created AppShell with Sidebar navigation, TopBar with engine controls, single global WebSocket via useWebSocket hook."

  - task: "Overview Page"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Overview.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "6 stat cards (Daily PnL, Paper Balance, Win Rate, Total Trades, Open Positions, Markets Tracked), System Status, Active Strategies, Feed Health, Recent Trades table."

  - task: "Arbitrage Page"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Arbitrage.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Tabs: Opportunities, Rejected, Executions, Health. Data tables with sorting. Scanner metrics and config display. REST-hydrated with 8s polling."

  - task: "Positions & Trades Page"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Positions.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Tabs: Positions, Trades, Orders. Data tables with sorting. Summary stats (exposure, unrealized/realized PnL). REST-hydrated with 8s polling."

  - task: "Risk Monitor Page"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Risk.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Kill switch button with banner, risk gauges (exposure, position slots, daily loss limit), risk alerts, risk config display, component health, strategy health."

  - task: "Markets Page"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Markets.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Markets data table with search/filter, volume and liquidity stats, sortable columns. REST-hydrated with 15s polling."

  - task: "Settings Page"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Settings.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Trading mode toggle (paper/shadow/live), credentials status, risk configuration form with save, strategy configuration display. Uses updateConfig API."

  - task: "State Management (Zustand store)"
    implemented: true
    working: "NA"
    file: "frontend/src/state/dashboardStore.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Central zustand store with WS snapshot + REST-hydrated data. Single global WebSocket, components subscribe to specific slices."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 0
  run_ui: true

test_plan:
  current_focus:
    - "App Shell (Sidebar + TopBar + global WebSocket)"
    - "Overview Page"
    - "Arbitrage Page"
    - "Positions & Trades Page"
    - "Risk Monitor Page"
    - "Markets Page"
    - "Settings Page"
    - "State Management (Zustand store)"
  stuck_tasks: []
  test_all: true
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Phase 4 frontend dashboard fully implemented. All 6 pages built with shared components, single global WebSocket, zustand state store. Dark trading terminal theme. Backend not modified. All pages need UI/functionality testing. Engine can be started via the Start button in the top bar. Backend APIs are at /api/*. Start engine first, then test arb injection endpoint to generate test data."
