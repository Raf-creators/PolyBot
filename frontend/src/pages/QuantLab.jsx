import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { API_BASE } from '../utils/constants';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { formatPnl, formatPrice, formatBps, formatTimestamp, formatTimeAgo, pnlColor, truncate, formatPercent } from '../utils/formatters';
import { FlaskConical, Zap, Ghost, BarChart3, Clock, Globe, AlertTriangle } from 'lucide-react';

const api = axios.create({ baseURL: API_BASE });

export default function QuantLab() {
  const [activeTab, setActiveTab] = useState('shadow_sniper');
  const [registry, setRegistry] = useState([]);

  // Shadow Sniper state
  const [ssReport, setSsReport] = useState(null);
  const [ssEvals, setSsEvals] = useState([]);
  const [ssUnitPos, setSsUnitPos] = useState([]);
  const [ssLePos, setSsLePos] = useState([]);
  const [ssUnitClosed, setSsUnitClosed] = useState([]);
  const [ssLeClosed, setSsLeClosed] = useState([]);

  // MoonDev state
  const [mdReport, setMdReport] = useState(null);
  const [mdEvals, setMdEvals] = useState([]);
  const [mdPositions, setMdPositions] = useState([]);
  const [mdClosed, setMdClosed] = useState([]);

  // Phantom state (one-side + gabagool)
  const [phReport, setPhReport] = useState(null);
  const [phEvals, setPhEvals] = useState([]);
  const [phPositions, setPhPositions] = useState([]);
  const [phClosed, setPhClosed] = useState([]);
  const [phGabaPos, setPhGabaPos] = useState([]);
  const [phGabaClosed, setPhGabaClosed] = useState([]);

  // Whrrari state (3 modes)
  const [whReport, setWhReport] = useState(null);
  const [whEvals, setWhEvals] = useState([]);
  const [whUnitPos, setWhUnitPos] = useState([]);
  const [whUnitClosed, setWhUnitClosed] = useState([]);
  const [whSandboxPos, setWhSandboxPos] = useState([]);
  const [whSandboxClosed, setWhSandboxClosed] = useState([]);
  const [whCryptoPos, setWhCryptoPos] = useState([]);
  const [whCryptoClosed, setWhCryptoClosed] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const [reg] = await Promise.all([api.get('/experiments/registry')]);
      setRegistry(reg.data.experiments || []);
    } catch { /* silent */ }

    // Fetch detail data based on active tab
    try {
      if (activeTab === 'shadow_sniper') {
        const [rpt, evals, uP, lP, uC, lC] = await Promise.all([
          api.get('/shadow/report'), api.get('/shadow/evaluations?limit=100'),
          api.get('/shadow/positions?mode=unit'), api.get('/shadow/positions?mode=le'),
          api.get('/shadow/closed?limit=50&mode=unit'), api.get('/shadow/closed?limit=50&mode=le'),
        ]);
        setSsReport(rpt.data); setSsEvals(evals.data);
        setSsUnitPos(uP.data); setSsLePos(lP.data);
        setSsUnitClosed(uC.data); setSsLeClosed(lC.data);
      } else if (activeTab === 'moondev') {
        const [rpt, evals, pos, cls] = await Promise.all([
          api.get('/experiments/moondev/report'), api.get('/experiments/moondev/evaluations?limit=100'),
          api.get('/experiments/moondev/positions?mode=unit'), api.get('/experiments/moondev/closed?mode=unit&limit=50'),
        ]);
        setMdReport(rpt.data); setMdEvals(evals.data);
        setMdPositions(pos.data); setMdClosed(cls.data);
      } else if (activeTab === 'phantom') {
        const [rpt, evals, pos, cls, gPos, gCls] = await Promise.all([
          api.get('/experiments/phantom/report'), api.get('/experiments/phantom/evaluations?limit=100'),
          api.get('/experiments/phantom/positions?mode=unit'), api.get('/experiments/phantom/closed?mode=unit&limit=50'),
          api.get('/experiments/phantom/positions?mode=gabagool'), api.get('/experiments/phantom/closed?mode=gabagool&limit=50'),
        ]);
        setPhReport(rpt.data); setPhEvals(evals.data);
        setPhPositions(pos.data); setPhClosed(cls.data);
        setPhGabaPos(gPos.data); setPhGabaClosed(gCls.data);
      } else if (activeTab === 'whrrari') {
        const [rpt, evals, uP, uC, sP, sC, cP, cC] = await Promise.all([
          api.get('/experiments/whrrari/report'), api.get('/experiments/whrrari/evaluations?limit=100'),
          api.get('/experiments/whrrari/positions?mode=unit'), api.get('/experiments/whrrari/closed?mode=unit&limit=50'),
          api.get('/experiments/whrrari/positions?mode=sandbox'), api.get('/experiments/whrrari/closed?mode=sandbox&limit=50'),
          api.get('/experiments/whrrari/positions?mode=crypto'), api.get('/experiments/whrrari/closed?mode=crypto&limit=50'),
        ]);
        setWhReport(rpt.data); setWhEvals(evals.data);
        setWhUnitPos(uP.data); setWhUnitClosed(uC.data);
        setWhSandboxPos(sP.data); setWhSandboxClosed(sC.data);
        setWhCryptoPos(cP.data); setWhCryptoClosed(cC.data);
      }
    } catch { /* silent */ }
  }, [activeTab]);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 10000);
    return () => clearInterval(iv);
  }, [refresh]);

  const tabConfig = [
    { id: 'shadow_sniper', label: 'EV-Gap + Stoikov', icon: Zap, wave: 0, color: 'indigo' },
    { id: 'moondev', label: 'MoonDev 5m/15m', icon: Zap, wave: 1, color: 'violet' },
    { id: 'phantom', label: 'Phantom Spread', icon: Ghost, wave: 1, color: 'emerald' },
    { id: 'whrrari', label: 'Whrrari LMSR', icon: BarChart3, wave: 1, color: 'amber' },
    { id: 'marik', label: 'Marik Latency', icon: Clock, wave: 2, color: 'zinc' },
    { id: 'argona', label: 'Argona Macro', icon: Globe, wave: 2, color: 'zinc' },
  ];

  const getExpStatus = (id) => {
    const exp = registry.find(e => e.id === id);
    return exp?.status || 'unknown';
  };

  return (
    <div data-testid="quant-lab-page" className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FlaskConical size={20} className="text-indigo-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Quant Lab</h1>
          <span className="text-[10px] font-mono text-zinc-600 bg-zinc-800/60 px-2 py-0.5 rounded">EPOCH 3</span>
        </div>
        <span className="text-xs text-zinc-600 font-mono">
          {registry.filter(e => e.status === 'active').length} active / {registry.length} total experiments
        </span>
      </div>

      {/* Global Shadow Banner */}
      <div data-testid="shadow-banner" className="flex items-center gap-3 px-4 py-2.5 border border-dashed border-indigo-500/40 bg-indigo-950/20 rounded-lg flex-wrap">
        <div className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse shrink-0" />
        <span className="text-xs font-semibold text-indigo-300 tracking-wide uppercase">Shadow Only — No Live Execution</span>
        <span className="text-xs text-zinc-500">All experiments are hypothetical research. None place live orders.</span>
      </div>

      {/* Experiment Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800 mb-3 flex-wrap h-auto gap-1 p-1">
          {tabConfig.map(t => {
            const status = getExpStatus(t.id);
            const isPlanned = status === 'planned';
            return (
              <TabsTrigger key={t.id} value={t.id} data-testid={`tab-${t.id}`}
                className={`text-xs gap-1.5 ${isPlanned ? 'opacity-50' : ''}`}>
                <t.icon size={12} />
                {t.label}
                {t.wave > 0 && (
                  <span className={`text-[9px] font-mono ml-1 px-1 rounded ${
                    isPlanned ? 'bg-zinc-800 text-zinc-600' : 'bg-zinc-800 text-zinc-400'
                  }`}>W{t.wave}</span>
                )}
                {isPlanned && <span className="text-[9px] text-zinc-600 ml-0.5">PLANNED</span>}
              </TabsTrigger>
            );
          })}
        </TabsList>

        {/* Shadow Sniper (Wave 0) */}
        <TabsContent value="shadow_sniper">
          <ShadowSniperTab report={ssReport} evaluations={ssEvals}
            unitPositions={ssUnitPos} lePositions={ssLePos}
            unitClosed={ssUnitClosed} leClosed={ssLeClosed} />
        </TabsContent>

        {/* MoonDev (Wave 1) */}
        <TabsContent value="moondev">
          <ExperimentTab
            testId="moondev"
            title="MoonDev Short Window"
            description="Shadow sniper restricted to 5m and 15m crypto windows only. Compares against full-window live sniper."
            badgeColor="violet"
            report={mdReport}
            evaluations={mdEvals}
            positions={mdPositions}
            closed={mdClosed}
            evalCols={moondevEvalCols}
            posCols={moondevPosCols}
            closedCols={genericClosedCols}
            hasDualMode={true}
          />
        </TabsContent>

        {/* Phantom Spread (Wave 1 — One-Side + Gabagool) */}
        <TabsContent value="phantom">
          <PhantomTab report={phReport} evaluations={phEvals}
            positions={phPositions} closed={phClosed}
            gabaPositions={phGabaPos} gabaClosed={phGabaClosed} />
        </TabsContent>

        {/* Whrrari LMSR (Wave 1 — 3 sizing modes) */}
        <TabsContent value="whrrari">
          <WhrrariTab report={whReport} evaluations={whEvals}
            unitPositions={whUnitPos} unitClosed={whUnitClosed}
            sandboxPositions={whSandboxPos} sandboxClosed={whSandboxClosed}
            cryptoPositions={whCryptoPos} cryptoClosed={whCryptoClosed} />
        </TabsContent>

        {/* Marik (Wave 2 — Planned) */}
        <TabsContent value="marik">
          <PlannedExperiment name="Marik Latency Execution" wave={2}
            description="Latency-sensitive execution timing analysis. Evaluates whether sub-second order timing can capture spread edges before they close. Requires 2-second WebSocket polling infrastructure (not yet built)."
            prerequisites={['Sub-second market data polling', 'Execution timing model', 'Fill latency benchmarking']} />
        </TabsContent>

        {/* Argona (Wave 2 — Planned) */}
        <TabsContent value="argona">
          <PlannedExperiment name="Argona Macro Event" wave={2}
            description="Macro economic event-driven strategy. Detects scheduled events (CPI, FOMC, earnings) and evaluates prediction market pricing dislocations around announcement windows. Requires external event calendar API."
            prerequisites={['External macro event calendar API', 'Event impact model', 'Pre/post-announcement spread analysis']} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ---- Shadow Sniper (existing, refactored into sub-component) ----

function ShadowSniperTab({ report, evaluations, unitPositions, lePositions, unitClosed, leClosed }) {
  const comp = report?.comparison || {};
  const live = comp.live || {};
  const signals = comp.shadow_signals || {};
  const unit = report?.unit_size || {};
  const le = report?.live_equivalent || {};
  const sizing = report?.sizing || {};
  const cfg = report?.config || {};
  const totalEvals = report?.total_evaluations || 0;
  const meaningfulEvals = report?.meaningful_evaluations || 0;

  return (
    <div className="space-y-4" data-testid="shadow-sniper-tab">
      <ExperimentHeader title="EV-Gap + Stoikov Shadow" badgeColor="indigo"
        description="Parallel EV-gap + pseudo-Stoikov evaluation. Tracks both unit-size and live-equivalent hypothetical PnL."
        status={report?.status} lastEval={report?.last_eval_time}
        subtitle={`${totalEvals} evals (${meaningfulEvals} meaningful)`} />

      {/* Signal comparison metrics */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MC t="metric-live-signals" l="Live Signals" v={live.trade_count ?? 0} s="actual fills" />
        <MC t="metric-shadow-signals" l="Shadow Signals" v={signals.trade_count ?? 0} s="would-trade" a />
        <MC t="metric-agreement" l="Agreement Rate"
          v={comp.meaningful_agreement_rate != null ? formatPercent(comp.meaningful_agreement_rate * 100, 1) : '--'}
          s={`${meaningfulEvals} meaningful`} />
        <MC t="metric-fp" l="False Positives" v={comp.false_positives ?? 0} s="shadow traded, loss" />
        <MC t="metric-fn" l="False Negatives" v={comp.false_negatives ?? 0} s="shadow skip, live won" />
      </div>

      {/* Dual-mode PnL comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ModeCard testId="mode-unit" title="Unit-Size" badge="Research Normalization" badgeColor="amber"
          description={sizing.unit?.note || 'Flat per-signal, no accumulation'} stats={unit} />
        <ModeCard testId="mode-le" title="Live-Equivalent" badge="Hypothetical Real-World" badgeColor="cyan"
          description={sizing.live_equivalent?.note || 'Same sizing/accumulation as live'} stats={le} />
      </div>

      {/* Config */}
      <SectionCard title="Shadow Config" testId="section-shadow-config">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-x-6 gap-y-2 text-xs">
          <CR l="EV-Gap" v={cfg.min_ev_ratio != null ? `${(cfg.min_ev_ratio * 100).toFixed(1)}%` : '--'} />
          <CR l="Stoikov" v="Enabled" active />
          <CR l="Gamma" v={cfg.gamma ?? '--'} />
          <CR l="Inv Decay" v={cfg.inventory_decay ?? '--'} />
          <CR l="Unit Size" v={`$${sizing.unit?.per_signal || '?'}`} />
          <CR l="LE Max" v={sizing.live_equivalent?.max_size ?? '--'} />
        </div>
      </SectionCard>

      {/* Data tables */}
      <Tabs defaultValue="le-open">
        <TabsList className="bg-zinc-900 border border-zinc-800 mb-3">
          <TabsTrigger value="le-open" data-testid="tab-ss-le-open">LE Open ({lePositions.length})</TabsTrigger>
          <TabsTrigger value="le-closed" data-testid="tab-ss-le-closed">LE Closed ({leClosed.length})</TabsTrigger>
          <TabsTrigger value="unit-open" data-testid="tab-ss-unit-open">Unit Open ({unitPositions.length})</TabsTrigger>
          <TabsTrigger value="unit-closed" data-testid="tab-ss-unit-closed">Unit Closed ({unitClosed.length})</TabsTrigger>
          <TabsTrigger value="evals" data-testid="tab-ss-evals">Evaluations ({evaluations.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="le-open">
          <DataTable columns={leOpenCols} data={lePositions} emptyMessage="No LE hypothetical positions" testId="ss-le-open-table" />
        </TabsContent>
        <TabsContent value="le-closed">
          <DataTable columns={ssClosedCols} data={leClosed} emptyMessage="No LE resolved trades" testId="ss-le-closed-table" />
        </TabsContent>
        <TabsContent value="unit-open">
          <DataTable columns={unitOpenCols} data={unitPositions} emptyMessage="No unit hypothetical positions" testId="ss-unit-open-table" />
        </TabsContent>
        <TabsContent value="unit-closed">
          <DataTable columns={ssClosedCols} data={unitClosed} emptyMessage="No unit resolved trades" testId="ss-unit-closed-table" />
        </TabsContent>
        <TabsContent value="evals">
          <DataTable columns={ssEvalCols} data={evaluations} emptyMessage="Waiting for scan cycle" testId="ss-evals-table" />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ---- Phantom Tab (One-Side + Gabagool Both-Sides) ----

function PhantomTab({ report, evaluations, positions, closed, gabaPositions, gabaClosed }) {
  const metrics = report?.metrics || {};
  const config = report?.config || {};
  const unitStats = report?.unit_size || {};
  const gabaStats = report?.gabagool || {};
  const sufficient = report?.sample_size_sufficient;

  return (
    <div className="space-y-4" data-testid="phantom-tab">
      <ExperimentHeader title="Phantom Spread + Gabagool" badgeColor="emerald"
        description="Spread dislocation detection (one-side) + Gabagool both-sides structural arbitrage (buy YES+NO when sum < $0.96)."
        status={report?.status} lastEval={report?.last_scan_time} />

      {sufficient === false && (
        <div data-testid="phantom-sample-warning" className="flex items-center gap-2 px-3 py-2 border border-amber-500/30 bg-amber-950/15 rounded-lg">
          <AlertTriangle size={14} className="text-amber-400 shrink-0" />
          <span className="text-xs text-amber-300">Sample size too small for reliable metrics. Collecting data...</span>
        </div>
      )}

      {/* Two mode cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div data-testid="ph-mode-unit" className="border border-emerald-500/25 bg-emerald-950/10 rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className="text-sm font-semibold text-zinc-100">One-Side Spread</span>
            </div>
            <span className="text-[9px] font-mono border border-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded">Directional</span>
          </div>
          <div className="text-[11px] text-zinc-500">Buy cheaper side when YES+NO spread &gt; {config.min_spread_bps || 80}bps</div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <MiniStat label="PnL" value={formatPnl(unitStats.pnl_total || 0)} pnl />
            <MiniStat label="Win Rate" value={unitStats.binary_win_rate != null ? formatPercent(unitStats.binary_win_rate * 100, 1) : '--'} />
            <MiniStat label="Open" value={unitStats.open_positions ?? 0} />
            <MiniStat label="Closed" value={unitStats.closed_trades ?? 0} />
            <MiniStat label="PnL/Trade" value={unitStats.pnl_per_trade != null ? formatPnl(unitStats.pnl_per_trade) : '--'} pnl />
            <MiniStat label="Exposure" value={unitStats.open_exposure != null ? `$${unitStats.open_exposure.toFixed(2)}` : '--'} />
          </div>
        </div>

        <div data-testid="ph-mode-gabagool" className="border border-cyan-500/25 bg-cyan-950/10 rounded-lg p-4 space-y-3 ring-1 ring-cyan-500/20">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
              <span className="text-sm font-semibold text-zinc-100">Gabagool Both-Sides</span>
            </div>
            <span className="text-[9px] font-mono border border-cyan-500/20 text-cyan-400 px-1.5 py-0.5 rounded">Guaranteed Arb</span>
          </div>
          <div className="text-[11px] text-zinc-500">Buy YES + NO when sum &lt; ${config.gabagool_threshold || 0.96} — guaranteed profit at resolution</div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <MiniStat label="PnL" value={formatPnl(gabaStats.pnl_total || 0)} pnl />
            <MiniStat label="Win Rate" value={gabaStats.binary_win_rate != null ? formatPercent(gabaStats.binary_win_rate * 100, 1) : '--'} />
            <MiniStat label="Open Pairs" value={gabaStats.open_positions ?? 0} />
            <MiniStat label="Closed" value={gabaStats.closed_trades ?? 0} />
            <MiniStat label="PnL/Pair" value={gabaStats.pnl_per_trade != null ? formatPnl(gabaStats.pnl_per_trade) : '--'} pnl />
            <MiniStat label="Exposure" value={gabaStats.open_exposure != null ? `$${gabaStats.open_exposure.toFixed(2)}` : '--'} />
          </div>
        </div>
      </div>

      {/* Engine Metrics */}
      <SectionCard title="Engine Metrics" testId="phantom-metrics">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 text-xs">
          {Object.entries(metrics).filter(([k]) => k !== 'last_scan_time').map(([k, v]) => (
            <CR key={k} l={k.replace(/_/g, ' ')} v={typeof v === 'number' ? v.toLocaleString() : String(v ?? '--')} />
          ))}
        </div>
      </SectionCard>

      {/* Data tables */}
      <Tabs defaultValue="gaba-open">
        <TabsList className="bg-zinc-900 border border-zinc-800 mb-3 flex-wrap h-auto gap-1 p-1">
          <TabsTrigger value="gaba-open" data-testid="tab-ph-gaba-open">Gabagool Open ({gabaPositions.length})</TabsTrigger>
          <TabsTrigger value="gaba-closed" data-testid="tab-ph-gaba-closed">Gabagool Closed ({gabaClosed.length})</TabsTrigger>
          <TabsTrigger value="unit-open" data-testid="tab-ph-unit-open">One-Side Open ({positions.length})</TabsTrigger>
          <TabsTrigger value="unit-closed" data-testid="tab-ph-unit-closed">One-Side Closed ({closed.length})</TabsTrigger>
          <TabsTrigger value="evals" data-testid="tab-ph-evals">Evaluations ({evaluations.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="gaba-open">
          <DataTable columns={gabagoolOpenCols} data={gabaPositions} emptyMessage="No Gabagool pairs open" testId="ph-gaba-open-table" />
        </TabsContent>
        <TabsContent value="gaba-closed">
          <DataTable columns={gabagoolClosedCols} data={gabaClosed} emptyMessage="No Gabagool pairs resolved" testId="ph-gaba-closed-table" />
        </TabsContent>
        <TabsContent value="unit-open">
          <DataTable columns={phantomPosCols} data={positions} emptyMessage="No one-side positions" testId="ph-unit-open-table" />
        </TabsContent>
        <TabsContent value="unit-closed">
          <DataTable columns={genericClosedCols} data={closed} emptyMessage="No one-side resolved" testId="ph-unit-closed-table" />
        </TabsContent>
        <TabsContent value="evals">
          <DataTable columns={phantomEvalCols} data={evaluations} emptyMessage="Waiting for scan cycle" testId="ph-evals-table" />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ---- Whrrari Tab (3 Sizing Modes) ----

function WhrrariTab({ report, evaluations, unitPositions, unitClosed, sandboxPositions, sandboxClosed, cryptoPositions, cryptoClosed }) {
  const metrics = report?.metrics || {};
  const config = report?.config || {};
  const sufficient = report?.sample_size_sufficient;
  const unit = report?.unit_size || {};
  const sandbox = report?.sandbox_notional || {};
  const crypto = report?.crypto_mirrored || {};

  return (
    <div className="space-y-4" data-testid="whrrari-tab">
      <ExperimentHeader title="Whrrari Fair-Value / LMSR" badgeColor="amber"
        description="LMSR-inspired fair-value model for multi-outcome markets. 3 independent sizing modes tracked in parallel."
        status={report?.status} lastEval={report?.last_scan_time} />

      {sufficient === false && (
        <div data-testid="whrrari-sample-warning" className="flex items-center gap-2 px-3 py-2 border border-amber-500/30 bg-amber-950/15 rounded-lg">
          <AlertTriangle size={14} className="text-amber-400 shrink-0" />
          <span className="text-xs text-amber-300">Sample size too small for reliable metrics. Collecting data...</span>
        </div>
      )}

      {/* 3 Mode Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <WhrrariModeCard testId="wh-mode-unit" title="Unit-Size" label="Normalized Research"
          labelColor="border-amber-500/20 text-amber-400 bg-amber-950/10"
          borderColor="border-amber-500/25 bg-amber-950/10"
          dotColor="bg-amber-400"
          note="Flat $3/signal · No accumulation · Signal quality comparison"
          stats={unit} primary={false} />
        <WhrrariModeCard testId="wh-mode-sandbox" title="Sandbox Notional" label="Primary Promotion Metric"
          labelColor="border-emerald-500/20 text-emerald-400 bg-emerald-950/10"
          borderColor="border-emerald-500/25 bg-emerald-950/10"
          dotColor="bg-emerald-400"
          note="Edge-tiered: $3 (300-599bps) · $8 (600-899bps) · $15 (900+bps)"
          stats={sandbox} primary={true} />
        <WhrrariModeCard testId="wh-mode-crypto" title="Crypto-Mirrored" label="Hypothetical Stress Test"
          labelColor="border-red-500/20 text-red-400 bg-red-950/10"
          borderColor="border-red-500/25 bg-red-950/10"
          dotColor="bg-red-400"
          note="$3/signal accumulating to $25 cap · NOT a realistic arb benchmark"
          stats={crypto} primary={false} />
      </div>

      {/* Engine Metrics */}
      {Object.keys(metrics).length > 0 && (
        <SectionCard title="Engine Metrics" testId="whrrari-metrics">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 text-xs">
            {Object.entries(metrics).filter(([k]) => k !== 'last_scan_time').map(([k, v]) => (
              <CR key={k} l={k.replace(/_/g, ' ')} v={typeof v === 'number' ? v.toLocaleString() : String(v ?? '--')} />
            ))}
          </div>
        </SectionCard>
      )}

      {/* Config */}
      {Object.keys(config).length > 0 && (
        <SectionCard title="Config" testId="whrrari-config">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2 text-xs">
            {Object.entries(config).map(([k, v]) => (
              <CR key={k} l={k.replace(/_/g, ' ')} v={String(v)} />
            ))}
          </div>
        </SectionCard>
      )}

      {/* Data tables — scoped by mode */}
      <Tabs defaultValue="sandbox-open">
        <TabsList className="bg-zinc-900 border border-zinc-800 mb-3 flex-wrap h-auto gap-1 p-1">
          <TabsTrigger value="sandbox-open" data-testid="tab-wh-sandbox-open">Sandbox Open ({sandboxPositions.length})</TabsTrigger>
          <TabsTrigger value="sandbox-closed" data-testid="tab-wh-sandbox-closed">Sandbox Closed ({sandboxClosed.length})</TabsTrigger>
          <TabsTrigger value="unit-open" data-testid="tab-wh-unit-open">Unit Open ({unitPositions.length})</TabsTrigger>
          <TabsTrigger value="unit-closed" data-testid="tab-wh-unit-closed">Unit Closed ({unitClosed.length})</TabsTrigger>
          <TabsTrigger value="crypto-open" data-testid="tab-wh-crypto-open">Stress Open ({cryptoPositions.length})</TabsTrigger>
          <TabsTrigger value="crypto-closed" data-testid="tab-wh-crypto-closed">Stress Closed ({cryptoClosed.length})</TabsTrigger>
          <TabsTrigger value="evals" data-testid="tab-wh-evals">Evaluations ({evaluations.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="sandbox-open">
          <DataTable columns={whrrariSandboxPosCols} data={sandboxPositions} emptyMessage="No sandbox positions" testId="wh-sandbox-open-table" />
        </TabsContent>
        <TabsContent value="sandbox-closed">
          <DataTable columns={whrrariSandboxClosedCols} data={sandboxClosed} emptyMessage="No sandbox resolved" testId="wh-sandbox-closed-table" />
        </TabsContent>
        <TabsContent value="unit-open">
          <DataTable columns={whrrariPosCols} data={unitPositions} emptyMessage="No unit positions" testId="wh-unit-open-table" />
        </TabsContent>
        <TabsContent value="unit-closed">
          <DataTable columns={genericClosedCols} data={unitClosed} emptyMessage="No unit resolved" testId="wh-unit-closed-table" />
        </TabsContent>
        <TabsContent value="crypto-open">
          <DataTable columns={whrrariCryptoPosCols} data={cryptoPositions} emptyMessage="No crypto-mirrored positions" testId="wh-crypto-open-table" />
        </TabsContent>
        <TabsContent value="crypto-closed">
          <DataTable columns={genericClosedCols} data={cryptoClosed} emptyMessage="No crypto-mirrored resolved" testId="wh-crypto-closed-table" />
        </TabsContent>
        <TabsContent value="evals">
          <DataTable columns={whrrariEvalCols} data={evaluations} emptyMessage="Waiting for scan cycle" testId="wh-evals-table" />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function WhrrariModeCard({ testId, title, label, labelColor, borderColor, dotColor, note, stats, primary }) {
  return (
    <div data-testid={testId} className={`border rounded-lg p-4 space-y-3 ${borderColor} ${primary ? 'ring-1 ring-emerald-500/30' : ''}`}>
      <div className="flex items-center justify-between flex-wrap gap-1">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${dotColor}`} />
          <span className="text-sm font-semibold text-zinc-100">{title}</span>
        </div>
        <span className={`text-[9px] font-mono border rounded px-1.5 py-0.5 ${labelColor}`}>{label}</span>
      </div>
      <div className="text-[11px] text-zinc-500">{note}</div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <MiniStat label="PnL" value={formatPnl(stats.pnl_total || 0)} pnl />
        <MiniStat label="PnL/Trade" value={stats.pnl_per_trade != null ? formatPnl(stats.pnl_per_trade) : '--'} pnl />
        <MiniStat label="Win Rate" value={stats.binary_win_rate != null ? formatPercent(stats.binary_win_rate * 100, 1) : '--'} />
        <MiniStat label="Open" value={stats.open_positions ?? 0} />
        <MiniStat label="Closed" value={stats.closed_trades ?? 0} />
        <MiniStat label="Exposure" value={stats.open_exposure != null ? `$${stats.open_exposure.toFixed(2)}` : '--'} />
        <MiniStat label="Rolling 1h" value={formatPnl(stats.rolling_pnl?.['1h'] || 0)} pnl />
        <MiniStat label="Rolling 3h" value={formatPnl(stats.rolling_pnl?.['3h'] || 0)} pnl />
        <MiniStat label="Rolling 6h" value={formatPnl(stats.rolling_pnl?.['6h'] || 0)} pnl />
      </div>
    </div>
  );
}

// ---- Generic Wave 1 Experiment Tab ----

function ExperimentTab({ testId, title, description, badgeColor, report, evaluations, positions, closed, evalCols, posCols, closedCols, hasDualMode }) {
  const stats = report?.unit_size || {};
  const metrics = report?.metrics || {};
  const config = report?.config || {};
  const sufficient = report?.sample_size_sufficient;

  return (
    <div className="space-y-4" data-testid={`${testId}-tab`}>
      <ExperimentHeader title={title} badgeColor={badgeColor} description={description}
        status={report?.status} lastEval={report?.last_scan_time || report?.last_eval_time} />

      {sufficient === false && (
        <div data-testid={`${testId}-sample-warning`} className="flex items-center gap-2 px-3 py-2 border border-amber-500/30 bg-amber-950/15 rounded-lg">
          <AlertTriangle size={14} className="text-amber-400 shrink-0" />
          <span className="text-xs text-amber-300">Sample size too small for reliable metrics. Collecting data...</span>
        </div>
      )}

      {/* Metrics grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MC t={`${testId}-trades`} l="Hypothetical Trades" v={stats.closed_trades ?? 0} s="resolved" a />
        <MC t={`${testId}-open`} l="Open Positions" v={stats.open_positions ?? 0} s={`$${stats.open_exposure?.toFixed(2) || '0'} exposure`} />
        <MC t={`${testId}-winrate`} l="Win Rate (Binary)" v={stats.binary_win_rate != null ? formatPercent(stats.binary_win_rate * 100, 1) : '--'} s={`${stats.binary_resolved ?? 0} binary resolved`} />
        <MC t={`${testId}-pnl`} l="Total PnL" v={formatPnl(stats.pnl_total || 0)} />
        <MC t={`${testId}-pnl-trade`} l="PnL / Trade" v={stats.pnl_per_trade != null ? formatPnl(stats.pnl_per_trade) : '--'} />
      </div>

      {/* Rolling PnL */}
      {stats.rolling_pnl && (
        <div className="grid grid-cols-3 gap-3">
          <MC t={`${testId}-roll-1h`} l="Rolling 1h PnL" v={formatPnl(stats.rolling_pnl['1h'] || 0)} />
          <MC t={`${testId}-roll-3h`} l="Rolling 3h PnL" v={formatPnl(stats.rolling_pnl['3h'] || 0)} />
          <MC t={`${testId}-roll-6h`} l="Rolling 6h PnL" v={formatPnl(stats.rolling_pnl['6h'] || 0)} />
        </div>
      )}

      {/* Experiment-specific metrics */}
      {Object.keys(metrics).length > 0 && (
        <SectionCard title="Engine Metrics" testId={`${testId}-metrics`}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 text-xs">
            {Object.entries(metrics).filter(([k]) => k !== 'last_scan_time' && k !== 'last_eval_time').map(([k, v]) => (
              <CR key={k} l={k.replace(/_/g, ' ')} v={typeof v === 'number' ? v.toLocaleString() : String(v ?? '--')} />
            ))}
          </div>
        </SectionCard>
      )}

      {/* Config */}
      {Object.keys(config).length > 0 && (
        <SectionCard title="Config" testId={`${testId}-config`}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 text-xs">
            {Object.entries(config).map(([k, v]) => (
              <CR key={k} l={k.replace(/_/g, ' ')} v={String(v)} />
            ))}
          </div>
        </SectionCard>
      )}

      {/* Mode label */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-zinc-600 font-mono uppercase tracking-wider">
          {hasDualMode ? 'Unit-Size + Live-Equivalent' : 'Unit-Size Research Mode'}
        </span>
      </div>

      {/* Data tables */}
      <Tabs defaultValue="positions">
        <TabsList className="bg-zinc-900 border border-zinc-800 mb-3">
          <TabsTrigger value="positions" data-testid={`tab-${testId}-pos`}>Open ({positions.length})</TabsTrigger>
          <TabsTrigger value="closed" data-testid={`tab-${testId}-closed`}>Closed ({closed.length})</TabsTrigger>
          <TabsTrigger value="evals" data-testid={`tab-${testId}-evals`}>Evaluations ({evaluations.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="positions">
          <DataTable columns={posCols} data={positions} emptyMessage="No hypothetical positions" testId={`${testId}-pos-table`} />
        </TabsContent>
        <TabsContent value="closed">
          <DataTable columns={closedCols} data={closed} emptyMessage="No resolved trades yet" testId={`${testId}-closed-table`} />
        </TabsContent>
        <TabsContent value="evals">
          <DataTable columns={evalCols} data={evaluations} emptyMessage="Waiting for scan cycle" testId={`${testId}-evals-table`} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ---- Wave 2 Planned Experiment ----

function PlannedExperiment({ name, wave, description, prerequisites }) {
  return (
    <div data-testid={`planned-${name.toLowerCase().replace(/\s/g, '-')}`} className="space-y-4">
      <div className="border border-dashed border-zinc-700 bg-zinc-900/30 rounded-lg p-6 text-center space-y-4">
        <div className="flex items-center justify-center gap-2">
          <Clock size={20} className="text-zinc-600" />
          <h2 className="text-base font-semibold text-zinc-400">{name}</h2>
          <span className="text-[9px] font-mono bg-zinc-800 text-zinc-500 px-1.5 py-0.5 rounded">WAVE {wave}</span>
        </div>
        <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-zinc-800/60 border border-zinc-700 rounded-full">
          <div className="w-1.5 h-1.5 rounded-full bg-zinc-600" />
          <span className="text-xs font-mono text-zinc-500 uppercase tracking-wider">Planned / Inactive / Not Yet Running</span>
        </div>
        <p className="text-sm text-zinc-500 max-w-lg mx-auto">{description}</p>
        {prerequisites && (
          <div className="text-left max-w-md mx-auto">
            <p className="text-[10px] text-zinc-600 uppercase tracking-wider mb-2">Prerequisites</p>
            {prerequisites.map((p, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-zinc-500 py-1">
                <div className="w-1 h-1 rounded-full bg-zinc-700 shrink-0" />
                <span>{p}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---- Shared Components ----

function ExperimentHeader({ title, badgeColor, description, status, lastEval, subtitle }) {
  const colorMap = {
    indigo: 'border-indigo-500/30 bg-indigo-950/15 text-indigo-300',
    violet: 'border-violet-500/30 bg-violet-950/15 text-violet-300',
    emerald: 'border-emerald-500/30 bg-emerald-950/15 text-emerald-300',
    amber: 'border-amber-500/30 bg-amber-950/15 text-amber-300',
  };
  const dotColor = {
    indigo: 'bg-indigo-400', violet: 'bg-violet-400',
    emerald: 'bg-emerald-400', amber: 'bg-amber-400',
  };
  const classes = colorMap[badgeColor] || colorMap.indigo;

  return (
    <div className={`border rounded-lg px-4 py-3 ${classes}`}>
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <div className={`w-2 h-2 rounded-full ${dotColor[badgeColor] || dotColor.indigo} ${status === 'active' ? 'animate-pulse' : ''}`} />
          <h2 className="text-sm font-semibold">{title}</h2>
          <span className="text-[9px] font-mono bg-black/20 px-1.5 py-0.5 rounded uppercase tracking-wider">Shadow Only</span>
        </div>
        <div className="text-[10px] text-zinc-500 font-mono">
          {subtitle || (lastEval ? `Last: ${formatTimeAgo(lastEval)}` : 'Collecting...')}
        </div>
      </div>
      <p className="text-[11px] text-zinc-500 mt-1">{description}</p>
    </div>
  );
}

function ModeCard({ testId, title, badge, badgeColor, description, stats }) {
  const bc = badgeColor === 'cyan' ? 'border-cyan-500/30 bg-cyan-950/15' : 'border-amber-500/30 bg-amber-950/15';
  const tc = badgeColor === 'cyan' ? 'text-cyan-300' : 'text-amber-300';
  const bc2 = badgeColor === 'cyan' ? 'border-cyan-500/20 text-cyan-400' : 'border-amber-500/20 text-amber-400';
  return (
    <div data-testid={testId} className={`border rounded-lg p-4 space-y-3 ${bc}`}>
      <div className="flex items-center justify-between">
        <span className={`text-sm font-semibold ${tc}`}>{title}</span>
        <span className={`text-[10px] font-mono border rounded px-1.5 py-0.5 ${bc2}`}>{badge}</span>
      </div>
      <div className="text-[11px] text-zinc-500">{description}</div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <MiniStat label="PnL" value={formatPnl(stats.pnl_total || 0)} pnl />
        <MiniStat label="PnL/Trade" value={stats.pnl_per_trade != null ? formatPnl(stats.pnl_per_trade) : '--'} pnl />
        <MiniStat label="Win Rate" value={stats.binary_win_rate != null ? formatPercent(stats.binary_win_rate * 100, 1) : '--'} />
        <MiniStat label="Open" value={stats.open_positions ?? 0} />
        <MiniStat label="Closed" value={stats.closed_trades ?? 0} />
        <MiniStat label="Exposure" value={stats.open_exposure != null ? `$${stats.open_exposure.toFixed(2)}` : '--'} />
        <MiniStat label="Total Size" value={stats.open_total_size != null ? `${stats.open_total_size}` : '--'} />
        <MiniStat label="Rolling 1h" value={formatPnl(stats.rolling_pnl?.['1h'] || 0)} pnl />
        <MiniStat label="Rolling 6h" value={formatPnl(stats.rolling_pnl?.['6h'] || 0)} pnl />
      </div>
    </div>
  );
}

function MiniStat({ label, value, pnl }) {
  let c = 'text-zinc-200';
  if (pnl && typeof value === 'string') {
    if (value.startsWith('+') && value !== '+$0.00') c = 'text-emerald-400';
    else if (value.startsWith('-')) c = 'text-red-400';
    else c = 'text-zinc-400';
  }
  return (
    <div>
      <div className="text-[10px] text-zinc-500">{label}</div>
      <div className={`font-mono text-sm font-medium ${c}`}>{value ?? '--'}</div>
    </div>
  );
}

function MC({ t, l, v, s, a }) {
  return (
    <div data-testid={t} className={`border rounded-lg px-4 py-3 ${a ? 'bg-indigo-950/20 border-indigo-500/20' : 'bg-zinc-900/60 border-zinc-800'}`}>
      <div className="text-[11px] text-zinc-500 mb-1">{l}</div>
      <div className={`text-base font-semibold font-mono ${a ? 'text-indigo-300' : 'text-zinc-100'}`}>{v ?? '--'}</div>
      {s && <div className="text-[10px] text-zinc-600 mt-0.5">{s}</div>}
    </div>
  );
}

function CR({ l, v, active }) {
  return (
    <div className="flex justify-between py-1 text-xs">
      <span className="text-zinc-500">{l}</span>
      <span className={`font-mono ${active ? 'text-indigo-300' : 'text-zinc-300'}`}>{v}</span>
    </div>
  );
}

// ---- Table Columns ----

// Shadow Sniper (existing)
const leOpenCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[160px] truncate block">{truncate(v, 40)}</span> },
  { key: 'asset', label: 'Asset', render: v => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'side', label: 'Side', render: v => <span className={v === 'buy_yes' ? 'text-emerald-400' : v === 'buy_no' ? 'text-red-400' : 'text-zinc-500'}>{v}</span> },
  { key: 'size', label: 'Size', align: 'right', sortable: true, render: v => <span className="font-mono text-cyan-300 font-medium">{v}</span> },
  { key: 'fills', label: 'Fills', align: 'right', render: v => <span className="font-mono text-zinc-400">{v}</span> },
  { key: 'avg_entry', label: 'Avg Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'current_price', label: 'Mark', align: 'right', render: v => <span className="font-mono text-zinc-200">{v != null ? formatPrice(v) : '--'}</span> },
  { key: 'unrealized_pnl', label: 'Unrl PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-medium ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'opened_at', label: 'Opened', render: v => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
];

const unitOpenCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[160px] truncate block">{truncate(v, 40)}</span> },
  { key: 'asset', label: 'Asset', render: v => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'side', label: 'Side', render: v => <span className={v === 'buy_yes' ? 'text-emerald-400' : v === 'buy_no' ? 'text-red-400' : 'text-zinc-500'}>{v}</span> },
  { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono text-amber-300">{v}</span> },
  { key: 'entry_price', label: 'Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'current_price', label: 'Mark', align: 'right', render: v => <span className="font-mono text-zinc-200">{v != null ? formatPrice(v) : '--'}</span> },
  { key: 'unrealized_pnl', label: 'Unrl PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-medium ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'opened_at', label: 'Opened', render: v => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
];

const ssClosedCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[160px] truncate block">{truncate(v, 40)}</span> },
  { key: 'asset', label: 'Asset', render: v => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'side', label: 'Side', render: v => <span className={v === 'buy_yes' ? 'text-emerald-400' : v === 'buy_no' ? 'text-red-400' : 'text-zinc-500'}>{v}</span> },
  { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono">{v}</span> },
  { key: 'avg_entry', label: 'Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'exit_price', label: 'Exit', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'pnl', label: 'PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-semibold ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'won', label: 'Result', render: v => <span className={v ? 'text-emerald-400' : 'text-red-400'}>{v ? 'WIN' : 'LOSS'}</span> },
  { key: 'resolution_type', label: 'Resolution', render: v => <ResType v={v} /> },
  { key: 'closed_at', label: 'Closed', render: v => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
];

const ssEvalCols = [
  { key: 'timestamp', label: 'Time', render: v => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-400 max-w-[140px] truncate block">{truncate(v, 35)}</span> },
  { key: 'asset', label: 'Asset', render: v => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'live_decision', label: 'Live', render: v => <span className={v?.startsWith('trade') ? 'text-emerald-400 font-medium' : 'text-zinc-600'}>{v}</span> },
  { key: 'shadow_would_trade', label: 'Shadow', render: v => <span className={v ? 'text-indigo-300 font-medium' : 'text-zinc-600'}>{v ? 'TRADE' : 'skip'}</span> },
  { key: 'ev_ratio', label: 'EV Gap', align: 'right', sortable: true, render: (v, r) => (
    <span className={`font-mono ${r.ev_pass ? 'text-indigo-300' : 'text-zinc-600'}`}>{v != null ? `${(v * 100).toFixed(1)}%` : '--'}</span>
  )},
  { key: 'stoikov_edge_bps', label: 'Stoikov', align: 'right', sortable: true, render: (v, r) => (
    <span className={`font-mono ${r.stoikov_pass ? 'text-indigo-300' : 'text-zinc-600'}`}>{v != null ? formatBps(v) : '--'}</span>
  )},
  { key: 'edge_bps', label: 'Edge', align: 'right', render: v => <span className={`font-mono ${v > 0 ? 'text-amber-400' : 'text-zinc-600'}`}>{formatBps(v)}</span> },
];

// MoonDev columns
const moondevEvalCols = [
  { key: 'timestamp', label: 'Time', render: v => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-400 max-w-[140px] truncate block">{truncate(v, 35)}</span> },
  { key: 'asset', label: 'Asset', render: v => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'window', label: 'Window', render: v => <span className="font-mono text-violet-300">{v}</span> },
  { key: 'live_decision', label: 'Live', render: v => <span className={v?.startsWith('trade') ? 'text-emerald-400' : 'text-zinc-600'}>{v}</span> },
  { key: 'moondev_would_trade', label: 'MoonDev', render: v => <span className={v ? 'text-violet-300 font-medium' : 'text-zinc-600'}>{v ? 'TRADE' : 'skip'}</span> },
  { key: 'edge_bps', label: 'Edge', align: 'right', sortable: true, render: v => <span className={`font-mono ${v > 0 ? 'text-amber-400' : 'text-zinc-600'}`}>{formatBps(v)}</span> },
  { key: 'tte_seconds', label: 'TTE', align: 'right', render: v => <span className="font-mono text-zinc-400">{v ? `${Math.round(v / 60)}m` : '--'}</span> },
];

const moondevPosCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[160px] truncate block">{truncate(v, 40)}</span> },
  { key: 'asset', label: 'Asset', render: v => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'window', label: 'Window', render: v => <span className="font-mono text-violet-300">{v}</span> },
  { key: 'side', label: 'Side', render: v => <span className={v === 'buy_yes' ? 'text-emerald-400' : 'text-red-400'}>{v}</span> },
  { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono text-violet-300">{v}</span> },
  { key: 'avg_entry', label: 'Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'current_price', label: 'Mark', align: 'right', render: v => <span className="font-mono text-zinc-200">{v != null ? formatPrice(v) : '--'}</span> },
  { key: 'unrealized_pnl', label: 'Unrl PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-medium ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'opened_at', label: 'Opened', render: v => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
];

// Phantom columns
const phantomEvalCols = [
  { key: 'timestamp', label: 'Time', render: v => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-400 max-w-[140px] truncate block">{truncate(v, 35)}</span> },
  { key: 'yes_price', label: 'YES', align: 'right', render: v => <span className="font-mono text-emerald-400">{formatPrice(v)}</span> },
  { key: 'no_price', label: 'NO', align: 'right', render: v => <span className="font-mono text-red-400">{formatPrice(v)}</span> },
  { key: 'price_sum', label: 'Sum', align: 'right', render: v => <span className={`font-mono ${Math.abs(1 - (v || 1)) > 0.005 ? 'text-amber-400' : 'text-zinc-400'}`}>{v?.toFixed(4)}</span> },
  { key: 'spread_bps', label: 'Spread', align: 'right', sortable: true, render: v => <span className="font-mono text-emerald-300">{formatBps(v)}</span> },
  { key: 'gabagool_eligible', label: 'Gaba', render: v => <span className={v ? 'text-cyan-300 font-semibold' : 'text-zinc-600'}>{v ? 'YES' : '--'}</span> },
  { key: 'gabagool_edge_pct', label: 'Gaba Edge', align: 'right', render: v => <span className={`font-mono ${(v || 0) > 0 ? 'text-cyan-300' : 'text-zinc-600'}`}>{v ? `${v}%` : '--'}</span> },
  { key: 'would_trade', label: 'Signal', render: v => <span className={v ? 'text-emerald-300 font-medium' : 'text-zinc-600'}>{v ? 'TRADE' : 'skip'}</span> },
];

const phantomPosCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[160px] truncate block">{truncate(v, 40)}</span> },
  { key: 'side', label: 'Side', render: v => <span className={v === 'buy_yes' ? 'text-emerald-400' : 'text-red-400'}>{v}</span> },
  { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono text-emerald-300">{v}</span> },
  { key: 'spread_bps_at_entry', label: 'Spread', align: 'right', render: v => <span className="font-mono text-emerald-300">{formatBps(v)}</span> },
  { key: 'trade_type', label: 'Type', render: v => <span className="font-mono text-xs text-zinc-400">{v}</span> },
  { key: 'avg_entry', label: 'Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'current_price', label: 'Mark', align: 'right', render: v => <span className="font-mono text-zinc-200">{v != null ? formatPrice(v) : '--'}</span> },
  { key: 'unrealized_pnl', label: 'Unrl PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-medium ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'opened_at', label: 'Opened', render: v => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
];

// Whrrari columns
const whrrariEvalCols = [
  { key: 'timestamp', label: 'Time', render: v => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-400 max-w-[140px] truncate block">{truncate(v, 35)}</span> },
  { key: 'outcome_count', label: 'Outcomes', align: 'right', render: v => <span className="font-mono text-zinc-300">{v}</span> },
  { key: 'price_sum', label: 'Price Sum', align: 'right', render: v => <span className={`font-mono ${Math.abs(1 - (v || 1)) > 0.02 ? 'text-amber-400' : 'text-zinc-400'}`}>{v?.toFixed(4)}</span> },
  { key: 'best_edge_bps', label: 'Best Edge', align: 'right', sortable: true, render: v => <span className={`font-mono ${(v || 0) >= 300 ? 'text-amber-400' : 'text-zinc-600'}`}>{formatBps(v)}</span> },
  { key: 'sandbox_size', label: 'Sandbox $', align: 'right', render: v => <span className={`font-mono ${v > 0 ? 'text-emerald-400' : 'text-zinc-600'}`}>{v ? `$${v}` : '--'}</span> },
  { key: 'would_trade', label: 'Signal', render: v => <span className={v ? 'text-amber-300 font-medium' : 'text-zinc-600'}>{v ? 'TRADE' : 'skip'}</span> },
];

const whrrariPosCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[160px] truncate block">{truncate(v, 40)}</span> },
  { key: 'outcome_count', label: 'Outcomes', align: 'right', render: v => <span className="font-mono text-zinc-300">{v}</span> },
  { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono text-amber-300">{v}</span> },
  { key: 'edge_bps_at_entry', label: 'Edge', align: 'right', render: v => <span className="font-mono text-amber-300">{formatBps(v)}</span> },
  { key: 'fair_prob_at_entry', label: 'Fair Prob', align: 'right', render: v => <span className="font-mono text-zinc-300">{v != null ? formatPercent(v * 100, 1) : '--'}</span> },
  { key: 'avg_entry', label: 'Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'current_price', label: 'Mark', align: 'right', render: v => <span className="font-mono text-zinc-200">{v != null ? formatPrice(v) : '--'}</span> },
  { key: 'unrealized_pnl', label: 'Unrl PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-medium ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'opened_at', label: 'Opened', render: v => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
];

const whrrariSandboxPosCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[140px] truncate block">{truncate(v, 35)}</span> },
  { key: 'outcome_count', label: 'Out', align: 'right', render: v => <span className="font-mono text-zinc-300">{v}</span> },
  { key: 'sandbox_band', label: 'Band', render: v => <span className="font-mono text-emerald-300">{v || '--'}</span> },
  { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono text-emerald-300 font-medium">${v}</span> },
  { key: 'edge_bps_at_entry', label: 'Edge', align: 'right', render: v => <span className="font-mono text-amber-300">{formatBps(v)}</span> },
  { key: 'avg_entry', label: 'Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'current_price', label: 'Mark', align: 'right', render: v => <span className="font-mono text-zinc-200">{v != null ? formatPrice(v) : '--'}</span> },
  { key: 'unrealized_pnl', label: 'Unrl PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-medium ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'opened_at', label: 'Opened', render: v => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
];

const whrrariSandboxClosedCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[140px] truncate block">{truncate(v, 35)}</span> },
  { key: 'sandbox_band', label: 'Band', render: v => <span className="font-mono text-emerald-300">{v || '--'}</span> },
  { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono">{v}</span> },
  { key: 'avg_entry', label: 'Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'exit_price', label: 'Exit', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'pnl', label: 'PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-semibold ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'won', label: 'Result', render: v => <span className={v ? 'text-emerald-400' : 'text-red-400'}>{v ? 'WIN' : 'LOSS'}</span> },
  { key: 'resolution_type', label: 'Resolution', render: v => <ResType v={v} /> },
  { key: 'closed_at', label: 'Closed', render: v => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
];

const whrrariCryptoPosCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[140px] truncate block">{truncate(v, 35)}</span> },
  { key: 'outcome_count', label: 'Out', align: 'right', render: v => <span className="font-mono text-zinc-300">{v}</span> },
  { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono text-red-300 font-medium">{v}</span> },
  { key: 'fills', label: 'Fills', align: 'right', render: v => <span className="font-mono text-zinc-400">{v}</span> },
  { key: 'edge_bps_at_entry', label: 'Edge', align: 'right', render: v => <span className="font-mono text-amber-300">{formatBps(v)}</span> },
  { key: 'avg_entry', label: 'Avg Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'current_price', label: 'Mark', align: 'right', render: v => <span className="font-mono text-zinc-200">{v != null ? formatPrice(v) : '--'}</span> },
  { key: 'unrealized_pnl', label: 'Unrl PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-medium ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'opened_at', label: 'Opened', render: v => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
];

// Generic closed columns (works for all experiments)
const genericClosedCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[160px] truncate block">{truncate(v, 40)}</span> },
  { key: 'side', label: 'Side', render: v => <span className={v === 'buy_yes' ? 'text-emerald-400' : v === 'buy_no' ? 'text-red-400' : 'text-zinc-500'}>{v}</span> },
  { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono">{v}</span> },
  { key: 'avg_entry', label: 'Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'exit_price', label: 'Exit', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'pnl', label: 'PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-semibold ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'won', label: 'Result', render: v => <span className={v ? 'text-emerald-400' : 'text-red-400'}>{v ? 'WIN' : 'LOSS'}</span> },
  { key: 'resolution_type', label: 'Resolution', render: v => <ResType v={v} /> },
  { key: 'closed_at', label: 'Closed', render: v => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
];

function ResType({ v }) {
  const c = { resolved_yes: 'text-emerald-400', resolved_no: 'text-red-400', expired_mtm: 'text-amber-500', no_data: 'text-zinc-600' };
  return <span className={`font-mono text-xs ${c[v] || 'text-zinc-500'}`}>{v || '--'}</span>;
}
