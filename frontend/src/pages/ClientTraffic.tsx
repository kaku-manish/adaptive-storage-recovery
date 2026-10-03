import { useState, useEffect } from 'react';
import { Play, Square, Gauge, Activity, Zap, AlertCircle } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function ClientTraffic() {
  const [status, setStatus] = useState<any>(null);
  const [selectedProfile, setSelectedProfile] = useState<string>('LOW');
  const [loading, setLoading] = useState<boolean>(false);

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/workload/status');
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
        if (data.profile) {
          setSelectedProfile(data.profile);
        }
      }
    } catch (e) {
      console.error("Failed to fetch workload status", e);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 1500);
    return () => clearInterval(interval);
  }, []);

  const handleStart = async (profileToStart: string) => {
    setLoading(true);
    try {
      await fetch('/api/workload/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: profileToStart })
      });
      await fetchStatus();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await fetch('/api/workload/stop', { method: 'POST' });
      await fetchStatus();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleProfileChange = async (newProfile: string) => {
    setSelectedProfile(newProfile);
    if (status?.running) {
      try {
        await fetch('/api/workload/profile', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ profile: newProfile })
        });
        await fetchStatus();
      } catch (e) {
        console.error(e);
      }
    }
  };

  const isRunning = status?.running;
  const history = status?.history || [];

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-3xl font-semibold text-slate-100">Client Traffic Generator</h2>
          <p className="text-slate-400 text-sm mt-1">Real-time HTTP 70/30 read/write workload targeting coordinator</p>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="bg-slate-800 p-1 rounded-lg border border-slate-700 flex gap-1">
            {(['LOW', 'MEDIUM', 'HIGH'] as const).map(p => (
              <button
                key={p}
                onClick={() => handleProfileChange(p)}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold tracking-wide transition-all ${
                  selectedProfile === p
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {p}
              </button>
            ))}
          </div>

          {isRunning ? (
            <button
              onClick={handleStop}
              disabled={loading}
              className="flex items-center gap-2 bg-rose-600 hover:bg-rose-500 text-white font-medium px-4 py-2 rounded-lg transition-colors shadow-sm disabled:opacity-50 text-sm"
            >
              <Square className="w-4 h-4 fill-white" />
              STOP WORKLOAD
            </button>
          ) : (
            <button
              onClick={() => handleStart(selectedProfile)}
              disabled={loading}
              className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-4 py-2 rounded-lg transition-colors shadow-sm disabled:opacity-50 text-sm"
            >
              <Play className="w-4 h-4 fill-white" />
              START WORKLOAD
            </button>
          )}
        </div>
      </div>

      {/* Live Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700 shadow-sm">
          <div className="flex justify-between items-start">
            <span className="text-xs uppercase font-medium tracking-wider text-slate-400">RPS</span>
            <Activity className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-slate-100">
              {isRunning ? status.rps : '--'}
            </span>
            <span className="text-xs text-slate-500 block mt-0.5">req / sec</span>
          </div>
        </div>

        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700 shadow-sm">
          <div className="flex justify-between items-start">
            <span className="text-xs uppercase font-medium tracking-wider text-slate-400">Throughput</span>
            <Zap className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-slate-100">
              {isRunning ? `${status.throughput_mbps} MB/s` : '--'}
            </span>
            <span className="text-xs text-slate-500 block mt-0.5">bandwidth</span>
          </div>
        </div>

        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700 shadow-sm">
          <div className="flex justify-between items-start">
            <span className="text-xs uppercase font-medium tracking-wider text-slate-400">p50 Latency</span>
            <Gauge className="w-4 h-4 text-slate-400" />
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-slate-100">
              {isRunning ? `${status.p50_ms} ms` : '--'}
            </span>
            <span className="text-xs text-slate-500 block mt-0.5">median response</span>
          </div>
        </div>

        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700 shadow-sm">
          <div className="flex justify-between items-start">
            <span className="text-xs uppercase font-medium tracking-wider text-slate-400">p95 Latency</span>
            <Gauge className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-slate-100">
              {isRunning ? `${status.p95_ms} ms` : '--'}
            </span>
            <span className="text-xs text-slate-500 block mt-0.5">95th percentile</span>
          </div>
        </div>

        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700 shadow-sm">
          <div className="flex justify-between items-start">
            <span className="text-xs uppercase font-medium tracking-wider text-slate-400">p99 Latency</span>
            <Gauge className="w-4 h-4 text-rose-400" />
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-rose-400">
              {isRunning ? `${status.p99_ms} ms` : '--'}
            </span>
            <span className="text-xs text-slate-500 block mt-0.5">tail latency</span>
          </div>
        </div>

        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700 shadow-sm">
          <div className="flex justify-between items-start">
            <span className="text-xs uppercase font-medium tracking-wider text-slate-400">Error Rate</span>
            <AlertCircle className="w-4 h-4 text-slate-400" />
          </div>
          <div className="mt-3">
            <span className={`text-2xl font-bold ${status?.errors_per_second > 0 ? 'text-rose-400' : 'text-slate-100'}`}>
              {isRunning ? status.errors_per_second : '--'}
            </span>
            <span className="text-xs text-slate-500 block mt-0.5">err / sec</span>
          </div>
        </div>
      </div>

      {/* Live Charts */}
      {history.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
            <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-4">Requests / Second</h3>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="time" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }} />
                  <Line type="monotone" dataKey="rps" stroke="#818cf8" strokeWidth={2} dot={false} isAnimationActive={false} name="RPS" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
            <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-4">p99 Latency (ms)</h3>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="time" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }} />
                  <Line type="monotone" dataKey="p99_ms" stroke="#f43f5e" strokeWidth={2} dot={false} isAnimationActive={false} name="p99 (ms)" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
            <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-4">Throughput (MB/s)</h3>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="time" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }} />
                  <Line type="monotone" dataKey="throughput_mbps" stroke="#34d399" strokeWidth={2} dot={false} isAnimationActive={false} name="MB/s" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-slate-800 p-12 rounded-xl border border-slate-700 text-center">
          <p className="text-slate-400 font-medium">Client workload is stopped</p>
          <p className="text-slate-500 text-sm mt-1">Select a profile (LOW, MEDIUM, HIGH) and click START WORKLOAD to generate live HTTP client traffic.</p>
        </div>
      )}
    </div>
  );
}
