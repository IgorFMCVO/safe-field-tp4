import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { simulate } from '@veriflow/iverilog-wasm';

const simDir = path.dirname(fileURLToPath(import.meta.url));
const projectDir = path.resolve(simDir, '..');
const startedAt = new Date();
const variants = [
  { name: 'NONE', constraint: 'src/debug7_sd_none.cst' },
  { name: 'UP', constraint: 'src/debug7_sd_up.cst' },
];
const sources = [
  'src/i2s_clock_gen.v',
  'src/i2s_rx_24.v',
  'src/debug6_low_rate_i2s.v',
  'tb/tb_debug6_low_rate_i2s.v',
];
const files = sources.map((relativePath) => ({
  path: relativePath.replaceAll('\\', '/'),
  data: fs.readFileSync(path.join(projectDir, relativePath), 'utf8'),
}));
const sections = [];
let passed = true;
for (const variant of variants) {
  const cst = fs.readFileSync(path.join(projectDir, variant.constraint), 'utf8');
  const pinOk = /IO_LOC\s+"i2s_sd"\s+43\s*;/.test(cst);
  const pullOk = new RegExp(`IO_PORT\\s+"i2s_sd"[^;]*PULL_MODE=${variant.name}`).test(cst);
  const result = await simulate({ files, sources, generation: '2012', timeoutMs: 120_000 });
  const variantPassed = pinOk && pullOk && result.success &&
                        /TEST_RESULT:\s*PASS/.test(result.combinedOutput);
  passed &&= variantPassed;
  sections.push([
    `===== DEBUG7 PULL_${variant.name} =====`,
    `constraint=${variant.constraint}`,
    `pin43_input_constraint=${pinOk}`,
    `pull_mode_constraint=${pullOk}`,
    `simulation_success=${result.success}`,
    result.combinedOutput,
    `VARIANT_RESULT: ${variantPassed ? 'PASS' : 'FAIL'}`,
  ].join('\n'));
}
const log = [
  'SAFE-FIELD TP4 DEBUG7 simulations',
  `started_utc=${startedAt.toISOString()}`,
  ...sections,
].join('\n');
const logDir = path.join(projectDir, 'evidence', 'physical',
                         'debug7_sd_slot_diagnostic');
fs.mkdirSync(logDir, { recursive: true });
const stamp = startedAt.toISOString().replaceAll(':', '-').replaceAll('.', '-');
const logPath = path.join(logDir, `simulation_${stamp}.log`);
fs.writeFileSync(logPath, log, 'utf8');
process.stdout.write(log);
process.stdout.write(`\nEVIDENCE_LOG=${logPath}\n`);
process.exitCode = passed ? 0 : 1;
