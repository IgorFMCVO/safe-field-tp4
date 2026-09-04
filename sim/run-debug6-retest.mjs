import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { simulate } from '@veriflow/iverilog-wasm';

const simDir = path.dirname(fileURLToPath(import.meta.url));
const projectDir = path.resolve(simDir, '..');
const startedAt = new Date();
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
const result = await simulate({
  files,
  sources,
  generation: '2012',
  timeoutMs: 120_000,
});
const log = [
  'SAFE-FIELD TP4 DEBUG6 post-contact-fix retest simulation',
  `started_utc=${startedAt.toISOString()}`,
  `success=${result.success}`,
  `stage=${result.stage ?? 'complete'}`,
  result.combinedOutput,
].join('\n');
const logDir = path.join(projectDir, 'evidence', 'physical',
                         'retest_after_contact_fix');
fs.mkdirSync(logDir, { recursive: true });
const stamp = startedAt.toISOString().replaceAll(':', '-').replaceAll('.', '-');
const logPath = path.join(logDir, `debug6_simulation_${stamp}.log`);
fs.writeFileSync(logPath, log, 'utf8');
process.stdout.write(log);
process.stdout.write(`\nEVIDENCE_LOG=${logPath}\n`);
process.exitCode = result.success && /TEST_RESULT:\s*PASS/.test(result.combinedOutput) ? 0 : 1;
