import { useState, useEffect } from 'react';
import { ShieldAlert, ArrowRight, Clock, CheckCircle, RefreshCw, BarChart2 } from 'lucide-react';

interface RiskSummaryItem {
  strategy: string;
  recovery_time: number;
  risk_window: number;
  failure_prob: number;
  sample_count: number;
}

interface EventItem {
  id: number;
  event_type: string;
  node_id: string;
  details: string;
  created_at: string;
}

export default function RiskAnalysis() {
  const [riskData, setRiskData] = useState<RiskSummaryItem[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchRisk = async () => {
    try {
      const [riskRes, eventsRes] = await Promise.all([
        fetch('/api/risk/summary'),
        fetch('/api/events')
      ]);

      if (riskRes.ok) {
        const data = await riskRes.json();
        setRiskData(Array.isArray(data) ? data : []);
      }
      if (eventsRes.ok) {
        const evData = await eventsRes.json();
        setEvents(Array.isArray(evData) ? evData : []);
      }
    } catch (e) {
      console.error('Failed to fetch risk data:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRisk();
    const interval = setInterval(fetchRisk, 3000);
    return () => clearInterval(interval);
  }, []);

  const hasData = riskData.length > 0;

  // Derive timeline metrics from the latest or best available experiment
  const latestAdaptive = riskData.find((r) => r.strategy === 'ADAPTIVE');
  const primaryStrategy = latestAdaptive || riskData[0];
  const measuredWindow = primaryStrategy ? primaryStrategy.risk_window : null;

  return (
    <div className="space-y-8 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-3xl font-bold text-slate-100 tracking-tight">Durability-Risk Analysis</h2>
          <p className="text-slate-400 text-sm mt-1">
            Quantifying estimated additional-failure probability during the single-node degraded recovery window.
          </p>
        </div>
        <button
          onClick={fetchRisk}
          className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <RefreshCw className="w-4 h-4 text-slate-400" />
          Refresh
        </button>
      </div>

      {!hasData && !loading ? (
        <div className="bg-slate-800/80 border border-slate-700 p-12 rounded-xl text-center space-y-4">
          <div className="w-16 h-16 bg-slate-900 border border-slate-700 rounded-full flex items-center justify-center mx-auto text-slate-500">
            <ShieldAlert className="w-8 h-8 text-amber-500" />
          </div>
          <h3 className="text-xl font-semibold text-slate-200">
            No risk analysis available. Complete an experiment first.
          </h3>
          <p className="text-slate-400 text-sm max-w-md mx-auto">
            Risk calculations require empirical recovery duration measurements. Navigate to the{' '}
            <a href="/experiments" className="text-indigo-400 underline font-medium">
              Experiments page
            </a>{' '}
            to launch a benchmark run across any strategy.
          </p>
        </div>
      ) : (
        <>
          {/* Timeline of Degradation & Recovery */}
          <div className="bg-slate-800 p-8 rounded-xl border border-slate-700 shadow-sm overflow-hidden">
            <div className="flex justify-between items-center mb-8">
              <div>
                <h3 className="text-lg font-semibold text-slate-200">
                  Empirical Vulnerability Window Timeline
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Timeline mapped directly from measured experiment execution duration.
                </p>
              </div>
              {primaryStrategy && (
                <span className="bg-slate-900 border border-slate-700 text-indigo-300 text-xs px-3 py-1 rounded-full font-mono">
                  Strategy: {primaryStrategy.strategy}
                </span>
              )}
            </div>

            <div className="flex items-center justify-between relative py-6">
              <div className="absolute top-1/2 left-0 w-full h-1 bg-slate-700 -z-10 -translate-y-1/2"></div>

              {/* Step 1: Failure */}
              <div className="flex flex-col items-center bg-slate-800 px-4">
                <div className="w-12 h-12 rounded-full bg-rose-500/20 border-2 border-rose-500 flex items-center justify-center mb-4 shadow-[0_0_15px_rgba(244,63,94,0.3)]">
                  <ShieldAlert className="w-6 h-6 text-rose-400" />
                </div>
                <span className="text-slate-200 font-medium text-sm">Node Failure</span>
                <span className="text-slate-400 font-mono text-xs mt-0.5">T+0.0s</span>
              </div>

              {/* Step 2: Under-Replicated */}
              <div className="flex flex-col items-center bg-slate-800 px-4">
                <div className="w-12 h-12 rounded-full bg-amber-500/20 border-2 border-amber-500 flex items-center justify-center mb-4">
                  <ArrowRight className="w-6 h-6 text-amber-400" />
                </div>
                <span className="text-slate-200 font-medium text-sm">Heartbeat Timeout</span>
                <span className="text-slate-400 font-mono text-xs mt-0.5">T+3.0s</span>
              </div>

              {/* Step 3: Active Reconstruction */}
              <div className="flex flex-col items-center bg-slate-800 px-4">
                <div className="w-12 h-12 rounded-full bg-indigo-500/20 border-2 border-indigo-500 flex items-center justify-center mb-4">
                  <Clock className="w-6 h-6 text-indigo-400" />
                </div>
                <span className="text-slate-200 font-medium text-sm">Active Reconstruction</span>
                <span className="text-rose-400 font-bold text-xs mt-0.5">Degraded Risk Window</span>
              </div>

              {/* Step 4: Redundancy Restored */}
              <div className="flex flex-col items-center bg-slate-800 px-4">
                <div className="w-12 h-12 rounded-full bg-emerald-500/20 border-2 border-emerald-500 flex items-center justify-center mb-4 shadow-[0_0_15px_rgba(16,185,129,0.3)]">
                  <CheckCircle className="w-6 h-6 text-emerald-400" />
                </div>
                <span className="text-slate-200 font-medium text-sm">Full Redundancy</span>
                <span className="text-emerald-400 font-mono font-bold text-xs mt-0.5">
                  {measuredWindow != null ? `T+${measuredWindow.toFixed(1)}s` : '--'}
                </span>
              </div>
            </div>
          </div>

          {/* Mathematical Model Explanation */}
          <div className="bg-slate-800 p-8 rounded-xl border border-slate-700 shadow-sm space-y-4">
            <h3 className="text-lg font-semibold text-slate-200">
              Mathematical Durability Risk Formulation
            </h3>
            <p className="text-slate-300 text-sm leading-relaxed max-w-4xl">
              In a replicated storage cluster with replication factor 3, single-node failure degrades replica availability to 2.
              Catastrophic data loss occurs only if an independent second failure strikes an overlapping block replica before the recovery worker completes full re-replication.
              The estimated additional-failure probability during this vulnerability window is modeled as:
            </p>
            <div className="bg-slate-900 p-4 rounded-lg border border-slate-700 font-mono text-sm text-indigo-300 flex items-center gap-3">
              <span className="text-slate-400 font-bold">Model:</span>
              <span>P = 1 - e<sup>-λT</sup></span>
              <span className="text-slate-500 text-xs ml-auto">
                where λ ≈ 3.17 × 10⁻⁸ s⁻¹ (annualized hard failure rate) and T = empirical recovery window (s)
              </span>
            </div>
          </div>

          {/* Strategy Risk Comparison Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {riskData.map((item) => (
              <div
                key={item.strategy}
                className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm flex flex-col justify-between"
              >
                <div>
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">
                      {item.strategy}
                    </span>
                    <span className="bg-slate-900 border border-slate-700 text-slate-400 text-xs px-2 py-0.5 rounded font-mono">
                      {item.sample_count} {item.sample_count === 1 ? 'run' : 'runs'}
                    </span>
                  </div>

                  <div className="my-2">
                    <span className="text-xs text-slate-400 block mb-1">
                      Estimated 2nd Failure Probability
                    </span>
                    <span className="text-2xl font-bold font-mono text-indigo-300">
                      {(item.failure_prob * 100).toExponential(4)}%
                    </span>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-slate-700/60 flex justify-between items-center text-xs">
                  <span className="text-slate-400">Degraded Window:</span>
                  <span className="font-mono font-semibold text-slate-200">
                    {item.recovery_time ? `${item.recovery_time.toFixed(1)}s` : '--'}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Cluster Fault Event Log */}
          {events.length > 0 && (
            <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
              <h3 className="text-base font-semibold text-slate-200 mb-4 flex items-center gap-2">
                <BarChart2 className="w-4 h-4 text-indigo-400" />
                Cluster Fault & Recovery Audit Trail
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-700 text-slate-400 uppercase tracking-wider">
                      <th className="pb-2.5 px-4 font-semibold">Timestamp</th>
                      <th className="pb-2.5 px-4 font-semibold">Event Type</th>
                      <th className="pb-2.5 px-4 font-semibold">Target Node</th>
                      <th className="pb-2.5 px-4 font-semibold">Details</th>
                    </tr>
                  </thead>
                  <tbody className="text-slate-300 divide-y divide-slate-700/50">
                    {events.slice(0, 10).map((ev) => (
                      <tr key={ev.id} className="hover:bg-slate-700/20">
                        <td className="py-2.5 px-4 font-mono text-slate-400">
                          {ev.created_at ? new Date(ev.created_at).toLocaleTimeString() : '--'}
                        </td>
                        <td className="py-2.5 px-4">
                          <span
                            className={`px-2 py-0.5 rounded font-mono font-semibold ${
                              ev.event_type.includes('FAIL')
                                ? 'bg-rose-950/60 text-rose-400 border border-rose-800'
                                : ev.event_type.includes('RECOVER')
                                ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800'
                                : 'bg-slate-900 text-slate-300 border border-slate-700'
                            }`}
                          >
                            {ev.event_type}
                          </span>
                        </td>
                        <td className="py-2.5 px-4 font-mono text-slate-300">{ev.node_id}</td>
                        <td className="py-2.5 px-4 text-slate-400">{ev.details}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
