import { useState, useEffect } from 'react';
import { Server, Activity, HardDrive, Wifi, ShieldAlert, CheckCircle, Clock } from 'lucide-react';

export default function Cluster() {
  const [nodes, setNodes] = useState<any[]>([]);
  const [loadingNode, setLoadingNode] = useState<string | null>(null);

  const fetchNodes = async () => {
    try {
      const res = await fetch('/api/nodes');
      if (res.ok) {
        const data = await res.json();
        setNodes(data);
      }
    } catch (e) {
      console.error("Failed to fetch nodes", e);
    }
  };

  useEffect(() => {
    fetchNodes();
    const interval = setInterval(fetchNodes, 1500);
    return () => clearInterval(interval);
  }, []);

  const injectFailure = async (nodeId: string) => {
    setLoadingNode(nodeId);
    try {
      await fetch(`/api/admin/fail/${nodeId}`, { method: 'POST' });
      await fetchNodes();
    } catch (e) {
      console.error("Failed to inject fault:", e);
    } finally {
      setLoadingNode(null);
    }
  };

  const recoverNode = async (nodeId: string) => {
    setLoadingNode(nodeId);
    try {
      await fetch(`/api/admin/recover/${nodeId}`, { method: 'POST' });
      await fetchNodes();
    } catch (e) {
      console.error("Failed to recover node:", e);
    } finally {
      setLoadingNode(null);
    }
  };

  const formatBytes = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-semibold text-slate-100">Cluster Infrastructure</h2>
          <p className="text-slate-400 text-sm mt-1">Live physical storage nodes, hardware utilization, and fault injection</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
        {nodes.map(node => {
          const isHealthy = node.status === 'HEALTHY' || node.status === 'healthy';
          const isFailed = node.status === 'FAILED' || node.status === 'failed';
          const isReconciling = node.status === 'RECONCILING';

          return (
            <div key={node.node_id} className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-sm flex flex-col justify-between">
              <div>
                <div className="flex justify-between items-center border-b border-slate-700 pb-4 mb-4">
                  <div className="flex items-center gap-3">
                    <Server className="w-6 h-6 text-indigo-400" />
                    <div>
                      <h3 className="font-bold text-lg text-slate-200">{node.node_id}</h3>
                      <span className="text-xs text-slate-500 font-mono block">{node.url}</span>
                    </div>
                  </div>
                  <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${
                    isHealthy ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                    isReconciling ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' :
                    'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                  }`}>
                    {node.status.toUpperCase()}
                  </span>
                </div>
                
                <div className="space-y-3.5 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Stored Blocks</span>
                    <span className="text-slate-100 font-mono font-medium">{node.stored_blocks ?? node.block_count ?? 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Stored Bytes</span>
                    <span className="text-slate-100 font-mono font-medium">{formatBytes(node.stored_bytes)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400 flex items-center gap-2"><Activity className="w-3.5 h-3.5 text-indigo-400"/> CPU</span>
                    <span className="text-slate-100 font-mono font-medium">
                      {isHealthy && node.cpu_percent != null ? `${node.cpu_percent.toFixed(1)}%` : '--'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400 flex items-center gap-2"><Server className="w-3.5 h-3.5 text-indigo-400"/> Memory</span>
                    <span className="text-slate-100 font-mono font-medium">
                      {isHealthy && node.memory_percent != null ? `${node.memory_percent.toFixed(1)}%` : '--'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400 flex items-center gap-2"><HardDrive className="w-3.5 h-3.5 text-indigo-400"/> Disk</span>
                    <span className="text-slate-100 font-mono font-medium">
                      {isHealthy && node.disk_percent != null ? `${node.disk_percent.toFixed(1)}%` : '--'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400 flex items-center gap-2"><Wifi className="w-3.5 h-3.5 text-indigo-400"/> Network RX/TX</span>
                    <span className="text-slate-100 font-mono font-medium text-xs">
                      {isHealthy && (node.network_rx_bytes != null || node.network_tx_bytes != null) ? `${formatBytes(node.network_rx_bytes)} / ${formatBytes(node.network_tx_bytes)}` : '--'}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs pt-1 border-t border-slate-700/50">
                    <span className="text-slate-500 flex items-center gap-1.5"><Clock className="w-3 h-3"/> Heartbeat</span>
                    <span className="text-slate-400 font-mono">
                      {node.last_heartbeat ? `${new Date(node.last_heartbeat * 1000).toLocaleTimeString()}` : '--'}
                    </span>
                  </div>
                </div>
              </div>
              
              <div className="mt-6 pt-4 border-t border-slate-700 flex gap-2">
                <button 
                  onClick={() => injectFailure(node.node_id)}
                  disabled={isFailed || loadingNode === node.node_id}
                  className="flex-1 flex justify-center items-center gap-1.5 bg-rose-600/20 hover:bg-rose-600/40 text-rose-400 py-2 rounded-lg transition-colors disabled:opacity-30 font-medium text-xs"
                >
                  <ShieldAlert className="w-3.5 h-3.5" /> Inject Failure
                </button>
                <button 
                  onClick={() => recoverNode(node.node_id)}
                  disabled={isHealthy || loadingNode === node.node_id}
                  className="flex-1 flex justify-center items-center gap-1.5 bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-400 py-2 rounded-lg transition-colors disabled:opacity-30 font-medium text-xs"
                >
                  <CheckCircle className="w-3.5 h-3.5" /> Recover Node
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
