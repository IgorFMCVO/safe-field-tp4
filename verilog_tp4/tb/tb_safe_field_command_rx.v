`timescale 1ns/1ps
module tb_safe_field_command_rx;
localparam CPB=8;
reg clk=0,reset_n=0,uart_rx=1;
wire command_valid,checksum_error,framing_error;
wire [7:0] command_id;wire[15:0]command_sequence;wire[31:0]command_payload;
integer checks=0,errors=0,valid_count=0,error_count=0;
always #5 clk=~clk;
safe_field_command_rx #(.UART_CLKS_PER_BIT(CPB)) dut(.*);
function [7:0] crc8_update;input[7:0]c0;input[7:0]d;integer k;reg[7:0]c;begin c=c0^d;for(k=0;k<8;k=k+1)c=c[7]?((c<<1)^8'h07):(c<<1);crc8_update=c;end endfunction
task send_byte;input[7:0]b;integer j;begin uart_rx=0;repeat(CPB)@(posedge clk);for(j=0;j<8;j=j+1)begin uart_rx=b[j];repeat(CPB)@(posedge clk);end uart_rx=1;repeat(CPB)@(posedge clk);end endtask
task send_packet;input[7:0]cmd;input[15:0]seq;input[31:0]payload;input corrupt;reg[7:0]c;begin
 c=0;c=crc8_update(c,8'h01);c=crc8_update(c,cmd);c=crc8_update(c,seq[7:0]);c=crc8_update(c,seq[15:8]);c=crc8_update(c,payload[7:0]);c=crc8_update(c,payload[15:8]);c=crc8_update(c,payload[23:16]);c=crc8_update(c,payload[31:24]);
 send_byte(8'hA6);send_byte(8'h6A);send_byte(8'h01);send_byte(cmd);send_byte(seq[7:0]);send_byte(seq[15:8]);send_byte(payload[7:0]);send_byte(payload[15:8]);send_byte(payload[23:16]);send_byte(payload[31:24]);send_byte(c^(corrupt?8'h01:8'h00));
end endtask
task check;input[255:0]label;input[31:0]expected,actual;begin checks=checks+1;if(expected!==actual)begin errors=errors+1;$display("FAIL %0s expected=%0h actual=%0h",label,expected,actual);end else $display("PASS %0s expected=%0h actual=%0h",label,expected,actual);end endtask
always@(posedge clk)begin if(command_valid)begin valid_count=valid_count+1;case(valid_count)
1:begin check("vector1 command",1,command_id);check("vector1 sequence",16'h1001,command_sequence);check("vector1 payload",32'h0000007B,command_payload);end
2:begin check("vector2 negative",32'hFFFFFB2E,command_payload);end
3:begin check("vector3 limit",32'h00007FFF,command_payload);end endcase end if(checksum_error)error_count=error_count+1;end
initial begin
 $dumpfile("safe_field_command_rx.vcd");$dumpvars(0,tb_safe_field_command_rx);repeat(4)@(posedge clk);reset_n=1;repeat(2)@(posedge clk);
 send_packet(8'h01,16'h1001,32'h0000007B,0);send_packet(8'h01,16'h1002,32'hFFFFFB2E,0);send_packet(8'h01,16'h1003,32'h00007FFF,0);send_packet(8'h01,16'h1004,32'h12345678,1);repeat(30)@(posedge clk);
 check("three valid vectors",3,valid_count);check("bad checksum rejected",1,error_count);check("no framing error",0,framing_error);
 if(errors==0)$display("TEST_RESULT: PASS");else $display("TEST_RESULT: FAIL errors=%0d",errors);$display("checks=%0d errors=%0d",checks,errors);$finish;
end
endmodule
