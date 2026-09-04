import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { simulate } from '@veriflow/iverilog-wasm';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const started=new Date();
const base=['verilog_tp4/rtl/frozen_baseline/rasp_to_tang.v',
 'verilog_tp4/rtl/frozen_baseline/i2s_clock_gen.v',
 'verilog_tp4/rtl/frozen_baseline/i2s_rx_24.v',
 'verilog_tp4/rtl/frozen_baseline/audio_activity_fsm_persistent.v',
 'verilog_tp4/rtl/frozen_baseline/audio_energy_detector_persistent.v',
 'verilog_tp4/rtl/frozen_baseline/uart_tx_byte.v',
 'verilog_tp4/rtl/frozen_baseline/safe_field_telemetry_tx.v'];
const academic=['verilog_tp4/rtl/safe_field_audio_energy_dsp.v',
 'verilog_tp4/rtl/safe_field_energy_bram.v','verilog_tp4/rtl/uart_rx_byte.v',
 'verilog_tp4/rtl/safe_field_command_rx.v','verilog_tp4/rtl/safe_field_tp4_official.v'];
const tests=[
 ['dsp_arithmetic','safe_field_audio_energy_dsp.vcd',['verilog_tp4/rtl/safe_field_audio_energy_dsp.v','verilog_tp4/tb/tb_safe_field_audio_energy_dsp.v']],
 ['functional_bram','safe_field_energy_bram.vcd',['verilog_tp4/rtl/safe_field_energy_bram.v','verilog_tp4/tb/tb_safe_field_energy_bram.v']],
 ['uart_command_checksum','safe_field_command_rx.vcd',['verilog_tp4/rtl/uart_rx_byte.v','verilog_tp4/rtl/safe_field_command_rx.v','verilog_tp4/tb/tb_safe_field_command_rx.v']],
 ['integrated_audio_dsp_bram_uart','safe_field_tp4_official.vcd',[...base,...academic,'verilog_tp4/tb/tb_safe_field_tp4_official.v']],
];
const output=[];let pass=true;
const dir=path.join(root,'evidence','official_tp4');fs.mkdirSync(dir,{recursive:true});
const waveDir=path.join(dir,'waveforms');fs.mkdirSync(waveDir,{recursive:true});
for(const [name,vcd,sources] of tests){
 const files=sources.map(p=>({path:p,data:fs.readFileSync(path.join(root,p),'utf8')}));
 const r=await simulate({files,sources,generation:'2012',artifacts:[vcd],timeoutMs:120000});
 output.push(`===== TEST ${name} =====\nsuccess=${r.success}\nstage=${r.stage??'complete'}\n${r.combinedOutput}`);
 if(r.artifacts?.has(vcd))fs.writeFileSync(path.join(waveDir,vcd),r.artifacts.get(vcd));
 if(!r.success||!/TEST_RESULT:\s*PASS/.test(r.combinedOutput))pass=false;
}
const log=['SAFE-FIELD official TP4 rubric simulation',`started_utc=${started.toISOString()}`,
 `node=${process.version}`,'simulator=@veriflow/iverilog-wasm@0.1.4',...output].join('\n');
const stamp=started.toISOString().replaceAll(':','-').replaceAll('.','-');
const logPath=path.join(dir,`simulation_${stamp}.log`);fs.writeFileSync(logPath,log,'utf8');
process.stdout.write(`${log}\nEVIDENCE_LOG=${logPath}\n`);process.exitCode=pass?0:1;
