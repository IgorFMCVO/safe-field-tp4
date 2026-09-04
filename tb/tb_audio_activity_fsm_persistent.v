`timescale 1ns/1ps
module tb_audio_activity_fsm_persistent;
integer checks, errors, index;
reg clk, reset_n, energy_valid;
reg [23:0] energy;
wire sound_active;

audio_activity_fsm_persistent #(
 .THRESHOLD_ON(24'd12000), .THRESHOLD_OFF(24'd6000),
 .ATTACK_WINDOWS(4), .RELEASE_WINDOWS(7)
) dut (.clk(clk), .reset_n(reset_n), .energy_valid(energy_valid),
 .energy(energy), .sound_active(sound_active));

initial begin clk=0; forever #5 clk=~clk; end
task check_value; input [8*64-1:0] label_text; input expected; input obtained;
 begin checks=checks+1; if(obtained===expected) $display("PASS %-64s expected=%0d obtained=%0d",label_text,expected,obtained);
 else begin errors=errors+1; $display("FAIL %-64s expected=%0d obtained=%0d",label_text,expected,obtained); end end endtask
task feed; input [23:0] value;
 begin @(negedge clk); energy=value; energy_valid=1; @(posedge clk); #1; energy_valid=0; end endtask

initial begin
 checks=0; errors=0; reset_n=0; energy_valid=0; energy=0;
 repeat(2) @(posedge clk); reset_n=1; feed(24'd13000); feed(24'd13000);
 feed(24'd7000); feed(24'd13000); feed(24'd13000); feed(24'd13000);
 check_value("interruption resets attack persistence",0,sound_active);
 feed(24'd13000); check_value("fourth consecutive ON window enters ACTIVE",1,sound_active);
 for(index=0;index<6;index=index+1) feed(24'd5000);
 check_value("six OFF windows do not release M=7",1,sound_active);
 feed(24'd7000); check_value("deadband resets release persistence",1,sound_active);
 for(index=0;index<7;index=index+1) feed(24'd5000);
 check_value("seventh consecutive OFF window returns QUIET",0,sound_active);
 feed(24'd8000); check_value("hysteresis deadband preserves QUIET",0,sound_active);
 $display("checks=%0d errors=%0d",checks,errors);
 if(errors==0)$display("TEST_RESULT: PASS");else $display("TEST_RESULT: FAIL");$finish;
end
endmodule
