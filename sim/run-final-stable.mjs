import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { simulate } from '@veriflow/iverilog-wasm';

const projectDir=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const startedAt=new Date();
const common=['src/audio_activity_fsm_persistent.v'];
const tests=[
 {name:'persistence_unit',sources:[...common,'tb/tb_audio_activity_fsm_persistent.v']},
 {name:'physical_99s_regression',sources:[...common,'tb/tb_fsm_physical_regression.v'],data:['evidence/physical/retest_after_contact_fix/fsm_stabilization/physical_energy_99s.memh']},
 {name:'synchronized_cued_regression',sources:[...common,'tb/tb_fsm_final_cued_regression.v'],data:['evidence/physical/retest_after_contact_fix/fsm_stabilization/cued_capture03_regression/physical_energy_99s.memh']},
 {name:'stable_end_to_end',sources:['src/rasp_to_tang.v','src/i2s_clock_gen.v','src/i2s_rx_24.v',...common,'src/audio_energy_detector_persistent.v','src/safe_field_tp4_audio_stable.v','tb/tb_safe_field_tp4_audio_stable.v']},
];
const results=[];
for(const test of tests){
 const inputPaths=[...test.sources,...(test.data??[])];
 const files=inputPaths.map(p=>({path:p,data:fs.readFileSync(path.join(projectDir,p),'utf8')}));
 const result=await simulate({files,sources:test.sources,generation:'2012',timeoutMs:120000});
 results.push({...test,result});
}
const sections=results.map(({name,result})=>[
 `===== TEST ${name} =====`,`success=${result.success}`,`stage=${result.stage??'complete'}`,result.combinedOutput
].join('\n'));
const log=[
 'SAFE-FIELD TP4 final stable simulation',`started_utc=${startedAt.toISOString()}`,
 `node=${process.version}`,'simulator=@veriflow/iverilog-wasm@0.1.4 (Icarus Verilog WASM)',...sections
].join('\n');
const logDir=path.join(projectDir,'evidence','physical','retest_after_contact_fix','fsm_stabilization');
fs.mkdirSync(logDir,{recursive:true});
const stamp=startedAt.toISOString().replaceAll(':','-').replaceAll('.','-');
const logPath=path.join(logDir,`final_stable_simulation_${stamp}.log`);fs.writeFileSync(logPath,log,'utf8');
process.stdout.write(log+`\nEVIDENCE_LOG=${logPath}\n`);
process.exitCode=results.every(({result})=>result.success&&/TEST_RESULT:\s*PASS/.test(result.combinedOutput))?0:1;
