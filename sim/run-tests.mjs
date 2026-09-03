import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { simulate } from '@veriflow/iverilog-wasm';

const simDir = path.dirname(fileURLToPath(import.meta.url));
const projectDir = path.resolve(simDir, '..');
const startedAt = new Date();
const tests = [
  {
    name: 'unit_and_protocol',
    sources: [
      'src/i2s_clock_gen.v',
      'src/i2s_rx_24.v',
      'src/audio_energy_detector.v',
      'tb/tb_safe_field_tp4.v',
    ],
  },
  {
    name: 'end_to_end_top',
    sources: [
      'src/rasp_to_tang.v',
      'src/i2s_clock_gen.v',
      'src/i2s_rx_24.v',
      'src/audio_energy_detector.v',
      'src/safe_field_tp4.v',
      'tb/tb_end_to_end.v',
    ],
  },
];

const results = [];
for (const test of tests) {
  const files = test.sources.map((relativePath) => ({
    path: relativePath.replaceAll('\\', '/'),
    data: fs.readFileSync(path.join(projectDir, relativePath), 'utf8'),
  }));
  const result = await simulate({
    files,
    sources: test.sources,
    generation: '2012',
    timeoutMs: 120_000,
  });
  results.push({ ...test, result });
}

const header = [
  `SAFE-FIELD TP4 simulation`,
  `started_utc=${startedAt.toISOString()}`,
  `node=${process.version}`,
  `simulator=@veriflow/iverilog-wasm@0.1.4 (Icarus Verilog WASM)`,
  '',
].join('\n');
const sections = results.map(({ name, result }) => [
  `===== TEST ${name} =====`,
  `success=${result.success}`,
  `stage=${result.stage ?? 'complete'}`,
  result.combinedOutput,
].join('\n'));
const log = header + sections.join('\n');

const logDir = path.join(projectDir, 'evidence', 'simulation');
fs.mkdirSync(logDir, { recursive: true });
const stamp = startedAt.toISOString().replaceAll(':', '-').replaceAll('.', '-');
const logPath = path.join(logDir, `simulation_${stamp}.log`);
fs.writeFileSync(logPath, log, 'utf8');

process.stdout.write(log);
process.stdout.write(`\nEVIDENCE_LOG=${logPath}\n`);

const passed = results.every(({ result }) =>
  result.success && /TEST_RESULT:\s*PASS/.test(result.combinedOutput));
process.exitCode = passed ? 0 : 1;
