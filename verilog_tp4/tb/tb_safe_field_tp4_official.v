`timescale 1ns/1ps
module tb_safe_field_tp4_official;
localparam CPB=4;
reg sys_clk=0,pi_signal=0,i2s_sd=0,uart_rx=1;
wire i2s_sck,i2s_ws,led,uart_tx;
reg[23:0]model_left_word=24'h001000,model_right_word=0,selected_model_word;
reg model_ws=0;integer model_bit_index=0,checks=0,errors=0,timeout_count;
always #5 sys_clk=~sys_clk;
safe_field_tp4_official #(.POR_BITS(2),.WINDOW_LOG2(2),.HALF_PERIOD_CLKS(3),
 .THRESHOLD_ON(24'd1000),.THRESHOLD_OFF(24'd500),.ATTACK_WINDOWS(2),
 .RELEASE_WINDOWS(3),.UART_CLKS_PER_BIT(CPB)) dut(.*);
initial begin #10000000;$display("FAIL timeout");$display("TEST_RESULT: FAIL");$finish;end
task check;input[8*60-1:0]label;input[31:0]expected,actual;begin checks=checks+1;if(expected!==actual)begin errors=errors+1;$display("FAIL %-60s expected=%0d actual=%0d",label,expected,actual);end else $display("PASS %-60s expected=%0d actual=%0d",label,expected,actual);end endtask
function[7:0]crc8_update;input[7:0]c0;input[7:0]d;integer k;reg[7:0]c;begin c=c0^d;for(k=0;k<8;k=k+1)c=c[7]?((c<<1)^8'h07):(c<<1);crc8_update=c;end endfunction
task send_byte;input[7:0]b;integer j;begin uart_rx=0;repeat(CPB)@(posedge sys_clk);for(j=0;j<8;j=j+1)begin uart_rx=b[j];repeat(CPB)@(posedge sys_clk);end uart_rx=1;repeat(CPB)@(posedge sys_clk);end endtask
task send_command;input[15:0]seq;input signed[15:0]operand;reg[31:0]p;reg[7:0]c;begin
 p={{16{operand[15]}},operand};c=0;c=crc8_update(c,8'h01);c=crc8_update(c,8'h01);c=crc8_update(c,seq[7:0]);c=crc8_update(c,seq[15:8]);c=crc8_update(c,p[7:0]);c=crc8_update(c,p[15:8]);c=crc8_update(c,p[23:16]);c=crc8_update(c,p[31:24]);
 send_byte(8'hA6);send_byte(8'h6A);send_byte(8'h01);send_byte(8'h01);send_byte(seq[7:0]);send_byte(seq[15:8]);send_byte(p[7:0]);send_byte(p[15:8]);send_byte(p[23:16]);send_byte(p[31:24]);send_byte(c);
end endtask
task await_response;input[15:0]seq;input[31:0]expected;begin
 @(negedge sys_clk);timeout_count=0;
 while(!(dut.telemetry_event_valid&&dut.telemetry_event_ready&&dut.telemetry_flags[7]&&dut.telemetry_energy[15:0]==seq)&&timeout_count<200000)begin@(negedge sys_clk);timeout_count=timeout_count+1;end
 check("response event observed",1,(timeout_count<200000));check("response sequence echoed",seq,dut.telemetry_energy[15:0]);check("DSP result returned",expected,dut.telemetry_frame_counter);check("response error clear",0,dut.telemetry_flags[6]);
end endtask
initial begin wait(i2s_sck===1'b1);forever begin @(negedge i2s_sck);if(i2s_ws!=model_ws)begin model_ws=i2s_ws;model_bit_index=0;end else model_bit_index=model_bit_index+1;selected_model_word=model_ws?model_right_word:model_left_word;if(model_bit_index>=1&&model_bit_index<=24)i2s_sd=selected_model_word[24-model_bit_index];else i2s_sd=0;end end
initial begin
 $dumpfile("safe_field_tp4_official.vcd");$dumpvars(0,tb_safe_field_tp4_official);
 @(posedge dut.internal_reset_n);
 timeout_count=0;while(!dut.power_window_valid&&timeout_count<500000)begin@(posedge sys_clk);timeout_count=timeout_count+1;end #1;
 check("real I2S power window completed",1,(timeout_count<500000));check("DSP power average for 0x001000",256,dut.power_window_average);check("frame error remains zero",0,dut.i2s_frame_error);
 send_command(16'h2001,16'sd123);await_response(16'h2001,32'd15129);
 send_command(16'h2002,-16'sd123);await_response(16'h2002,32'd15129);
 send_command(16'h2003,16'sd32767);await_response(16'h2003,32'd1073676289);
 check("baseline audio reaches ACTIVE",1,dut.sound_active);pi_signal=1;#1;check("GPIO17 override preserved",1,led);
 if(errors==0)$display("TEST_RESULT: PASS");else $display("TEST_RESULT: FAIL errors=%0d",errors);$display("checks=%0d errors=%0d",checks,errors);$finish;
end
endmodule
