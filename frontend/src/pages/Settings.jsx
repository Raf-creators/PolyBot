import { useEffect, useState } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { SectionCard } from '../components/SectionCard';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import { Save, RefreshCw, Send } from 'lucide-react';
import axios from 'axios';
import { API_BASE } from '../utils/constants';

export default function Settings() {
  const config = useDashboardStore((s) => s.config);
  const risk = useDashboardStore((s) => s.risk);
  const mode = useDashboardStore((s) => s.mode);
  const strategies = useDashboardStore((s) => s.strategies);
  const { fetchConfig, updateConfig } = useApi();

  const [riskForm, setRiskForm] = useState({});
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  useEffect(() => {
    if (Object.keys(risk).length > 0) {
      setRiskForm({ ...risk });
      setDirty(false);
    }
  }, [risk]);

  const handleRiskChange = (key, value) => {
    setRiskForm((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const handleSaveRisk = async () => {
    try {
      const payload = {
        risk: {
          max_daily_loss: Number(riskForm.max_daily_loss),
          max_loss_per_strategy: Number(riskForm.max_loss_per_strategy),
          max_position_size: Number(riskForm.max_position_size),
          max_market_exposure: Number(riskForm.max_market_exposure),
          max_concurrent_positions: Number(riskForm.max_concurrent_positions),
          max_order_size: Number(riskForm.max_order_size),
          kill_switch_active: riskForm.kill_switch_active,
        },
      };
      await updateConfig(payload);
      setDirty(false);
      toast.success('Risk configuration updated');
      fetchConfig();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to update config');
    }
  };

  const handleModeChange = async (newMode) => {
    try {
      await updateConfig({ trading_mode: newMode });
      toast.success(`Trading mode changed to ${newMode}`);
      fetchConfig();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to change mode');
    }
  };

  const riskFields = [
    { key: 'max_daily_loss', label: 'Max Daily Loss ($)', type: 'number' },
    { key: 'max_loss_per_strategy', label: 'Max Loss Per Strategy ($)', type: 'number' },
    { key: 'max_position_size', label: 'Max Position Size', type: 'number' },
    { key: 'max_market_exposure', label: 'Max Market Exposure ($)', type: 'number' },
    { key: 'max_concurrent_positions', label: 'Max Concurrent Positions', type: 'number' },
    { key: 'max_order_size', label: 'Max Order Size', type: 'number' },
  ];

  const creds = config.credentials_present || {};

  return (
    <div data-testid="settings-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-zinc-100">Settings</h1>
          {config.persisted && (
            <Badge variant="outline" className="text-[10px] border-zinc-700 text-zinc-500 font-mono">
              Saved {config.last_saved ? new Date(config.last_saved).toLocaleTimeString() : ''}
            </Badge>
          )}
        </div>
        <Button
          data-testid="refresh-config-btn"
          size="sm"
          variant="outline"
          onClick={fetchConfig}
          className="h-7 text-xs px-3 border-zinc-700"
        >
          <RefreshCw size={12} className="mr-1" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Trading Mode */}
        <SectionCard title="Trading Mode" testId="section-trading-mode">
          <div className="space-y-3">
            <p className="text-xs text-zinc-500">Current mode: <span className="text-zinc-300 uppercase font-medium">{mode}</span></p>
            <div className="flex gap-2">
              {['paper', 'shadow', 'live'].map((m) => (
                <Button
                  key={m}
                  data-testid={`mode-${m}-btn`}
                  size="sm"
                  variant={mode === m ? 'default' : 'outline'}
                  onClick={() => handleModeChange(m)}
                  disabled={mode === m}
                  className={`text-xs h-8 px-4 ${mode === m ? '' : 'border-zinc-700 text-zinc-400'}`}
                >
                  {m.toUpperCase()}
                </Button>
              ))}
            </div>
            {mode !== 'paper' && !creds.polymarket && (
              <p className="text-xs text-amber-400">Polymarket credentials required for {mode} mode</p>
            )}
          </div>
        </SectionCard>

        {/* Credentials Status */}
        <SectionCard title="Credentials" testId="section-credentials">
          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-zinc-500">Polymarket API</span>
              <Badge variant={creds.polymarket ? 'default' : 'secondary'} className="text-xs">
                {creds.polymarket ? 'Connected' : 'Not Set'}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-zinc-500">Telegram Bot</span>
              <Badge variant={creds.telegram ? 'default' : 'secondary'} className="text-xs">
                {creds.telegram ? 'Connected' : 'Not Set'}
              </Badge>
            </div>
            <p className="text-zinc-600 pt-1">Configure credentials via backend .env file</p>
          </div>
        </SectionCard>

        {/* Risk Settings */}
        <SectionCard
          title="Risk Configuration"
          testId="section-risk-settings"
          action={
            <Button
              data-testid="save-risk-btn"
              size="sm"
              disabled={!dirty}
              onClick={handleSaveRisk}
              className="h-7 text-xs px-3"
            >
              <Save size={12} className="mr-1" /> Save
            </Button>
          }
        >
          <div className="space-y-3">
            {riskFields.map(({ key, label, type }) => (
              <div key={key} className="flex items-center justify-between gap-4">
                <Label className="text-xs text-zinc-500 shrink-0">{label}</Label>
                <Input
                  data-testid={`risk-${key}-input`}
                  type={type}
                  value={riskForm[key] ?? ''}
                  onChange={(e) => handleRiskChange(key, e.target.value)}
                  className="w-32 h-8 text-xs bg-zinc-900 border-zinc-800 text-right font-mono"
                />
              </div>
            ))}
          </div>
        </SectionCard>

        {/* Strategy Config */}
        <SectionCard title="Strategy Configuration" testId="section-strategy-config">
          <StrategyConfigSection config={config} fetchConfig={fetchConfig} />
        </SectionCard>

        {/* Telegram Alerts */}
        <SectionCard title="Telegram Alerts" testId="section-telegram-alerts">
          <TelegramSection config={config} updateConfig={updateConfig} fetchConfig={fetchConfig} />
        </SectionCard>
      </div>
    </div>
  );
}

function TelegramSection({ config, updateConfig, fetchConfig }) {
  const tg = config.telegram || {};
  const [sending, setSending] = useState(false);

  const handleToggle = async (key, value) => {
    try {
      await updateConfig({ [key]: value });
      toast.success(`${key.replace(/_/g, ' ')} ${value ? 'enabled' : 'disabled'}`);
      fetchConfig();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to update');
    }
  };

  const handleTestAlert = async () => {
    setSending(true);
    try {
      const { data } = await axios.get(`${API_BASE}/alerts/test`);
      if (data.status === 'sent') {
        toast.success('Test alert sent to Telegram');
      } else if (data.status === 'skipped') {
        toast.info(data.reason);
      } else {
        toast.error('Failed to send test alert');
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to send test alert');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center justify-between">
        <span className="text-zinc-500">Bot Configured</span>
        <Badge variant={tg.configured ? 'default' : 'secondary'} className="text-xs">
          {tg.configured ? 'Yes' : 'No'}
        </Badge>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-zinc-500">Trade Alerts</span>
        <Button
          data-testid="toggle-telegram-btn"
          size="sm"
          variant={tg.enabled ? 'default' : 'outline'}
          onClick={() => handleToggle('telegram_enabled', !tg.enabled)}
          className={`h-7 text-xs px-3 ${tg.enabled ? '' : 'border-zinc-700 text-zinc-400'}`}
        >
          {tg.enabled ? 'ON' : 'OFF'}
        </Button>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-zinc-500">Signal Alerts</span>
        <Button
          data-testid="toggle-signals-btn"
          size="sm"
          variant={tg.signals_enabled ? 'default' : 'outline'}
          onClick={() => handleToggle('telegram_signals_enabled', !tg.signals_enabled)}
          className={`h-7 text-xs px-3 ${tg.signals_enabled ? '' : 'border-zinc-700 text-zinc-400'}`}
        >
          {tg.signals_enabled ? 'ON' : 'OFF'}
        </Button>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-zinc-500">Messages Sent</span>
        <span className="text-zinc-400 font-mono">{tg.total_sent || 0}</span>
      </div>
      <div className="pt-2 border-t border-zinc-800">
        <Button
          data-testid="test-alert-btn"
          size="sm"
          variant="outline"
          onClick={handleTestAlert}
          disabled={sending || !tg.configured}
          className="h-7 text-xs px-3 border-zinc-700 w-full"
        >
          <Send size={12} className="mr-1" /> {sending ? 'Sending...' : 'Send Test Alert'}
        </Button>
        {!tg.configured && (
          <p className="text-zinc-600 mt-2">Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in backend .env</p>
        )}
      </div>
    </div>
  );
}


function StrategyConfigSection({ config, fetchConfig }) {
  const strategyConfigs = config.strategy_configs || {};
  const [editing, setEditing] = useState(null); // { stratId, key, value }
  const [saving, setSaving] = useState(false);

  const LABELS = {
    min_net_edge_bps: 'Min Net Edge (bps)',
    max_position_size: 'Max Position Size',
    max_concurrent_arbs: 'Max Concurrent Arbs',
    scan_interval_seconds: 'Scan Interval (s)',
    cooldown_seconds: 'Cooldown (s)',
    min_edge_bps: 'Min Edge (bps)',
    min_confidence: 'Min Confidence',
    max_concurrent_signals: 'Max Concurrent Signals',
    signal_cooldown_seconds: 'Signal Cooldown (s)',
  };

  const handleSave = async (stratId, key, rawValue) => {
    setSaving(true);
    try {
      const value = isNaN(Number(rawValue)) ? rawValue : Number(rawValue);
      await axios.post(`${API_BASE}/config/update`, {
        strategies: { [stratId]: { [key]: value } },
      });
      toast.success(`${LABELS[key] || key} updated`);
      setEditing(null);
      fetchConfig();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

  if (!Object.keys(strategyConfigs).length) {
    return <p className="text-xs text-zinc-600">No strategy configs available</p>;
  }

  const STRAT_NAMES = { arb_scanner: 'Arb Scanner', crypto_sniper: 'Crypto Sniper' };

  return (
    <div className="space-y-4">
      {Object.entries(strategyConfigs).map(([stratId, params]) => (
        <div key={stratId} className="space-y-2">
          <span className="text-sm text-zinc-300 font-medium">{STRAT_NAMES[stratId] || stratId}</span>
          <div className="bg-zinc-950 rounded p-3 space-y-1.5">
            {Object.entries(params).map(([k, v]) => {
              const isEditing = editing?.stratId === stratId && editing?.key === k;
              const isNumeric = typeof v === 'number';
              return (
                <div key={k} className="flex items-center justify-between text-xs min-h-[28px]">
                  <span className="text-zinc-500">{LABELS[k] || k.replace(/_/g, ' ')}</span>
                  {isEditing ? (
                    <div className="flex items-center gap-1">
                      <Input
                        data-testid={`edit-${stratId}-${k}`}
                        type="number"
                        step="any"
                        defaultValue={editing.value}
                        className="h-6 w-24 text-xs bg-zinc-900 border-zinc-700 px-2"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSave(stratId, k, e.target.value);
                          if (e.key === 'Escape') setEditing(null);
                        }}
                      />
                      <Button
                        size="sm"
                        className="h-6 text-xs px-2"
                        disabled={saving}
                        onClick={(e) => {
                          const input = e.target.closest('div').querySelector('input');
                          handleSave(stratId, k, input?.value ?? editing.value);
                        }}
                      >
                        <Save size={10} />
                      </Button>
                    </div>
                  ) : (
                    <span
                      data-testid={`param-${stratId}-${k}`}
                      className={`font-mono ${isNumeric ? 'text-zinc-400 cursor-pointer hover:text-zinc-200' : 'text-zinc-500'}`}
                      onClick={() => isNumeric && setEditing({ stratId, key: k, value: v })}
                      title={isNumeric ? 'Click to edit' : ''}
                    >
                      {typeof v === 'number' ? v : String(v)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
