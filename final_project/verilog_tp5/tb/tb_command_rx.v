`timescale 1ns/1ps
module tb_command_rx;
localparam CPB=16;
reg clk=0,reset_n=0,rx=1,ready=0;wire valid;wire[7:0]cmd;wire[15:0]seq;wire[31:0]payload;
wire crc_error,frame_error;integer fails=0,crc_count=0;always #5 clk=~clk;
always@(posedge clk)if(crc_error)crc_count=crc_count+1;
sf_command_rx #(.UART_CLKS_PER_BIT(CPB))dut(.clk(clk),.reset_n(reset_n),.uart_rx(rx),.command_ready(ready),.command_valid(valid),.command_id(cmd),.command_sequence(seq),.command_payload(payload),.checksum_error(crc_error),.framing_error(frame_error));
function[7:0]crc8_next;input[7:0]current,inputv;integer i;reg[7:0]c;
begin c=current^inputv;for(i=0;i<8;i=i+1)c=c[7]?((c<<1)^8'h07):(c<<1);crc8_next=c;end endfunction
task send_byte;input[7:0]v;integer i;
begin @(negedge clk);rx=0;repeat(CPB)@(negedge clk);for(i=0;i<8;i=i+1)begin rx=v[i];repeat(CPB)@(negedge clk);end rx=1;repeat(CPB)@(negedge clk);end endtask
task send_frame;input[7:0]c;input[15:0]s;input[31:0]p;input corrupt;reg[7:0]cc;
begin cc=0;cc=crc8_next(cc,8'h05);cc=crc8_next(cc,c);cc=crc8_next(cc,s[15:8]);cc=crc8_next(cc,s[7:0]);cc=crc8_next(cc,p[31:24]);cc=crc8_next(cc,p[23:16]);cc=crc8_next(cc,p[15:8]);cc=crc8_next(cc,p[7:0]);send_byte(8'hA6);send_byte(8'h6A);send_byte(8'h05);send_byte(c);send_byte(s[15:8]);send_byte(s[7:0]);send_byte(p[31:24]);send_byte(p[23:16]);send_byte(p[15:8]);send_byte(p[7:0]);send_byte(corrupt?(cc^8'h01):cc);end endtask
initial begin #1000000;$fatal(1,"FAIL command watchdog");end
initial begin
 $dumpfile("build/tb_command_rx.vcd");$dumpvars(0,tb_command_rx);
 repeat(4)@(negedge clk);reset_n=1;
 send_frame(8'h10,16'h1234,32'h40004000,0);repeat(8)@(negedge clk);
 if(!valid||cmd!==8'h10||seq!==16'h1234||payload!==32'h40004000)fails=fails+1;
 repeat(50)begin @(negedge clk);if(!valid||seq!==16'h1234)fails=fails+1;end
 ready=1;repeat(2)@(negedge clk);if(valid)fails=fails+1;ready=0;
 send_frame(8'h11,16'h1235,32'h3E004000,1);repeat(8)@(negedge clk);
 if(valid||crc_count!=1)begin $display("FAIL CRC rejection/count");fails=fails+1;end
 send_frame(8'h01,16'h1236,32'h00000000,0);repeat(8)@(negedge clk);
 if(!valid||seq!==16'h1236)begin $display("FAIL recovery after CRC");fails=fails+1;end
 if(fails!=0)$fatal(1,"TEST_RESULT: FAIL command_rx failures=%0d",fails);
 $display("TEST_RESULT: PASS command_rx hold+CRC+recovery");$finish;
end
endmodule
