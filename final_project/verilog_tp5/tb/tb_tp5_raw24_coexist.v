`timescale 1ns/1ps
// Physical-ratio proof: a valid command is received while a 95-byte RAW24
// packet owns TX. The command response begins only after byte 94 and both CRCs
// are checked on the one physical UART line.
module tb_tp5_raw24_coexist;
 localparam CPB=18;reg clk=0,pi_signal=0,i2s_sd=0,uart_rx=1;wire i2s_sck,i2s_ws,led,uart_tx;integer fails=0,raw_bytes=0,response_bytes=0;reg[7:0]raw[0:94],resp[0:11];integer i;
 always #5 clk=~clk;
 safe_field_tp5_top #(.POR_BITS(3),.HALF_PERIOD_CLKS(5),.WINDOW_LOG2(2),.THRESHOLD_ON(24'd10),.THRESHOLD_OFF(24'd5),.ATTACK_WINDOWS(1),.RELEASE_WINDOWS(1),.UART_CLKS_PER_BIT(CPB)) dut(.sys_clk(clk),.pi_signal(pi_signal),.i2s_sd(i2s_sd),.uart_rx(uart_rx),.i2s_sck(i2s_sck),.i2s_ws(i2s_ws),.led(led),.uart_tx(uart_tx));
 function[7:0]crc8_next;input[7:0]current,value;integer k;reg[7:0]c;begin c=current^value;for(k=0;k<8;k=k+1)c=c[7]?((c<<1)^8'h07):(c<<1);crc8_next=c;end endfunction
 function[15:0]crc16_next;input[15:0]current;input[7:0]value;integer k;reg[15:0]c;begin c=current^{value,8'h00};for(k=0;k<8;k=k+1)c=c[15]?((c<<1)^16'h1021):(c<<1);crc16_next=c;end endfunction
 task send_byte;input[7:0]v;integer k;begin @(negedge clk);uart_rx=0;repeat(CPB)@(negedge clk);for(k=0;k<8;k=k+1)begin uart_rx=v[k];repeat(CPB)@(negedge clk);end uart_rx=1;repeat(CPB)@(negedge clk);end endtask
 task send_ping;reg[7:0]c;begin c=0;c=crc8_next(c,8'h05);c=crc8_next(c,8'h01);c=crc8_next(c,8'h12);c=crc8_next(c,8'h34);c=crc8_next(c,0);c=crc8_next(c,0);c=crc8_next(c,0);c=crc8_next(c,0);send_byte(8'ha6);send_byte(8'h6a);send_byte(8'h05);send_byte(8'h01);send_byte(8'h12);send_byte(8'h34);send_byte(0);send_byte(0);send_byte(0);send_byte(0);send_byte(c);end endtask
 task recv_byte;output[7:0]v;integer k;begin @(negedge uart_tx);repeat(CPB+CPB/2)@(posedge clk);#1;for(k=0;k<8;k=k+1)begin v[k]=uart_tx;repeat(CPB)@(posedge clk);#1;end if(uart_tx!==1)begin $display("FAIL stop bit");fails=fails+1;end end endtask
 task recv_raw;reg[15:0]c;begin recv_byte(raw[0]);recv_byte(raw[1]);for(i=2;i<95;i=i+1)recv_byte(raw[i]);raw_bytes=95;if(raw[0]!==8'ha5||raw[1]!==8'hc4||raw[2]!==8'h01||raw[3]!==8'h21||{raw[5],raw[4]}!==16'd0||raw[10]!==16||raw[11]!==2)begin $display("FAIL RAW24 header/sequence");fails=fails+1;end c=16'hffff;for(i=2;i<=92;i=i+1)c=crc16_next(c,raw[i]);if({raw[94],raw[93]}!==c)begin $display("FAIL RAW24 CRC");fails=fails+1;end end endtask
 task recv_response;reg[7:0]c;begin for(i=0;i<12;i=i+1)recv_byte(resp[i]);response_bytes=12;if(resp[0]!==8'h5a||resp[1]!==8'ha5||resp[2]!==8'h05||resp[3]!==8'h01||{resp[4],resp[5]}!==16'h1234||{resp[6],resp[7],resp[8],resp[9]}!==32'h54503501)begin $display("FAIL response contract");fails=fails+1;end c=0;for(i=2;i<=10;i=i+1)c=crc8_next(c,resp[i]);if(resp[11]!==c)begin $display("FAIL response CRC");fails=fails+1;end end endtask
 initial begin #10000000;$fatal(1,"FAIL coexist watchdog");end
 initial begin
 $dumpfile("build/tb_tp5_raw24_coexist.vcd");$dumpvars(0,tb_tp5_raw24_coexist);
  // First RAW packet starts after 32 left samples. Start one command inside it.
  wait(dut.raw_tx_active===1'b1);fork recv_raw();send_ping();join
  recv_response();
  if(raw_bytes!=95||response_bytes!=12||dut.raw24_transport.dropped_sample_count!=0)begin $display("FAIL coexist counters raw=%0d response=%0d drops=%0d",raw_bytes,response_bytes,dut.raw24_transport.dropped_sample_count);fails=fails+1;end
  if(fails!=0)$fatal(1,"TEST_RESULT: FAIL RAW24 coexist failures=%0d",fails);
  $display("TEST_RESULT: PASS RAW24 95-byte CRC frame + deferred TP5 PING response, no TX collision");$finish;
 end
 always@(posedge clk)if(dut.raw_tx_active&&dut.telemetry_busy)$fatal(1,"FAIL response transmitter overlapped RAW24 ownership");
endmodule
