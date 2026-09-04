import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { simulate } from '@veriflow/iverilog-wasm';

const projectDir=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const startedAt=new Date();
const tests=[
 {name:'uart_byte_baud_and_framing',sources:['src/uart_tx_byte.v','tb/tb_uart_tx_byte.v']},
 {name:'telemetry_packet_protocol',sources:['src/uart_tx_byte.v','src/safe_field_telemetry_tx.v','tb/tb_safe_field_telemetry_tx.v']},
 {name:'mvp_audio_uart_integration',sources:[
  'src/rasp_to_tang.v','src/i2s_clock_gen.v','src/i2s_rx_24.v',
  'src/audio_activity_fsm_persistent.v','src/audio_energy_detector_persistent.v',
  'src/uart_tx_byte.v','src/safe_field_telemetry_tx.v','src/safe_field_mvp_hw_bridge.v',
  'tb/tb_safe_field_mvp_hw_bridge.v']},
];
const results=[];
for(const test of tests){
 const files=test.sources.map(p=>({path:p,data:fs.readFileSync(path.join(projectDir,p),'utf8')}));
 const result=await simulate({files,sources:test.sources,generation:'2012',timeoutMs:120000});
 results.push({...test,result});
}
const log=[
 'SAFE-FIELD MVP hardware bridge simulation',`started_utc=${startedAt.toISOString()}`,
 `node=${process.version}`,'simulator=@veriflow/iverilog-wasm@0.1.4 (Icarus Verilog WASM)',
 ...results.map(({name,result})=>`===== TEST ${name} =====\nsuccess=${result.success}\nstage=${result.stage??'complete'}\n${result.combinedOutput}`)
].join('\n');
const logDir=path.join(projectDir,'evidence','mvp_hw_bridge');fs.mkdirSync(logDir,{recursive:true});
const stamp=startedAt.toISOString().replaceAll(':','-').replaceAll('.','-');
const logPath=path.join(logDir,`simulation_${stamp}.log`);fs.writeFileSync(logPath,log,'utf8');
process.stdout.write(log+`\nEVIDENCE_LOG=${logPath}\n`);
process.exitCode=results.every(({result})=>result.success&&/TEST_RESULT:\s*PASS/.test(result.combinedOutput))?0:1;
