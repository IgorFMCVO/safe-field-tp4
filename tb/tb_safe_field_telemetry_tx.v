`timescale 1ns/1ps
module tb_safe_field_telemetry_tx;
localparam integer CLKS_PER_BIT = 8;
reg clk, reset_n, event_valid, event_state;
reg [23:0] event_energy;
reg [31:0] event_frame_counter;
reg [7:0] event_flags;
wire event_ready, uart_tx, busy;
reg [7:0] captured [0:15];
integer checks, errors, i, bit_number;

safe_field_telemetry_tx #(.UART_CLKS_PER_BIT(CLKS_PER_BIT)) dut (
 .clk(clk),.reset_n(reset_n),.event_valid(event_valid),.event_ready(event_ready),
 .event_state(event_state),.event_energy(event_energy),
 .event_frame_counter(event_frame_counter),.event_flags(event_flags),
 .uart_tx(uart_tx),.busy(busy));

initial begin clk=0;forever #5 clk=~clk;end
initial begin #1000000; $display("FAIL testbench timeout"); $display("TEST_RESULT: FAIL"); $finish; end

function [7:0] crc8_update;
 input [7:0] crc_in; input [7:0] data_in; integer k; reg [7:0] c;
 begin c=crc_in^data_in;for(k=0;k<8;k=k+1)c=c[7]?((c<<1)^8'h07):(c<<1);crc8_update=c;end
endfunction

function [7:0] frame_crc;
 integer k; reg [7:0] c;
 begin c=0;for(k=2;k<=14;k=k+1)c=crc8_update(c,captured[k]);frame_crc=c;end
endfunction

task check_value;
 input [8*52-1:0] label_text; input [31:0] expected; input [31:0] obtained;
 begin checks=checks+1;if(obtained===expected)$display("PASS %-52s expected=%0d obtained=%0d",label_text,expected,obtained);
 else begin errors=errors+1;$display("FAIL %-52s expected=%0d obtained=%0d",label_text,expected,obtained);end end
endtask

task send_event;
 input state_value; input [23:0] energy_value; input [31:0] frame_value; input [7:0] flags_value;
 begin
  wait(event_ready);@(negedge clk);event_state=state_value;event_energy=energy_value;
  event_frame_counter=frame_value;event_flags=flags_value;event_valid=1;
  @(negedge clk);event_valid=0;
 end
endtask

task receive_byte;
 output [7:0] value;
 begin
  @(negedge uart_tx);repeat(CLKS_PER_BIT/2)@(posedge clk);#1;
  check_value("UART packet start bit",0,uart_tx);
  for(bit_number=0;bit_number<8;bit_number=bit_number+1)begin repeat(CLKS_PER_BIT)@(posedge clk);#1;value[bit_number]=uart_tx;end
  repeat(CLKS_PER_BIT)@(posedge clk);#1;check_value("UART packet stop bit",1,uart_tx);
 end
endtask

task receive_frame;
 begin for(i=0;i<16;i=i+1)receive_byte(captured[i]);end
endtask

task verify_common;
 input [15:0] expected_seq; input expected_state; input [23:0] expected_energy;
 input [31:0] expected_counter; input [7:0] expected_flags;
 begin
  check_value("sync byte 0",8'hA5,captured[0]);check_value("sync byte 1",8'h5A,captured[1]);
  check_value("protocol version",1,captured[2]);check_value("fixed payload length",11,captured[3]);
  check_value("sequence number",expected_seq,{captured[5],captured[4]});
  check_value("QUIET/ACTIVE state",expected_state,captured[6]);
  check_value("24-bit energy",expected_energy,{captured[9],captured[8],captured[7]});
  check_value("32-bit frame counter",expected_counter,{captured[13],captured[12],captured[11],captured[10]});
  check_value("error/status flags",expected_flags,captured[14]);
  check_value("CRC-8/ATM",frame_crc(),captured[15]);
 end
endtask

initial begin
 checks=0;errors=0;reset_n=0;event_valid=0;event_state=0;event_energy=0;event_frame_counter=0;event_flags=0;
 repeat(3)@(posedge clk);reset_n=1;@(posedge clk);
 send_event(0,24'h123456,32'h01020304,8'h01);receive_frame;
 verify_common(16'd0,0,24'h123456,32'h01020304,8'h01);
 send_event(1,24'hFEDCBA,32'h11223344,8'h05);receive_frame;
 verify_common(16'd1,1,24'hFEDCBA,32'h11223344,8'h05);
 check_value("sequence increments exactly once per packet",1,dut.packet_sequence);
 $display("checks=%0d errors=%0d",checks,errors);
 if(errors==0)$display("TEST_RESULT: PASS");else $display("TEST_RESULT: FAIL");$finish;
end
endmodule
