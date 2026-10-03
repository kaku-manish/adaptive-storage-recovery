# Adaptive Storage Recovery - Frontend Dashboard

Real-time Observability and Control Plane console for the Adaptive Storage Recovery system, built with **React 19**, **Vite**, **TailwindCSS**, **Recharts**, and **Lucide Icons**.

---

## Features

- **Cluster Topology Visualization**: Real-time status of storage nodes, heartbeat health checks, and capacity.
- **Adaptive Controller Dashboard**: Live visualization of the Finite State Machine (NORMAL, WARNING, CRITICAL, RECOVERING).
- **Client Traffic & Contention Graphs**: Real-time tracking of Client p99 Latency vs. Background Recovery Bandwidth (MB/s).
- **Replica Recovery Control**: Manual rate override, start/stop recovery jobs, and under-replicated block metrics.
- **Automated Experiments & Comparison**: Execute trials (ADAPTIVE vs UNTHROTTLED vs FIXED_RATE) and compare throughput degradation and risk windows.
- **Durability Risk Analysis**: Real-time mathematical calculation of second-disk failure probabilities.

---

## Local Development

### Prerequisites
- Node.js >= 18.0.0
- npm >= 9.0.0

### Installation & Run

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start development server:
   ```bash
   npm run dev
   ```

4. Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_COORDINATOR_URL` | `http://127.0.0.1:8000` | Target URL for Coordinator API proxy |
| `VITE_CONTROLLER_URL` | `http://127.0.0.1:8003` | Target URL for Controller API proxy |

---

## Building for Production

```bash
npm run build
```
The optimized static build will be output to the `dist/` directory.

---

## Deployment Options

### 1. Vercel
1. Import the repository on [Vercel](https://vercel.com).
2. Set Root Directory to `frontend`.
3. Set Build Command to `npm run build` and Output Directory to `dist`.
4. Add backend URL environment variables if hosted remotely.

### 2. Netlify
1. Connect repository on [Netlify](https://netlify.com).
2. Base directory: `frontend`
3. Build command: `npm run build`
4. Publish directory: `frontend/dist`

### 3. Docker
```bash
docker build -t storage-recovery-frontend .
docker run -p 3000:80 storage-recovery-frontend
```
