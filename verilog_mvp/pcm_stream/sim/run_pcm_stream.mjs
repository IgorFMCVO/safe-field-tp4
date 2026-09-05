import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const componentDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoDir = path.resolve(componentDir, '..', '..');
const simulatorUrl = pathToFileURL(path.join(repoDir, 'sim', 'node_modules',
  '@veriflow', 'iverilog-wasm', 'dist', 'index.js')).href;
const { simulate } = await import(simulatorUrl);
const started = new Date();
const common = [
  'verilog_tp4/rtl/frozen_baseline/uart_tx_byte.v',
  'verilog_mvp/pcm_stream/rtl/safe_field_pcm_packet_tx.v',
];
const tests = [
  ['packet_protocol', 'verilog_mvp/pcm_stream/tb/tb_safe_field_pcm_packet_tx.v'],
  ['sustained_physical_rate', 'verilog_mvp/pcm_stream/tb/tb_safe_field_pcm_sustained.v'],
];
const results = [];
for (const [name, testbench] of tests) {
  const sources = [...common, testbench];
  const files = sources.map((source) => ({
    path: source,
    data: fs.readFileSync(path.join(repoDir, source), 'utf8'),
  }));
  results.push([name, await simulate({ files, sources, generation: '2012', timeoutMs: 120000 })]);
}
const log = [
  'SAFE-FIELD MVP PCM stream self-checking simulation',
  `started_utc=${started.toISOString()}`,
  'simulator=@veriflow/iverilog-wasm@0.1.4',
  ...results.map(([name, result]) => [
    `===== ${name} =====`,
    `success=${result.success}`,
    `stage=${result.stage ?? 'complete'}`,
    result.combinedOutput,
  ].join('\n')),
].join('\n');
const evidenceDir = path.join(componentDir, 'evidence');
fs.mkdirSync(evidenceDir, { recursive: true });
const logPath = path.join(evidenceDir, 'simulation.log');
fs.writeFileSync(logPath, log, 'utf8');
process.stdout.write(`${log}\nEVIDENCE_LOG=${logPath}\n`);
process.exitCode = results.every(([, result]) =>
  result.success && /TEST_RESULT:\s*PASS/.test(result.combinedOutput)) ? 0 : 1;
