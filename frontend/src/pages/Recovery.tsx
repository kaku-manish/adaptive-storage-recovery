import { useState, useEffect } from 'react';
import { Clock, Play, Square, Sliders, ShieldCheck, Database, Zap } from 'lucide-react';

export default function Recovery() {
  const [status, setStatus] = useState<any>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [configuredRate, setConfiguredRate] = useState<number>(25);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    try {
      const sRes = await fetch('/api/recovery/status');
      if (sRes.ok) {
        const sData = await sRes.json();
        setStatus(sData);
        if (sData.configured_rate_mbps) {
          setConfiguredRate(sData.configured_rate_mbps);
        }
      }

      const jRes = await fetch('/api/recovery/jobs');
      if (jRes.ok) {
        setJobs(await jRes.json());
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 1500);
    return () => clearInterval(interval);
  }, []);

  const handleStart = async () => {
    setLoading(true);
    try {
      await fetch('/api/recovery/start', { method: 'POST' });
      await fetchData();
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await fetch('/api/recovery/stop', { method: 'POST' });
      await fetchData();
    } finally {
      setLoading(false);
    }
  };

  const handleRateChange = async (newRate: number) => {
    setConfiguredRate(newRate);
    try {
      await fetch('/api/recovery/rate', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rate_mbps: newRate })
      });
      await fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const formatBytes = (bytes: number | null) => {
    if (bytes === null || bytes === undefined || bytes === 0) return '--';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const isRunning = status?.running;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-3xl font-semibold text-slate-100">Recovery Infrastructure</h2>
          <p className="text-slate-400 text-sm mt-1">Chunk-level replica reconstruction with Token Bucket rate limiting</p>
        </div>

        <div className="flex items-center gap-3">
          {isRunning ? (
            <button
              onClick={handleStop}
              disabled={loading}
              className="flex items-center gap-2 bg-rose-600 hover:bg-rose-500 text-white font-medium px-4 py-2 rounded-lg transition-colors shadow-sm disabled:opacity-50 text-sm"
            >
              <Square className="w-4 h-4 fill-white" />
              STOP RECOVERY
            </button>
          ) : (
            <button
              onClick={handleStart}
              disabled={loading}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-4 py-2 rounded-lg transition-colors shadow-sm disabled:opacity-50 text-sm"
            >
              <Play className="w-4 h-4 fill-white" />
              START RECOVERY
            </button>
          )}
        </div>
      </div>

      {/* Main Status Panel */}
      <div className="bg-slate-800 p-8 rounded-xl border border-slate-700 shadow-sm relative overflow-hidden">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
          <div>
            <h3 className="text-xl font-medium text-slate-100 flex items-center gap-2">
              <Database className="w-5 h-5 text-indigo-400" />
              Active Reconstruction Engine
            </h3>
            <span className="text-xs text-slate-500 block mt-1">
              Mode: <span className="font-semibold text-slate-300">{isRunning ? (status.mode ?? 'ADAPTIVE') : 'NOT RUNNING'}</span>
            </span>
          </div>

          <div className="flex items-center gap-4">
            <span className={`px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${
              isRunning ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-slate-700 text-slate-400'
            }`}>
              {isRunning ? status.status : 'IDLE'}
            </span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="mb-2 flex justify-between text-sm">
          <span className="text-slate-400 font-medium">
            {isRunning ? `Rebuilding ${status.remaining_blocks} missing block replicas` : 'No active reconstruction'}
          </span>
          <span className={`font-bold ${isRunning ? 'text-emerald-400' : 'text-slate-500'}`}>
            {isRunning && status.progress_percent !== null ? `${status.progress_percent}%` : '--'}
          </span>
        </div>
        <div className="w-full bg-slate-900 rounded-full h-3 mb-8 overflow-hidden border border-slate-700">
          <div
            className="bg-gradient-to-r from-emerald-600 to-emerald-400 h-full rounded-full transition-all duration-500"
            style={{ width: `${isRunning ? (status.progress_percent || 0) : 0}%` }}
          ></div>
        </div>

        {/* Metric Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div className="bg-slate-900/60 p-4 rounded-xl border border-slate-700/50">
            <span className="block text-slate-500 text-xs uppercase tracking-wider mb-1 font-medium">Recovered Data</span>
            <span className="text-2xl font-bold text-slate-200">
              {isRunning ? formatBytes(status.completed_bytes) : '--'}
            </span>
            <span className="text-xs text-slate-500 block mt-1">
              {isRunning ? `${status.completed_blocks} blocks` : '--'}
            </span>
          </div>

          <div className="bg-slate-900/60 p-4 rounded-xl border border-slate-700/50">
            <span className="block text-slate-500 text-xs uppercase tracking-wider mb-1 font-medium">Remaining Data</span>
            <span className="text-2xl font-bold text-slate-200">
              {isRunning ? formatBytes(status.remaining_bytes) : '--'}
            </span>
            <span className="text-xs text-slate-500 block mt-1">
              {isRunning ? `${status.remaining_blocks} blocks` : '--'}
            </span>
          </div>

          <div className="bg-slate-900/60 p-4 rounded-xl border border-slate-700/50">
            <span className="block text-slate-500 text-xs uppercase tracking-wider mb-1 font-medium flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-indigo-400" /> Transfer Rate
            </span>
            <span className="text-2xl font-bold text-indigo-400">
              {isRunning && status.actual_rate_mbps !== null ? `${status.actual_rate_mbps} MB/s` : '--'}
            </span>
            <span className="text-xs text-slate-500 block mt-1">
              Limit: {isRunning && status.configured_rate_mbps !== null ? `${status.configured_rate_mbps} MB/s` : '--'}
            </span>
          </div>

          <div className="bg-slate-900/60 p-4 rounded-xl border border-slate-700/50">
            <span className="block text-slate-500 text-xs uppercase tracking-wider mb-1 font-medium flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-amber-400" /> Estimated Time
            </span>
            <span className="text-2xl font-bold text-amber-400">
              {isRunning && status.eta_seconds !== null ? `${status.eta_seconds}s` : '--'}
            </span>
            <span className="text-xs text-slate-500 block mt-1">
              Elapsed: {isRunning && status.elapsed_seconds !== null ? `${status.elapsed_seconds}s` : '--'}
            </span>
          </div>
        </div>

        {/* Rate Limiter Control Slider */}
        <div className="mt-8 pt-6 border-t border-slate-700/60 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Sliders className="w-5 h-5 text-indigo-400" />
            <div>
              <span className="text-sm font-medium text-slate-200">Dynamic Rate Limit (Token Bucket)</span>
              <span className="text-xs text-slate-500 block">Modifies transfer speed in real-time without restarting recovery</span>
            </div>
          </div>

          <div className="flex items-center gap-4 w-full sm:w-auto">
            <input
              type="range"
              min="5"
              max="100"
              step="5"
              value={configuredRate}
              onChange={(e) => handleRateChange(Number(e.target.value))}
              className="w-48 accent-indigo-500 cursor-pointer"
            />
            <span className="font-mono text-sm font-bold text-indigo-400 min-w-16">
              {configuredRate} MB/s
            </span>
          </div>
        </div>
      </div>

      {/* Recovery Jobs Table */}
      <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
        <h3 className="text-lg font-medium text-slate-200 mb-4 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-emerald-400" />
          Replication & Recovery Jobs
        </h3>
        
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 text-xs uppercase tracking-wider">
                <th className="pb-3 px-4">Job ID</th>
                <th className="pb-3 px-4">Block ID</th>
                <th className="pb-3 px-4">Source</th>
                <th className="pb-3 px-4">Destination</th>
                <th className="pb-3 px-4">Bytes</th>
                <th className="pb-3 px-4">Status</th>
                <th className="pb-3 px-4">SHA-256</th>
              </tr>
            </thead>
            <tbody className="text-slate-300 divide-y divide-slate-700/40">
              {jobs.map((job, idx) => (
                <tr key={idx} className="hover:bg-slate-700/20">
                  <td className="py-3 px-4 font-mono text-xs text-slate-500">{job.job_id}</td>
                  <td className="py-3 px-4 font-mono text-xs text-indigo-300">{job.block_id}</td>
                  <td className="py-3 px-4 text-xs font-mono text-slate-400">{job.source_node}</td>
                  <td className="py-3 px-4 text-xs font-mono text-slate-200">{job.destination_node}</td>
                  <td className="py-3 px-4 font-mono text-xs">{formatBytes(job.total_bytes)}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                      job.status === 'COMPLETED' ? 'bg-emerald-500/20 text-emerald-400' :
                      job.status === 'RUNNING' ? 'bg-amber-500/20 text-amber-400 animate-pulse' :
                      'bg-rose-500/20 text-rose-400'
                    }`}>
                      {job.status}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <span className="text-xs text-emerald-400 font-mono">
                      {job.checksum_verified ? 'VERIFIED' : '--'}
                    </span>
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500">
                    No active or recorded recovery jobs.
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
