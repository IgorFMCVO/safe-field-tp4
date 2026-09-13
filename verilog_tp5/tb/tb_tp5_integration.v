`timescale 1ns/1ps
module tb_tp5_integration;
localparam CPB=16;
reg clk=0,pi_signal=0,i2s_sd=0,uart_rx=1;
wire i2s_sck,i2s_ws,led,uart_tx;
integer fails=0,transactions=0;
reg[7:0]rxbytes[0:11];always #5 clk=~clk;
safe_field_tp5_top #(.POR_BITS(3),.HALF_PERIOD_CLKS(2),.WINDOW_LOG2(2),
 .THRESHOLD_ON(24'd10),.THRESHOLD_OFF(24'd5),.ATTACK_WINDOWS(1),
 .RELEASE_WINDOWS(1),.UART_CLKS_PER_BIT(CPB))dut(
 .sys_clk(clk),.pi_signal(pi_signal),.i2s_sd(i2s_sd),.uart_rx(uart_rx),
 .i2s_sck(i2s_sck),.i2s_ws(i2s_ws),.led(led),.uart_tx(uart_tx));
function[7:0]crc8_next;
 input[7:0]current,inputv;integer k;reg[7:0]c;
 begin c=current^inputv;for(k=0;k<8;k=k+1)c=c[7]?((c<<1)^8'h07):(c<<1);crc8_next=c;end
endfunction
task send_byte;
 input[7:0]v;integer k;
 begin @(negedge clk);uart_rx=0;repeat(CPB)@(negedge clk);
 for(k=0;k<8;k=k+1)begin uart_rx=v[k];repeat(CPB)@(negedge clk);end
 uart_rx=1;repeat(CPB)@(negedge clk);end
endtask
task send_cmd;
 input[7:0]c;input[15:0]s;input[31:0]p;reg[7:0]cc;
 begin cc=0;cc=crc8_next(cc,8'h05);cc=crc8_next(cc,c);
 cc=crc8_next(cc,s[15:8]);cc=crc8_next(cc,s[7:0]);
 cc=crc8_next(cc,p[31:24]);cc=crc8_next(cc,p[23:16]);
 cc=crc8_next(cc,p[15:8]);cc=crc8_next(cc,p[7:0]);
 send_byte(8'hA6);send_byte(8'h6A);send_byte(8'h05);send_byte(c);
 send_byte(s[15:8]);send_byte(s[7:0]);send_byte(p[31:24]);
 send_byte(p[23:16]);send_byte(p[15:8]);send_byte(p[7:0]);send_byte(cc);end
endtask
task recv_byte;
 output[7:0]v;integer k;
 begin @(negedge uart_tx);
 // First data bit: 1.5 periods after start, not former 2.5-period offset.
 repeat(CPB+CPB/2)@(posedge clk);#1;
 for(k=0;k<8;k=k+1)begin v[k]=uart_tx;repeat(CPB)@(posedge clk);#1;end
 if(uart_tx!==1'b1)begin $display("FAIL stop bit");fails=fails+1;end
 end
endtask
task exchange;
 input[7:0]c;input[15:0]s;input[31:0]p,expected;input expected_error;
 integer j;reg[7:0]cc;
 begin
 fork send_cmd(c,s,p);begin for(j=0;j<12;j=j+1)recv_byte(rxbytes[j]);end join
 if(rxbytes[0]!==8'h5A||rxbytes[1]!==8'hA5||rxbytes[2]!==8'h05||rxbytes[3]!==c||{rxbytes[4],rxbytes[5]}!==s)begin
 $display("FAIL header/type/sequence seq=%h",s);fails=fails+1;end
 if({rxbytes[6],rxbytes[7],rxbytes[8],rxbytes[9]}!==expected)begin
 $display("FAIL payload seq=%h got=%h expected=%h",s,{rxbytes[6],rxbytes[7],rxbytes[8],rxbytes[9]},expected);fails=fails+1;end
 if(rxbytes[10][7]!==expected_error)begin $display("FAIL error flag");fails=fails+1;end
 cc=0;for(j=2;j<=10;j=j+1)cc=crc8_next(cc,rxbytes[j]);
 if(cc!==rxbytes[11])begin $display("FAIL response CRC");fails=fails+1;end
 transactions=transactions+1;repeat(CPB*2)@(posedge clk);
 end
endtask
initial begin #2000000;$fatal(1,"FAIL watchdog: incomplete UART transaction");end
initial begin
 $dumpfile("build/tb_tp5_integration.vcd");$dumpvars(0,tb_tp5_integration);
 repeat(20)@(negedge clk);pi_signal=1;#1;
 if(led!==1'b1)begin $display("FAIL GPIO17 observability");fails=fails+1;end
 @(negedge clk);pi_signal=0;
 exchange(8'h01,16'h0042,32'h0,32'h54503501,0);
 exchange(8'h10,16'h0043,32'h40004000,32'h00002000,0);
 exchange(8'h10,16'h0044,32'h80008000,32'h00007FFF,0);
 exchange(8'h11,16'h0045,32'h3E004000,32'h00004200,0);
 exchange(8'hEE,16'h0046,32'h0,32'hFFFFFFFF,1);
 exchange(8'h01,16'hFFFF,32'h0,32'h54503501,0);
 exchange(8'h01,16'h0000,32'h0,32'h54503501,0);
 exchange(8'h20,16'h0001,32'h0,32'd8,0);
 if(fails!=0)$fatal(1,"TEST_RESULT: FAIL integration failures=%0d",fails);
 $display("TEST_RESULT: PASS tp5_integration transactions=%0d",transactions);$finish;
end
endmodule
