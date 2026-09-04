`timescale 1ns/1ps
module tb_safe_field_stable_cued_capture;
integer checks, errors, timeout_count, left_samples, energy_edges;
integer active_sample_mark;
reg sys_clk, pi_signal, i2s_sd;
wire i2s_sck, i2s_ws, led;
reg [23:0] model_left_word, model_right_word, selected_model_word;
reg model_ws; integer model_bit_index;

safe_field_stable_cued_capture #(
 .POR_BITS(2), .WINDOW_LOG2(2), .HALF_PERIOD_CLKS(3),
 .THRESHOLD_ON(24'd1000), .THRESHOLD_OFF(24'd500),
 .ATTACK_WINDOWS(2), .RELEASE_WINDOWS(2), .MIN_ACTIVE_WINDOWS(4)
) dut (.sys_clk(sys_clk),.pi_signal(pi_signal),.i2s_sd(i2s_sd),
 .i2s_sck(i2s_sck),.i2s_ws(i2s_ws),.led(led));

initial begin sys_clk=0; forever #5 sys_clk=~sys_clk; end
task check_value; input [8*64-1:0] label_text; input [31:0] expected; input [31:0] obtained;
 begin checks=checks+1; if(obtained===expected) $display("PASS %-64s expected=%0d obtained=%0d",label_text,expected,obtained);
 else begin errors=errors+1; $display("FAIL %-64s expected=%0d obtained=%0d",label_text,expected,obtained); end end endtask

initial begin
 i2s_sd=0; model_ws=0; model_bit_index=0; wait(i2s_sck===1'b1);
 forever begin
  @(negedge i2s_sck);
  if(i2s_ws!=model_ws) begin model_ws=i2s_ws; model_bit_index=0; end
  else model_bit_index=model_bit_index+1;
  selected_model_word=model_ws?model_right_word:model_left_word;
  if(model_bit_index>=1&&model_bit_index<=24) i2s_sd=selected_model_word[24-model_bit_index]; else i2s_sd=0;
 end
end
always @(posedge dut.sample_valid) if(!dut.sample_channel) left_samples=left_samples+1;
always @(posedge dut.energy_capture_clock) energy_edges=energy_edges+1;

initial begin
 checks=0;errors=0;left_samples=0;energy_edges=0;pi_signal=0;
 model_left_word=24'h001000;model_right_word=0;
 $display("--- SAFE_FIELD_STABLE_CUED_CAPTURE ---"); @(posedge dut.internal_reset_n);
 timeout_count=0;
 while(!dut.sound_active&&timeout_count<200000) begin @(posedge sys_clk);timeout_count=timeout_count+1;end
 while(energy_edges<1&&timeout_count<200000) begin @(posedge sys_clk);timeout_count=timeout_count+1;end
 @(negedge sys_clk);
 check_value("two-window attack entered ACTIVE",1,dut.sound_active);
 check_value("receiver reconstructed LEFT samples",1,(left_samples>=8));
 check_value("GAO emitted completed-energy observations",1,(energy_edges>=1));
 check_value("completed energy observation is exact",256,dut.calibrated_energy_q);
 check_value("audio ACTIVE hidden from cue-only LED",0,led);
 active_sample_mark=left_samples;
 model_left_word=24'd0;
 timeout_count=0;
 while(dut.sound_active&&timeout_count<400000) begin @(posedge sys_clk);timeout_count=timeout_count+1;end
 @(negedge sys_clk);
 check_value("minimum hold plus qualified release returned QUIET",0,dut.sound_active);
 check_value("ACTIVE persisted for hold/release frame budget",1,((left_samples-active_sample_mark)>=20));
 check_value("no observation overflow",0,dut.energy_overflow);
 check_value("no frame error",0,dut.frame_error_latched);
 pi_signal=1; #1; check_value("GPIO17 marker drives cue-only LED",1,led);
 pi_signal=0; #1; check_value("GPIO17 LOW restores cue-only LED LOW",0,led);
 $display("checks=%0d errors=%0d",checks,errors);
 if(errors==0)$display("TEST_RESULT: PASS");else $display("TEST_RESULT: FAIL");$finish;
end
endmodule
