import fs from 'node:fs'; import path from 'node:path'; import { fileURLToPath } from 'node:url'; import { simulate } from '@veriflow/iverilog-wasm';
const projectDir=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'); const startedAt=new Date();
const sources=['src/rasp_to_tang.v','src/i2s_clock_gen.v','src/i2s_rx_24.v','src/audio_energy_detector.v','src/safe_field_calibrated_cued_capture.v','tb/tb_safe_field_calibrated_cued_capture.v'];
const files=sources.map(p=>({path:p,data:fs.readFileSync(path.join(projectDir,p),'utf8')})); const result=await simulate({files,sources,generation:'2012',timeoutMs:120000});
const log=['SAFE-FIELD TP4 calibrated cued capture simulation',`started_utc=${startedAt.toISOString()}`,`success=${result.success}`,`stage=${result.stage??'complete'}`,result.combinedOutput].join('\n');
const logDir=path.join(projectDir,'evidence','physical','retest_after_contact_fix');fs.mkdirSync(logDir,{recursive:true});const stamp=startedAt.toISOString().replaceAll(':','-').replaceAll('.','-');const logPath=path.join(logDir,`calibrated_audio_simulation_${stamp}.log`);fs.writeFileSync(logPath,log,'utf8');process.stdout.write(log+`\nEVIDENCE_LOG=${logPath}\n`);process.exitCode=result.success&&/TEST_RESULT:\s*PASS/.test(result.combinedOutput)?0:1;


