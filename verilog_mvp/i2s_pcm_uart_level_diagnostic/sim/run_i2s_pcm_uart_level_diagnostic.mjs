import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const componentDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoDir = path.resolve(componentDir, '..', '..');
const simulatorUrl = pathToFileURL(path.join(repoDir, 'sim', 'node_modules',
  '@veriflow', 'iverilog-wasm', 'dist', 'index.js')).href;
const { simulate } = await import(simulatorUrl);

const sources = [
  'verilog_tp4/rtl/frozen_baseline/i2s_clock_gen.v',
  'verilog_tp4/rtl/frozen_baseline/i2s_rx_24.v',
  'verilog_tp4/rtl/frozen_baseline/uart_tx_byte.v',
  'verilog_mvp/pcm_stream/rtl/safe_field_pcm_packet_tx.v',
  'verilog_mvp/pcm_stream_gain8/rtl/safe_field_pcm_s24_to_s16_sat.v',
  'verilog_mvp/pcm_stream_gain8/rtl/safe_field_pcm_packet_tx_gain8.v',
  'verilog_mvp/i2s_pcm_uart_level_diagnostic/tb/tb_i2s_pcm_uart_levels.v',
];
const files = sources.map((source) => ({
  path: source,
  data: fs.readFileSync(path.join(repoDir, source), 'utf8'),
}));
const hashes = Object.fromEntries(files.map(({ path: source, data }) => [
  source,
  crypto.createHash('sha256').update(data).digest('hex').toUpperCase(),
]));
const started = new Date();
const result = await simulate({ files, sources, generation: '2012', timeoutMs: 120000 });
const passed = result.success
  && /TEST_RESULT:\s*PASS/.test(result.combinedOutput)
  && !/^FAIL /m.test(result.combinedOutput);
const log = [
  'SAFE-FIELD additive I2S -> gain8 PCM16 -> UART level diagnostic',
  `started_utc=${started.toISOString()}`,
  'simulator=@veriflow/iverilog-wasm@0.1.4',
  'hardware_programming=NOT_PERFORMED',
  'frozen_rtl_modified=NO',
  'levels_dbfs=-80,-60,-50,-40,-30,-20,-6',
  'amplitude_formula=round((2^23-1)*10^(dBFS/20))',
  'conversion=saturate_s16(sample24 >>> 5)',
  'protocol=UART_PCM16_V1',
  `success=${result.success}`,
  `stage=${result.stage ?? 'complete'}`,
  ...Object.entries(hashes).map(([source, sha]) => `source_sha256 ${sha} ${source}`),
  '===== simulator output =====',
  result.combinedOutput,
  `OVERALL_RESULT=${passed ? 'PASS' : 'FAIL'}`,
].join('\n');

const evidenceDir = path.join(componentDir, 'evidence');
fs.mkdirSync(evidenceDir, { recursive: true });
const logPath = path.join(evidenceDir, 'simulation.log');
fs.writeFileSync(logPath, `${log}\n`, 'utf8');
process.stdout.write(`${log}\nEVIDENCE_LOG=${logPath}\n`);
process.exitCode = passed ? 0 : 1;
