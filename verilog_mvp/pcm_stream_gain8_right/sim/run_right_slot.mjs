import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const root = path.resolve(import.meta.dirname, '..', '..', '..');
const simModule = await import(pathToFileURL(path.join(root, 'sim', 'node_modules', '@veriflow', 'iverilog-wasm', 'dist', 'index.js')).href);
const files = [
  'verilog_tp4/rtl/frozen_baseline/uart_tx_byte.v',
  'verilog_mvp/pcm_stream/rtl/safe_field_pcm_packet_tx.v',
  'verilog_mvp/pcm_stream_gain8/rtl/safe_field_pcm_s24_to_s16_sat.v',
  'verilog_mvp/pcm_stream_gain8/rtl/safe_field_pcm_packet_tx_gain8.v',
  'verilog_mvp/pcm_stream_gain8_right/tb/tb_right_slot_selector.v'
];
const inputs = files.map(f => ({ path: f, data: fs.readFileSync(path.join(root, f), 'utf8') }));
const result = await simModule.simulate({ files: inputs, sources: files, generation: '2012', timeoutMs: 120000 });
const output = result.combinedOutput;
console.log(output);
if (!output.includes('TEST_RESULT: PASS') || output.includes('TEST_RESULT: FAIL')) process.exit(1);
