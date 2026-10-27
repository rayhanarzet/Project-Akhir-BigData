import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api/historical-hdfs': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 15 * 60 * 1000,
        proxyTimeout: 15 * 60 * 1000,
      },
      '/api/ingestion/backfill': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 20 * 60 * 1000,
        proxyTimeout: 20 * 60 * 1000,
      },
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
        configure: (proxy) => {
          // Hindari spam log ECONNREFUSED di terminal saat FastAPI belum dinyalakan
          proxy.on('error', (_err, _req, res) => {
            if (res && 'writeHead' in res && !res.headersSent) {
              res.writeHead(503, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ detail: 'FastAPI tidak dapat dihubungi. Jalankan backend di port 8000.' }));
            }
          });
        },
      },
    },
  },
});
