import assert from 'node:assert/strict';
import { File } from 'node:buffer';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

// Vite supplies import.meta.env in the browser; replace only that environment here.
const source = (await readFile(new URL('../src/services/api.ts', import.meta.url), 'utf8'))
  .replace('import.meta.env.VITE_API_URL', "''");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext },
});
const api = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('every API operation rejects offline instead of returning fabricated results', async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => { throw new TypeError('offline'); };
  const cfg = { symbol: 'BTCUSDT', timeframe: '1h' };
  const operations = [
    () => api.fetchHistoricalBaseline(),
    () => api.uploadDatasetFile(new File(['timestamp'], 'real.csv'), 'BTCUSDT', ''),
    () => api.triggerBinanceLiveSync(['BTCUSDT'], 300),
    () => api.fetchCronStatus(),
    () => api.updateCronConfig(true, 5),
    () => api.runDynamicAnalyticsApi(cfg),
    () => api.fetchCrossAssetCorrelation('1h', 'BTCUSDT', 'ETHUSDT', 30),
    () => api.trainAndEvaluateModels(cfg),
    () => api.fetchLatestModelMetrics(cfg),
    () => api.predictNextPeriodApi('BTCUSDT', '1h'),
  ];
  for (const operation of operations) {
    await assert.rejects(operation, /Backend tidak dapat dihubungi/);
  }
});

test('server data errors reach the dashboard unchanged', async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'Data penelitian belum tersedia' }), { status: 409 });
  await assert.rejects(() => api.runDynamicAnalyticsApi({}), /Data penelitian belum tersedia/);
});

test('invalid successful response is an error rather than simulated data', async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => new Response('<html>wrong server</html>');
  await assert.rejects(() => api.fetchHistoricalBaseline(), /Respons backend tidak valid/);
});

test('successful baseline contains exactly what the backend returned', async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const baseline = { pipeline_status: 'NO_DATA', assets: [], audit_logs: [], hdfs_cluster_path: '/research' };
  globalThis.fetch = async () => new Response(JSON.stringify(baseline));
  assert.deepEqual(await api.fetchHistoricalBaseline(), { data: baseline, isLiveBackend: true });
});

test('live subscription forwards prices and reports disconnects without simulated quotes', (t) => {
  const original = globalThis.EventSource;
  t.after(() => { globalThis.EventSource = original; });
  let source;
  globalThis.EventSource = class {
    constructor(url) { this.url = url; source = this; }
    close() { this.closed = true; }
  };
  const events = [];
  const errors = [];
  const close = api.subscribeMarket((event) => events.push(event), (error) => errors.push(error));
  assert.equal(source.url, '/api/market/stream');
  source.onmessage({ data: JSON.stringify({ type: 'quote', symbol: 'BTCUSDT', close: 101 }) });
  assert.equal(events[0].close, 101);
  source.onerror();
  assert.equal(events.length, 1);
  assert.match(errors[0], /terputus/);
  source.onmessage({ data: JSON.stringify({ type: 'quote', symbol: 'BTCUSDT', close: null }) });
  assert.equal(events.length, 1);
  assert.match(errors[1], /tidak valid/);
  close();
  assert.equal(source.closed, true);
  assert.equal(source.onmessage, null);
});
