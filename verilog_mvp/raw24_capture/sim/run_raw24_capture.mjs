import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const componentDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoDir = path.resolve(componentDir, '..', '..');
const simulatorUrl = pathToFileURL(path.join(repoDir, 'sim', 'node_modules',
  '@veriflow', 'iverilog-wasm', 'dist', 'index.js')).href;
const { simulate } = await import(simulatorUrl);

const common = [
  'verilog_tp4/rtl/frozen_baseline/i2s_clock_gen.v',
  'verilog_tp4/rtl/frozen_baseline/i2s_rx_24.v',
  'verilog_tp4/rtl/frozen_baseline/uart_tx_byte.v',
  'verilog_mvp/pcm_stream_gain8/rtl/safe_field_pcm_s24_to_s16_sat.v',
  'verilog_mvp/raw24_capture/rtl/safe_field_raw24_packet_tx.v',
];
const tests = [
  ['protocol_and_i2s_chain',
    'verilog_mvp/raw24_capture/tb/tb_safe_field_raw24_packet_tx.v'],
  ['sustained_physical_rate',
    'verilog_mvp/raw24_capture/tb/tb_safe_field_raw24_sustained.v'],
];
const results = [];
for (const [name, testbench] of tests) {
  const sources = [...common, testbench];
  const files = sources.map((source) => ({
    path: source,
    data: fs.readFileSync(path.join(repoDir, source), 'utf8'),
  }));
  const result = await simulate({ files, sources, generation: '2012', timeoutMs: 120000 });
  results.push([name, sources, files, result]);
}
const sourceMap = new Map();
for (const [, , files] of results) {
  for (const { path: source, data } of files)
    sourceMap.set(source, crypto.createHash('sha256').update(data).digest('hex').toUpperCase());
}
const passed = results.every(([, , , result]) => result.success
  && /TEST_RESULT:\s*PASS/.test(result.combinedOutput)
  && !/^FAIL /m.test(result.combinedOutput));
const log = [
  'SAFE-FIELD RAW_I2S_24_CAPTURE self-checking simulation',
  `started_utc=${new Date().toISOString()}`,
  'simulator=@veriflow/iverilog-wasm@0.1.4',
  'hardware_programming=NOT_PERFORMED',
  'frame_bytes=95 sync=A5C4 version=01 type=21 count=16 stride=2',
  'pair=RAW24_LE_3_BYTES+GAIN8_PCM16_LE_2_BYTES',
  'crc=CRC16_CCITT_FALSE_BYTES_2_THROUGH_92',
  'uart=1500000 baud at 27MHz/18',
  'nominal_line_utilization_percent=83.49609375',
  ...[...sourceMap.entries()].map(([source, sha]) => `source_sha256 ${sha} ${source}`),
  ...results.map(([name, , , result]) => [
    `===== ${name} =====`,
    `success=${result.success}`,
    `stage=${result.stage ?? 'complete'}`,
    result.combinedOutput,
  ].join('\n')),
  `OVERALL_RESULT=${passed ? 'PASS' : 'FAIL'}`,
].join('\n');
const evidenceDir = path.join(componentDir, 'evidence');
fs.mkdirSync(evidenceDir, { recursive: true });
const logPath = path.join(evidenceDir, 'simulation.log');
fs.writeFileSync(logPath, `${log}\n`, 'utf8');
process.stdout.write(`${log}\nEVIDENCE_LOG=${logPath}\n`);
process.exitCode = passed ? 0 : 1;
