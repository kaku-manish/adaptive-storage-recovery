import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Activity, Server, ActivitySquare, Settings, PlaySquare, ShieldAlert, LineChart } from 'lucide-react';
import Overview from './pages/Overview';
import Cluster from './pages/Cluster';
import Controller from './pages/Controller';
import Experiments from './pages/Experiments';
import RiskAnalysis from './pages/RiskAnalysis';
import Recovery from './pages/Recovery';
import ClientTraffic from './pages/ClientTraffic';

function Layout({ children }: { children: React.ReactNode }) {
  const navItems = [
    { name: 'Overview', path: '/', icon: <Activity className="w-5 h-5" /> },
    { name: 'Cluster', path: '/cluster', icon: <Server className="w-5 h-5" /> },
    { name: 'Client Traffic', path: '/traffic', icon: <LineChart className="w-5 h-5" /> },
    { name: 'Recovery', path: '/recovery', icon: <ActivitySquare className="w-5 h-5" /> },
    { name: 'Adaptive Controller', path: '/controller', icon: <Settings className="w-5 h-5" /> },
    { name: 'Experiments', path: '/experiments', icon: <PlaySquare className="w-5 h-5" /> },
    { name: 'Risk Analysis', path: '/risk', icon: <ShieldAlert className="w-5 h-5" /> },
  ];

  return (
    <div className="flex h-screen bg-slate-900 text-slate-200">
      <aside className="w-64 bg-slate-800 border-r border-slate-700 flex flex-col">
        <div className="h-16 flex items-center px-6 border-b border-slate-700">
          <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">
            ADAPTIVE RECOVERY
          </h1>
        </div>
        <nav className="flex-1 overflow-y-auto py-4">
          <ul className="space-y-1">
            {navItems.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  className={({ isActive }) =>
                    `flex items-center px-6 py-3 space-x-3 transition-colors ${
                      isActive
                        ? 'bg-indigo-600/20 text-indigo-400 border-r-4 border-indigo-500'
                        : 'text-slate-400 hover:bg-slate-700/50 hover:text-slate-200'
                    }`
                  }
                >
                  {item.icon}
                  <span className="font-medium">{item.name}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <main className="flex-1 flex flex-col overflow-hidden bg-slate-900">
        <div className="flex-1 overflow-y-auto p-8">
          {children}
        </div>
      </main>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/cluster" element={<Cluster />} />
          <Route path="/traffic" element={<ClientTraffic />} />
          <Route path="/recovery" element={<Recovery />} />
          <Route path="/controller" element={<Controller />} />
          <Route path="/experiments" element={<Experiments />} />
          <Route path="/risk" element={<RiskAnalysis />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;
