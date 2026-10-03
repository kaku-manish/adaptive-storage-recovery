import { useState, useEffect } from 'react';
import { Activity, Settings2, Power, Zap, HardDrive, Wifi } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export default function Controller() {
  const [status, setStatus] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [chartData, setChartData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    try {
      const statRes = await fetch('/api/controller/status');
      if (statRes.ok) {
        const data = await statRes.json();
        setStatus(data);
        
        if (data.online && data.is_enabled) {
          setChartData(prev => {
            const now = new Date().toLocaleTimeString();
            const newData = [...prev, {
              time: now,
              p99: data.current_p99 || 0,
              rate: data.current_rate_mbps || 0,
              throughput: data.current_throughput || 0
            }];
            if (newData.length > 25) newData.shift();
            return newData;
          });
        }
      } else {
        setStatus({ online: false });
      }
      
      const histRes = await fetch('/api/controller/history');
      if (histRes.ok) {
        setHistory(await histRes.json());
      }
    } catch (e) {
      setStatus({ online: false });
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 1500);
    return () => clearInterval(interval);
  }, []);

  const toggleController = async () => {
    setLoading(true);
    try {
      const endpoint = status?.is_enabled ? '/api/controller/disable' : '/api/controller/enable';
      await fetch(endpoint, { method: 'POST' });
      await fetchData();
    } finally {
      setLoading(false);
    }
  };

  const isOnline = status?.online;
  const isEnabled = status?.is_enabled;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-3xl font-semibold text-slate-100">Adaptive Feedback Controller</h2>
          <p className="text-slate-400 text-sm mt-1">Multi-dimensional closed loop protecting client p99 latency & throughput</p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700">
            <span className={`w-2.5 h-2.5 rounded-full ${isOnline ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}`}></span>
            <span className="text-xs font-semibold text-slate-300">
              {isOnline ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>

          <button
            onClick={toggleController}
            disabled={!isOnline || loading}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-colors shadow-sm disabled:opacity-40 ${
              isEnabled ? 'bg-amber-600 hover:bg-amber-500 text-white' : 'bg-emerald-600 hover:bg-emerald-500 text-white'
            }`}
          >
            <Power className="w-4 h-4" />
            {isEnabled ? 'DISABLE CONTROLLER' : 'ENABLE CONTROLLER'}
          </button>
        </div>
      </div>

      {/* State & Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm col-span-1 flex flex-col justify-between">
          <div>
            <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-5">Finite State Machine</h3>
            <div className="space-y-5">
              <div>
                <span className="text-slate-500 block text-xs uppercase tracking-wider">Current State</span>
                <span className={`text-2xl font-bold ${
                  status?.state === 'CRITICAL' ? 'text-rose-400' :
                  status?.state === 'WARNING' ? 'text-amber-400' :
                  status?.state === 'RECOVERING' ? 'text-emerald-400' :
                  status?.state === 'NORMAL' ? 'text-indigo-400' :
                  'text-slate-400'
                }`}>
                  {isOnline ? (status?.state ?? 'IDLE') : 'OFFLINE'}
                </span>
                <span className="text-xs text-slate-400 block mt-1">
                  Reason: <span className="text-slate-300">{status?.decision_reason ?? 'Awaiting evaluation'}</span>
                </span>
              </div>

              <div>
                <span className="text-slate-500 block text-xs uppercase tracking-wider">Assigned Recovery Rate</span>
                <span className="text-xl font-bold text-emerald-400 font-mono">
                  {isOnline && status?.current_rate_mbps !== undefined ? `${status.current_rate_mbps.toFixed(1)} MB/s` : '--'}
                </span>
              </div>

              <div>
                <span className="text-slate-500 block text-xs uppercase tracking-wider">Consecutive Samples</span>
                <span className="text-sm text-slate-300 font-mono block mt-0.5">
                  Bad: <span className="text-rose-400 font-bold">{status?.bad_samples ?? 0}</span> / 3 | Good: <span className="text-emerald-400 font-bold">{status?.good_samples ?? 0}</span> / 3
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm col-span-3">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-400" /> Live Closed-Loop Telemetry
            </h3>
            <div className="flex items-center gap-6 text-xs font-mono text-slate-400">
              <span className="flex items-center gap-1.5"><Zap className="w-3.5 h-3.5 text-emerald-400"/> Tput: {status?.current_throughput != null ? `${status.current_throughput.toFixed(1)} MB/s` : '--'}</span>
              <span className="flex items-center gap-1.5"><HardDrive className="w-3.5 h-3.5 text-indigo-400"/> Disk: {status?.current_disk_percent != null ? `${status.current_disk_percent.toFixed(1)}%` : '--'}</span>
              <span className="flex items-center gap-1.5"><Wifi className="w-3.5 h-3.5 text-amber-400"/> Net: {status?.current_network_percent != null ? `${status.current_network_percent.toFixed(1)}%` : '--'}</span>
            </div>
          </div>
          
          <div className="h-64">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="time" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="left" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" stroke="#34d399" tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }} />
                  <Legend />
                  <Line yAxisId="left" type="monotone" dataKey="p99" stroke="#818cf8" strokeWidth={2} name="Client p99 (ms)" dot={false} isAnimationActive={false} />
                  <Line yAxisId="right" type="stepAfter" dataKey="rate" stroke="#34d399" strokeWidth={2} name="Rate Limit (MB/s)" dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                Waiting for active controller telemetry...
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Decision History Table */}
      <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
        <h3 className="text-lg font-medium text-slate-200 mb-4 flex items-center gap-2">
          <Settings2 className="w-5 h-5 text-indigo-400" />
          Controller Decision History
        </h3>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 text-xs uppercase tracking-wider">
                <th className="pb-3 px-4">Timestamp</th>
                <th className="pb-3 px-4">State Transition</th>
                <th className="pb-3 px-4">Rate Adjustment</th>
                <th className="pb-3 px-4">Measured p99</th>
                <th className="pb-3 px-4">Measured Throughput</th>
                <th className="pb-3 px-4">Trigger Reason</th>
              </tr>
            </thead>
            <tbody className="text-slate-300 divide-y divide-slate-700/40">
              {[...history].reverse().map((row, i) => (
                <tr key={i} className="hover:bg-slate-700/20">
                  <td className="py-3 px-4 font-mono text-xs text-slate-400">{new Date(row.timestamp * 1000).toLocaleTimeString()}</td>
                  <td className="py-3 px-4">
                    <span className="text-slate-400 text-xs">{row.state_before}</span>
                    <span className="mx-2 text-slate-500">→</span>
                    <span className={`font-semibold text-xs ${
                      row.state_after === 'CRITICAL' ? 'text-rose-400' :
                      row.state_after === 'WARNING' ? 'text-amber-400' :
                      row.state_after === 'NORMAL' ? 'text-indigo-400' :
                      'text-emerald-400'
                    }`}>
                      {row.state_after}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-mono text-xs">
                    <span className="text-slate-400">{(row.old_rate_mbps ?? row.old_rate) != null ? (row.old_rate_mbps ?? row.old_rate).toFixed(1) : '--'}</span>
                    <span className="mx-1 text-slate-500">→</span>
                    <span className="text-emerald-400 font-bold">{(row.new_rate_mbps ?? row.new_rate) != null ? `${(row.new_rate_mbps ?? row.new_rate).toFixed(1)} MB/s` : '--'}</span>
                  </td>
                  <td className="py-3 px-4 font-mono text-xs text-slate-200">{(row.p99_ms ?? row.p99) != null ? `${(row.p99_ms ?? row.p99).toFixed(1)} ms` : '--'}</td>
                  <td className="py-3 px-4 font-mono text-xs text-slate-200">{(row.throughput_mbps ?? row.throughput) != null ? `${(row.throughput_mbps ?? row.throughput).toFixed(1)} MB/s` : '--'}</td>
                  <td className="py-3 px-4 text-xs text-amber-200/90">{row.trigger_reason ?? row.reason ?? '--'}</td>
                </tr>
              ))}
              {history.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500">
                    No controller decisions recorded yet. Start recovery and client workload to observe transitions.
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
