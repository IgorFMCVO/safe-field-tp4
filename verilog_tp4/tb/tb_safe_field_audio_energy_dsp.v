`timescale 1ns/1ps
module tb_safe_field_audio_energy_dsp;
reg clk=0, reset_n=0, input_valid=0, input_is_command=0;
reg signed [23:0] sample_signed=0;
wire result_valid, result_is_command;
wire [31:0] sample_power;
integer checks=0, errors=0;
always #5 clk=~clk;

safe_field_audio_energy_dsp dut(.*);

task check;
input [255:0] label; input [31:0] expected; input [31:0] actual;
begin checks=checks+1; if(expected!==actual) begin errors=errors+1; $display("FAIL %0s expected=%0d actual=%0d",label,expected,actual); end
else $display("PASS %0s expected=%0d actual=%0d",label,expected,actual); end
endtask

task apply;
input signed [15:0] value; input [31:0] expected; input [255:0] label;
begin
 @(negedge clk); sample_signed={value,8'b0}; input_valid=1; input_is_command=1;
 @(negedge clk); input_valid=0;
 wait(result_valid); #1; check(label,expected,sample_power); check("command tag",1,result_is_command);
end
endtask

initial begin
 $dumpfile("safe_field_audio_energy_dsp.vcd"); $dumpvars(0,tb_safe_field_audio_energy_dsp);
 repeat(3) @(negedge clk); reset_n=1;
 apply(16'sd0,32'd0,"zero squared");
 apply(16'sd123,32'd15129,"positive squared");
 apply(-16'sd123,32'd15129,"negative squared");
 apply(16'sd32767,32'd1073676289,"positive limit");
 apply(-16'sd32768,32'd1073741824,"negative limit without overflow");
 if(errors==0) $display("TEST_RESULT: PASS"); else $display("TEST_RESULT: FAIL errors=%0d",errors);
 $display("checks=%0d errors=%0d",checks,errors); $finish;
end
endmodule
