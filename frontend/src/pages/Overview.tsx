import { useState, useEffect } from 'react';
import { Activity, Play, Database, Zap, Server, Clock } from 'lucide-react';

export default function Overview() {
  const [systemStatus, setSystemStatus] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [demoStatus, setDemoStatus] = useState<any>(null);
  const [seeding, setSeeding] = useState(false);
  const [nodes, setNodes] = useState<any[]>([]);

  const fetchData = async () => {
    try {
      const sRes = await fetch('/api/system/status');
      if (sRes.ok) setSystemStatus(await sRes.json());
      
      const eRes = await fetch('/api/events');
      if (eRes.ok) setEvents(await eRes.json());

      const dRes = await fetch('/api/demo/status');
      if (dRes.ok) setDemoStatus(await dRes.json());

      const nRes = await fetch('/api/nodes');
      if (nRes.ok) setNodes(await nRes.json());
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 1500);
    return () => clearInterval(interval);
  }, []);

  const handleRunDemo = async () => {
    try {
      await fetch('/api/demo/start', { method: 'POST' });
      await fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const handleSeed = async (sizeMb: number) => {
    setSeeding(true);
    try {
      await fetch('/api/admin/seed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ total_size_mb: sizeMb, object_size_mb: 16 })
      });
      await fetchData();
    } catch (e) {
      console.error(e);
    } finally {
      setSeeding(false);
    }
  };

  const isDemoRunning = demoStatus?.status === 'RUNNING';
  const totalBlocks = systemStatus?.replication?.total_blocks ?? 0;

  return (
    <div className="space-y-6">
      {/* Header & Main Action */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-3xl font-semibold text-slate-100">Cluster Overview</h2>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-slate-400">System State:</span>
            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              {systemStatus?.system_state ?? 'INITIALIZING'}
            </span>
          </div>
        </div>

        <button 
          onClick={handleRunDemo}
          disabled={isDemoRunning}
          className="bg-gradient-to-r from-rose-500 to-orange-500 hover:from-rose-400 hover:to-orange-400 text-white font-bold px-6 py-2.5 rounded-lg shadow-lg shadow-rose-500/20 transition-all hover:scale-105 active:scale-95 disabled:opacity-50 text-sm flex items-center gap-2"
        >
          <Play className="w-4 h-4 fill-white" />
          {isDemoRunning ? 'DEMO IN PROGRESS...' : 'RUN END-TO-END DEMO'}
        </button>
      </div>

      {/* 15-Step Demo Live Status Banner */}
      {isDemoRunning && (
        <div className="bg-indigo-900/40 border border-indigo-500/50 p-5 rounded-xl shadow-lg animate-pulse">
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm font-semibold text-indigo-300 flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-400" />
              Automated End-to-End Orchestrator Active
            </span>
            <span className="text-xs font-mono text-emerald-400">
              Step {demoStatus.step} of {demoStatus.total_steps}
            </span>
          </div>
          <p className="text-slate-200 text-sm font-medium">{demoStatus.message}</p>
        </div>
      )}

      {/* Onboarding Wizard (shown if 0 blocks exist) */}
      {totalBlocks === 0 && (
        <div className="bg-slate-800 p-6 rounded-xl border border-indigo-500/40 shadow-sm">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
                <Database className="w-5 h-5 text-indigo-400" />
                Initialize Demo Dataset
              </h3>
              <p className="text-slate-400 text-xs mt-1">
                The cluster has 0 blocks. Seed deterministic test data with 3x replication to enable recovery evaluation.
              </p>
            </div>
            <div className="flex gap-2">
              {[256, 512, 1024].map((size) => (
                <button
                  key={size}
                  onClick={() => handleSeed(size)}
                  disabled={seeding}
                  className="px-3 py-1.5 bg-indigo-600/30 hover:bg-indigo-600/60 border border-indigo-500/40 text-indigo-300 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50"
                >
                  {seeding ? 'Seeding...' : `${size} MB`}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Top 8 Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4">
        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
          <span className="text-xs text-slate-400 block font-medium">Healthy Nodes</span>
          <span className="text-2xl font-bold text-emerald-400 mt-2 block font-mono">
            {systemStatus?.cluster?.healthy_nodes ?? 0}
          </span>
        </div>

        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
          <span className="text-xs text-slate-400 block font-medium">Failed Nodes</span>
          <span className={`text-2xl font-bold mt-2 block font-mono ${
            (systemStatus?.cluster?.failed_nodes ?? 0) > 0 ? 'text-rose-400' : 'text-slate-100'
          }`}>
            {systemStatus?.cluster?.failed_nodes ?? 0}
          </span>
        </div>

        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
          <span className="text-xs text-slate-400 block font-medium">Healthy Blocks</span>
          <span className="text-2xl font-bold text-slate-100 mt-2 block font-mono">
            {systemStatus?.replication?.healthy_blocks ?? 0}
          </span>
        </div>

        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
          <span className="text-xs text-slate-400 block font-medium">Under-Replicated</span>
          <span className={`text-2xl font-bold mt-2 block font-mono ${
            (systemStatus?.replication?.under_replicated_blocks ?? 0) > 0 ? 'text-amber-400' : 'text-slate-100'
          }`}>
            {systemStatus?.replication?.under_replicated_blocks ?? 0}
          </span>
        </div>

        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
          <span className="text-xs text-slate-400 block font-medium">Client p99</span>
          <span className="text-2xl font-bold text-rose-400 mt-2 block font-mono">
            {systemStatus?.client?.p99_ms != null ? `${systemStatus.client.p99_ms} ms` : '--'}
          </span>
        </div>

        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
          <span className="text-xs text-slate-400 block font-medium">Throughput</span>
          <span className="text-2xl font-bold text-emerald-400 mt-2 block font-mono">
            {systemStatus?.client?.throughput_mbps != null ? `${systemStatus.client.throughput_mbps} MB/s` : '--'}
          </span>
        </div>

        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
          <span className="text-xs text-slate-400 block font-medium">Recovery Rate</span>
          <span className="text-2xl font-bold text-indigo-400 mt-2 block font-mono">
            {systemStatus?.recovery?.actual_rate_mbps != null ? `${systemStatus.recovery.actual_rate_mbps} MB/s` : '--'}
          </span>
        </div>

        <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-sm">
          <span className="text-xs text-slate-400 block font-medium">Controller</span>
          <span className={`text-xl font-bold mt-2 block truncate ${
            systemStatus?.controller?.state === 'CRITICAL' ? 'text-rose-400' :
            systemStatus?.controller?.state === 'WARNING' ? 'text-amber-400' :
            systemStatus?.controller?.state === 'NORMAL' ? 'text-indigo-400' :
            'text-slate-400'
          }`}>
            {systemStatus?.controller?.online ? (systemStatus?.controller?.state ?? '--') : 'OFFLINE'}
          </span>
        </div>
      </div>

      {/* Cluster Health Visual + Adaptive Controller Quick View */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cluster Node Visual */}
        <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
          <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <Server className="w-4 h-4 text-indigo-400" /> Cluster Node Map
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {nodes.map(n => {
              const isH = n.status === 'HEALTHY' || n.status === 'healthy';
              return (
                <div key={n.node_id} className={`p-4 rounded-lg border flex flex-col justify-between ${
                  isH ? 'bg-slate-900/60 border-slate-700' : 'bg-rose-950/20 border-rose-500/40'
                }`}>
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-bold text-sm text-slate-200">{n.node_id}</span>
                    <span className={`w-2 h-2 rounded-full ${isH ? 'bg-emerald-400' : 'bg-rose-500'}`}></span>
                  </div>
                  <div className="text-xs text-slate-400 space-y-1 font-mono">
                    <div>Blocks: {n.stored_blocks ?? n.block_count ?? 0}</div>
                    <div>CPU: {isH && n.cpu_percent != null ? `${n.cpu_percent.toFixed(1)}%` : '--'}</div>
                    <div>Disk: {isH && n.disk_percent != null ? `${n.disk_percent.toFixed(1)}%` : '--'}</div>
                  </div>
                </div>
              );
            })}
            {nodes.length === 0 && (
              <div className="col-span-4 text-center py-6 text-slate-500 text-sm">
                No storage nodes registered.
              </div>
            )}
          </div>
        </div>

        {/* Recovery & Controller Quick Status */}
        <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Zap className="w-4 h-4 text-emerald-400" /> Active Recovery & Controller
            </h3>
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Recovery Status:</span>
                <span className="font-semibold text-slate-200">{systemStatus?.recovery?.running ? (systemStatus?.recovery?.status ?? 'RUNNING') : 'IDLE'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Reconstruction Progress:</span>
                <span className="font-bold text-emerald-400">{systemStatus?.recovery?.progress_percent != null ? `${systemStatus.recovery.progress_percent}%` : '--'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Controller Decision Reason:</span>
                <span className="text-slate-300 text-xs max-w-xs truncate text-right">
                  {systemStatus?.controller?.decision_reason || '--'}
                </span>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-700/60 text-xs text-slate-500 flex justify-between">
            <span>Workload: {systemStatus?.client?.running ? (systemStatus?.client?.workload ?? 'Running') : 'Stopped'}</span>
            <span>RPS: {systemStatus?.client?.requests_per_second != null ? systemStatus.client.requests_per_second : '--'}</span>
          </div>
        </div>
      </div>

      {/* Recent Events Log Table */}
      <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm">
        <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
          <Clock className="w-4 h-4 text-indigo-400" /> Recent Cluster Activity Log
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400">
                <th className="pb-2 px-3 font-medium">Time</th>
                <th className="pb-2 px-3 font-medium">Event Type</th>
                <th className="pb-2 px-3 font-medium">Details</th>
              </tr>
            </thead>
            <tbody className="text-slate-300 divide-y divide-slate-700/40">
              {events.slice(0, 8).map((ev, i) => (
                <tr key={i} className="hover:bg-slate-700/20">
                  <td className="py-2.5 px-3 font-mono text-slate-400">{new Date(ev.created_at * 1000).toLocaleTimeString()}</td>
                  <td className="py-2.5 px-3">
                    <span className={`px-2 py-0.5 rounded font-semibold ${
                      ev.event_type.includes('FAILURE') || ev.event_type.includes('CRITICAL') ? 'bg-rose-500/20 text-rose-400' :
                      ev.event_type.includes('RECOVERED') || ev.event_type.includes('RESTORED') ? 'bg-emerald-500/20 text-emerald-400' :
                      'bg-indigo-500/20 text-indigo-300'
                    }`}>
                      {ev.event_type}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 font-mono text-slate-400 truncate max-w-md">{ev.details}</td>
                </tr>
              ))}
              {events.length === 0 && (
                <tr>
                  <td colSpan={3} className="py-6 text-center text-slate-500">No events recorded.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
