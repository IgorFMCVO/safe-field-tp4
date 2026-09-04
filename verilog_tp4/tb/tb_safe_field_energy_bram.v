`timescale 1ns/1ps
module tb_safe_field_energy_bram;
reg clk=0,reset_n=0,power_valid=0;
reg [31:0] power_value=0;
reg [7:0] read_address=0;
wire [31:0] read_data,window_average;
wire window_valid;
wire [7:0] write_address;
integer i,checks=0,errors=0;
always #5 clk=~clk;
safe_field_energy_bram dut(.*);
task check; input [255:0] label; input [31:0] expected,actual;
begin checks=checks+1; if(expected!==actual) begin errors=errors+1;$display("FAIL %0s expected=%0d actual=%0d",label,expected,actual);end
else $display("PASS %0s expected=%0d actual=%0d",label,expected,actual);end endtask
initial begin
 $dumpfile("safe_field_energy_bram.vcd");$dumpvars(0,tb_safe_field_energy_bram);
 repeat(3)@(negedge clk);reset_n=1;
 for(i=0;i<256;i=i+1) begin @(negedge clk);power_valid=1;power_value=i;end
 @(negedge clk);power_valid=0; wait(window_valid);#1;
 check("average floor of 0..255",32'd127,window_average);
 read_address=8'd0; repeat(2)@(posedge clk);#1;check("BRAM address zero",32'd0,read_data);
 read_address=8'd123; repeat(2)@(posedge clk);#1;check("BRAM middle",32'd123,read_data);
 read_address=8'd255; repeat(2)@(posedge clk);#1;check("BRAM upper limit",32'd255,read_data);
 check("write pointer wrapped",32'd0,{24'd0,write_address});
 if(errors==0)$display("TEST_RESULT: PASS");else $display("TEST_RESULT: FAIL errors=%0d",errors);
 $display("checks=%0d errors=%0d",checks,errors);$finish;
end
endmodule
