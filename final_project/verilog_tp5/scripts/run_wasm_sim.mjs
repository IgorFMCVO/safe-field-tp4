import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const componentDir = path.resolve(scriptDir, '..');
const repoDir = path.resolve(componentDir, '..');
const workspaceDir = path.resolve(repoDir, '..');
const simulatorPath = path.join(
  workspaceDir,
  'fpga',
  'tp4-audio-inmp441',
  'sim',
  'node_modules',
  '@veriflow',
  'iverilog-wasm',
  'dist',
  'index.js',
);
const { simulate } = await import(pathToFileURL(simulatorPath).href);

const rtlDir = path.join(componentDir, 'rtl');
const rtlSources = fs.readdirSync(rtlDir)
  .filter((name) => name.endsWith('.v'))
  .sort()
  .map((name) => `verilog_tp5/rtl/${name}`);
const testbenches = [
  'tb_arithmetic',
  'tb_command_rx',
  'tb_gpio_oe',
  'tb_tp5_integration',
  'tb_tp5_raw24_coexist',
];

const sourceHashes = new Map();
const results = [];
const evidenceDir = path.join(repoDir, 'docs_tp5', 'evidence', 'simulation');
const waveformDir = path.join(evidenceDir, 'waveforms');
fs.mkdirSync(waveformDir, { recursive: true });
for (const name of testbenches) {
  const testbench = `verilog_tp5/tb/${name}.v`;
  const sources = [...rtlSources, testbench];
  const files = sources.map((source) => {
    const data = fs.readFileSync(path.join(repoDir, source), 'utf8');
    sourceHashes.set(
      source,
      crypto.createHash('sha256').update(data).digest('hex').toUpperCase(),
    );
    return { path: source, data };
  });
  // The testbenches emit VCD files under build/.  Seed that directory in the
  // simulator's in-memory filesystem so $dumpfile can create the artifact.
  files.push({ path: 'build/.keep', data: '' });
  const vcd = `build/${name}.vcd`;
  const result = await simulate({
    files,
    sources,
    generation: '2012',
    artifacts: [vcd],
    timeoutMs: 120000,
  });
  if (result.artifacts?.has(vcd)) {
    fs.writeFileSync(
      path.join(waveformDir, `${name}.vcd`),
      result.artifacts.get(vcd),
    );
  }
  results.push({ name, result });
}

const passed = results.every(({ result }) => result.success
  && /TEST_RESULT:\s*PASS/.test(result.combinedOutput)
  && !/^FAIL(?:\s|$)/m.test(result.combinedOutput));
const log = [
  'SAFE-FIELD TP5 self-checking simulation',
  `finished_utc=${new Date().toISOString()}`,
  'simulator=@veriflow/iverilog-wasm@0.1.4',
  'hardware_programming=NOT_PERFORMED',
  'uart=1500000 baud at 27MHz/18',
  'raw24_and_tp5_commands=COEXIST_ON_ONE_UART_TX',
  ...[...sourceHashes.entries()].map(([source, sha]) => `source_sha256 ${sha} ${source}`),
  ...results.flatMap(({ name, result }) => [
    `===== ${name} =====`,
    `success=${result.success}`,
    `stage=${result.stage ?? 'complete'}`,
    result.combinedOutput,
  ]),
  `OVERALL_RESULT=${passed ? 'PASS' : 'FAIL'}`,
].join('\n');

const logPath = path.join(evidenceDir, 'tp5_wasm_self_checking.log');
fs.writeFileSync(logPath, `${log}\n`, 'utf8');
process.stdout.write(`${log}\nEVIDENCE_LOG=${logPath}\n`);
process.exitCode = passed ? 0 : 1;
