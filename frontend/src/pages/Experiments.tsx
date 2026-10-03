import { useState, useEffect } from 'react';
import { Play, Download, RefreshCw, Clock, CheckCircle2, AlertTriangle, Layers, Activity } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer } from 'recharts';

interface ComparisonRow {
  strategy: string;
  workload: string;
  sample_count: number;
  mean_throughput_drop: number | null;
  min_throughput_drop: number | null;
  max_throughput_drop: number | null;
  mean_avg_p99: number | null;
  mean_peak_p99: number | null;
  max_peak_p99: number | null;
  mean_recovery_time: number | null;
  min_recovery_time: number | null;
  max_recovery_time: number | null;
  mean_recovery_rate: number | null;
  mean_risk_window?: number | null;
  mean_estimated_risk?: number | null;
}

interface ExperimentHistoryRow {
  id: number;
  mode: string;
  workload: string;
  start_time: number;
  baseline_throughput: number | null;
  min_client_throughput: number | null;
  avg_client_throughput: number | null;
  throughput_drop_percent: number | null;
  baseline_p99: number | null;
  avg_recovery_p99: number | null;
  peak_recovery_p99: number | null;
  total_recovery_time: number | null;
  avg_recovery_mbps: number | null;
  peak_disk_utilization: number | null;
  peak_network_utilization: number | null;
  status: string;
  completed_at: number | null;
}

interface ExperimentStatus {
  status: string;
  experiment_id: number | null;
  strategy: string | null;
  workload: string | null;
  phase: string;
  phase_number: number;
  phase_name: string;
  elapsed: number;
  progress: number;
}

export default function Experiments() {
  const [comparisons, setComparisons] = useState<ComparisonRow[]>([]);
  const [history, setHistory] = useState<ExperimentHistoryRow[]>([]);
  const [status, setStatus] = useState<ExperimentStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Form Controls
  const [strategy, setStrategy] = useState<string>('ADAPTIVE');
  const [workload, setWorkload] = useState<string>('MEDIUM');
  const [nodeToFail, setNodeToFail] = useState<string>('storage2');
  const [datasetSizeMb, setDatasetSizeMb] = useState<number>(256);

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/experiments/status');
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (e) {
      console.error('Failed to fetch experiment status:', e);
    }
  };

  const fetchComparisons = async () => {
    try {
      const res = await fetch('/api/experiments/comparison');
      if (res.ok) {
        const data = await res.json();
        setComparisons(Array.isArray(data) ? data : []);
      }
    } catch (e) {
      console.error('Failed to fetch comparisons:', e);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch('/api/experiments/history');
      if (res.ok) {
        const data = await res.json();
        setHistory(Array.isArray(data) ? data : []);
      }
    } catch (e) {
      console.error('Failed to fetch experiment history:', e);
    }
  };

  const refreshAll = () => {
    fetchStatus();
    fetchComparisons();
    fetchHistory();
  };

  useEffect(() => {
    refreshAll();
    const interval = setInterval(() => {
      fetchStatus();
      if (status?.status === 'RUNNING') {
        fetchHistory();
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [status?.status]);

  const runExperiment = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await fetch('/api/experiments/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy,
          workload,
          dataset_size_mb: datasetSizeMb,
          node_to_fail: nodeToFail,
          recovery_rate_mbps: strategy === 'FIXED_50' ? 50.0 : 25.0
        })
      });

      if (!res.ok) {
        const err = await res.json();
        setErrorMessage(err.detail || 'Failed to start experiment');
      } else {
        await fetchStatus();
      }
    } catch (e: any) {
      setErrorMessage(e.message || 'Connection error starting experiment');
    } finally {
      setLoading(false);
    }
  };

  const isRunning = status?.status === 'RUNNING';

  return (
    <div className="space-y-8 pb-12">
      {/* Page Title & Actions */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-3xl font-bold text-slate-100 tracking-tight">Experiment Engine</h2>
          <p className="text-slate-400 text-sm mt-1">
            Conduct multi-phase fault injection benchmarks to compare recovery strategies against client SLOs.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="/api/experiments/export/csv"
            download="experiments_summary.csv"
            className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Download className="w-4 h-4 text-slate-400" />
            Export Summary (CSV)
          </a>
          <button
            onClick={refreshAll}
            className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
            title="Refresh All Data"
          >
            <RefreshCw className="w-4 h-4 text-slate-400" />
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="bg-rose-950/40 border border-rose-600/50 p-4 rounded-xl flex items-center gap-3 text-rose-300 text-sm">
          <AlertTriangle className="w-5 h-5 flex-shrink-0 text-rose-400" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Control Panel */}
      <div className="bg-slate-800/90 p-6 rounded-xl border border-slate-700 shadow-sm backdrop-blur">
        <h3 className="text-base font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <Layers className="w-4 h-4 text-indigo-400" />
          Benchmark Configuration
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
              Recovery Strategy
            </label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              disabled={isRunning}
              className="w-full bg-slate-900 border border-slate-600 text-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 disabled:opacity-50"
            >
              <option value="ADAPTIVE">ADAPTIVE (Dynamic Closed-Loop)</option>
              <option value="UNTHROTTLED">UNTHROTTLED (Aggressive 100 MB/s)</option>
              <option value="FIXED_25">FIXED_25 (Static 25 MB/s)</option>
              <option value="FIXED_50">FIXED_50 (Static 50 MB/s)</option>
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
              Client Workload
            </label>
            <select
              value={workload}
              onChange={(e) => setWorkload(e.target.value)}
              disabled={isRunning}
              className="w-full bg-slate-900 border border-slate-600 text-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 disabled:opacity-50"
            >
              <option value="LOW">LOW (10 RPS, 70/30 R/W)</option>
              <option value="MEDIUM">MEDIUM (30 RPS, 70/30 R/W)</option>
              <option value="HIGH">HIGH (60 RPS, 70/30 R/W)</option>
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
              Fault Injection Node
            </label>
            <select
              value={nodeToFail}
              onChange={(e) => setNodeToFail(e.target.value)}
              disabled={isRunning}
              className="w-full bg-slate-900 border border-slate-600 text-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 disabled:opacity-50"
            >
              <option value="storage1">storage1 (127.0.0.1:8001)</option>
              <option value="storage2">storage2 (127.0.0.1:8002)</option>
              <option value="storage3">storage3 (127.0.0.1:8004)</option>
              <option value="storage4">storage4 (127.0.0.1:8005)</option>
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
              Dataset Size
            </label>
            <select
              value={datasetSizeMb}
              onChange={(e) => setDatasetSizeMb(Number(e.target.value))}
              disabled={isRunning}
              className="w-full bg-slate-900 border border-slate-600 text-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 disabled:opacity-50"
            >
              <option value={128}>128 MB (32 blocks × 4MB)</option>
              <option value={256}>256 MB (64 blocks × 4MB)</option>
              <option value={512}>512 MB (128 blocks × 4MB)</option>
            </select>
          </div>
        </div>

        <div className="mt-5 flex justify-end">
          <button
            onClick={runExperiment}
            disabled={isRunning || loading}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2.5 rounded-lg font-medium transition-colors disabled:opacity-50 shadow-sm"
          >
            <Play className="w-4 h-4 fill-white" />
            {isRunning ? 'Benchmark In Progress...' : 'Start Benchmark'}
          </button>
        </div>
      </div>

      {/* Live Pipeline Status Banner */}
      {isRunning && status && (
        <div className="bg-indigo-950/40 border border-indigo-500/50 p-6 rounded-xl shadow-lg relative overflow-hidden backdrop-blur">
          <div className="absolute top-0 left-0 h-1 bg-indigo-500 animate-pulse w-full"></div>
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <span className="flex h-3 w-3 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-indigo-500"></span>
                </span>
                <span className="text-xs uppercase tracking-wider font-bold text-indigo-400">
                  Live Benchmark Pipeline Active
                </span>
                <span className="bg-indigo-900/60 border border-indigo-700/50 text-indigo-200 text-xs px-2.5 py-0.5 rounded-full font-mono">
                  {status.strategy} • {status.workload}
                </span>
              </div>
              <h4 className="text-xl font-bold text-slate-100 mt-2">
                Phase {status.phase_number}/10: {status.phase_name}
              </h4>
            </div>

            <div className="flex items-center gap-6 text-sm">
              <div className="text-right">
                <span className="text-slate-400 block text-xs">Elapsed Time</span>
                <span className="text-lg font-mono font-bold text-slate-200 flex items-center gap-1">
                  <Clock className="w-4 h-4 text-slate-400" />
                  {status.elapsed}s
                </span>
              </div>
              <div className="text-right">
                <span className="text-slate-400 block text-xs">Recovery Progress</span>
                <span className="text-lg font-mono font-bold text-emerald-400">
                  {status.progress.toFixed(1)}%
                </span>
              </div>
            </div>
          </div>

          <div className="mt-4 w-full bg-slate-900 rounded-full h-2.5 overflow-hidden border border-slate-700">
            <div
              className="bg-indigo-500 h-2.5 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${Math.max(5, (status.phase_number / 10) * 100)}%` }}
            ></div>
          </div>
        </div>
      )}

      {/* Comparison Engine Summary Table */}
      <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h3 className="text-lg font-semibold text-slate-200 flex items-center gap-2">
              <Activity className="w-5 h-5 text-indigo-400" />
              Aggregated Strategy Comparison
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Strictly computed from completed benchmark runs. Zero mock or interpolated values.
            </p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 text-xs uppercase tracking-wider">
                <th className="pb-3 px-4 font-semibold">Strategy</th>
                <th className="pb-3 px-4 font-semibold">Workload</th>
                <th className="pb-3 px-4 font-semibold">Runs</th>
                <th className="pb-3 px-4 font-semibold">Mean Tput Drop %</th>
                <th className="pb-3 px-4 font-semibold">Mean p99 (ms)</th>
                <th className="pb-3 px-4 font-semibold">Peak p99 (ms)</th>
                <th className="pb-3 px-4 font-semibold">Mean Recovery (s)</th>
                <th className="pb-3 px-4 font-semibold">Risk Window (s)</th>
                <th className="pb-3 px-4 font-semibold">Est. 2nd Fail Prob</th>
              </tr>
            </thead>
            <tbody className="text-slate-300 divide-y divide-slate-700/50">
              {comparisons.map((row, i) => (
                <tr key={i} className="hover:bg-slate-700/20 transition-colors">
                  <td className="py-3 px-4 font-semibold text-indigo-400">
                    {row.strategy}
                  </td>
                  <td className="py-3 px-4">
                    <span className="bg-slate-900 px-2 py-0.5 rounded text-xs text-slate-300 border border-slate-700">
                      {row.workload}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-mono">{row.sample_count}</td>
                  <td className="py-3 px-4 font-mono font-medium">
                    {row.mean_throughput_drop != null ? (
                      <span className={row.mean_throughput_drop > 20 ? 'text-amber-400' : 'text-emerald-400'}>
                        {row.mean_throughput_drop.toFixed(1)}%
                      </span>
                    ) : '--'}
                  </td>
                  <td className="py-3 px-4 font-mono">
                    {row.mean_avg_p99 != null ? `${row.mean_avg_p99.toFixed(1)} ms` : '--'}
                  </td>
                  <td className="py-3 px-4 font-mono text-rose-300">
                    {row.mean_peak_p99 != null ? `${row.mean_peak_p99.toFixed(1)} ms` : '--'}
                  </td>
                  <td className="py-3 px-4 font-mono">
                    {row.mean_recovery_time != null ? `${row.mean_recovery_time.toFixed(1)}s` : '--'}
                  </td>
                  <td className="py-3 px-4 font-mono text-amber-300">
                    {row.mean_risk_window != null
                      ? `${row.mean_risk_window.toFixed(1)}s`
                      : row.mean_recovery_time != null
                      ? `${row.mean_recovery_time.toFixed(1)}s`
                      : '--'}
                  </td>
                  <td className="py-3 px-4 font-mono text-xs text-slate-400">
                    {row.mean_estimated_risk != null
                      ? `${(row.mean_estimated_risk * 100).toExponential(4)}%`
                      : '--'}
                  </td>
                </tr>
              ))}
              {comparisons.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-500 font-medium">
                    No experimental data available. Run an experiment above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Visual Analytics Charts */}
      {comparisons.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
            <h3 className="text-base font-semibold text-slate-200 mb-4">
              Mean Client Throughput Degradation (%)
            </h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={comparisons}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="strategy" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <YAxis stroke="#94a3b8" unit="%" tick={{ fontSize: 11 }} />
                  <RechartsTooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px' }} />
                  <Legend />
                  <Bar dataKey="mean_throughput_drop" fill="#6366f1" name="Throughput Drop %" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
            <h3 className="text-base font-semibold text-slate-200 mb-4">
              Mean Degraded Recovery Duration (Seconds)
            </h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={comparisons}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="strategy" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <YAxis stroke="#94a3b8" unit="s" tick={{ fontSize: 11 }} />
                  <RechartsTooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px' }} />
                  <Legend />
                  <Bar dataKey="mean_recovery_time" fill="#f43f5e" name="Recovery Time (s)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Experiment Run History Table */}
      <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-200 mb-4">
          Individual Benchmark History
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 text-xs uppercase tracking-wider">
                <th className="pb-3 px-4 font-semibold">ID</th>
                <th className="pb-3 px-4 font-semibold">Strategy</th>
                <th className="pb-3 px-4 font-semibold">Workload</th>
                <th className="pb-3 px-4 font-semibold">Baseline Tput</th>
                <th className="pb-3 px-4 font-semibold">Recov Tput</th>
                <th className="pb-3 px-4 font-semibold">Tput Drop</th>
                <th className="pb-3 px-4 font-semibold">Peak p99</th>
                <th className="pb-3 px-4 font-semibold">Duration</th>
                <th className="pb-3 px-4 font-semibold">Status</th>
                <th className="pb-3 px-4 font-semibold">Samples Export</th>
              </tr>
            </thead>
            <tbody className="text-slate-300 divide-y divide-slate-700/50">
              {history.map((row) => (
                <tr key={row.id} className="hover:bg-slate-700/20 transition-colors">
                  <td className="py-3 px-4 font-mono font-semibold text-slate-400">#{row.id}</td>
                  <td className="py-3 px-4 font-medium text-indigo-400">{row.mode}</td>
                  <td className="py-3 px-4 text-xs font-mono">{row.workload}</td>
                  <td className="py-3 px-4 font-mono">
                    {row.baseline_throughput != null ? `${row.baseline_throughput.toFixed(2)} MB/s` : '--'}
                  </td>
                  <td className="py-3 px-4 font-mono">
                    {row.avg_client_throughput != null ? `${row.avg_client_throughput.toFixed(2)} MB/s` : '--'}
                  </td>
                  <td className="py-3 px-4 font-mono">
                    {row.throughput_drop_percent != null ? `${row.throughput_drop_percent.toFixed(1)}%` : '--'}
                  </td>
                  <td className="py-3 px-4 font-mono text-rose-300">
                    {row.peak_recovery_p99 != null ? `${row.peak_recovery_p99.toFixed(1)} ms` : '--'}
                  </td>
                  <td className="py-3 px-4 font-mono">
                    {row.total_recovery_time != null ? `${row.total_recovery_time.toFixed(1)}s` : '--'}
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold ${
                        row.status === 'COMPLETED'
                          ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800'
                          : row.status === 'RUNNING'
                          ? 'bg-indigo-950/60 text-indigo-400 border border-indigo-800 animate-pulse'
                          : 'bg-rose-950/60 text-rose-400 border border-rose-800'
                      }`}
                    >
                      {row.status === 'COMPLETED' && <CheckCircle2 className="w-3 h-3" />}
                      {row.status}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <a
                      href={`/api/experiments/${row.id}/samples.csv`}
                      download={`experiment_${row.id}_samples.csv`}
                      className="text-xs inline-flex items-center gap-1 text-indigo-400 hover:text-indigo-300 font-medium"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Samples CSV
                    </a>
                  </td>
                </tr>
              ))}
              {history.length === 0 && (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-500 font-medium">
                    No past experiments recorded.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
