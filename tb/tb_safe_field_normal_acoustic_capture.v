`timescale 1ns/1ps
module tb_safe_field_normal_acoustic_capture;
integer checks, errors, timeout_count, left_samples, decimated_edges;
reg sys_clk, pi_signal, i2s_sd;
wire i2s_sck, i2s_ws, led;
reg [23:0] model_left_word, model_right_word, selected_model_word;
reg model_ws;
integer model_bit_index;
time edge_time;

safe_field_normal_acoustic_capture #(
    .POR_BITS(2), .WINDOW_LOG2(2), .HALF_PERIOD_CLKS(3),
    .DECIMATION_LOG2(2), .THRESHOLD_ON(24'd1000), .THRESHOLD_OFF(24'd500)
) dut (.sys_clk(sys_clk), .pi_signal(pi_signal), .i2s_sd(i2s_sd),
       .i2s_sck(i2s_sck), .i2s_ws(i2s_ws), .led(led));

initial begin sys_clk=0; forever #5 sys_clk=~sys_clk; end
task check_value;
 input [8*64-1:0] label_text; input [31:0] expected; input [31:0] obtained;
 begin checks=checks+1; if(obtained===expected)
   $display("PASS %-64s expected=%0d obtained=%0d",label_text,expected,obtained);
 else begin errors=errors+1; $display("FAIL %-64s expected=%0d obtained=%0d",label_text,expected,obtained); end end
endtask

initial begin
 i2s_sd=0; model_ws=0; model_bit_index=0; wait(i2s_sck===1'b1);
 forever begin
  @(negedge i2s_sck);
  if(i2s_ws!=model_ws) begin model_ws=i2s_ws; model_bit_index=0; end
  else model_bit_index=model_bit_index+1;
  selected_model_word=model_ws ? model_right_word : model_left_word;
  if(model_bit_index>=1 && model_bit_index<=24) i2s_sd=selected_model_word[24-model_bit_index];
  else i2s_sd=0;
 end
end
always @(posedge dut.sample_valid) if(!dut.sample_channel) left_samples=left_samples+1;
always @(posedge dut.decimated_sample_clock) decimated_edges=decimated_edges+1;

initial begin
 checks=0; errors=0; left_samples=0; decimated_edges=0; pi_signal=0;
 model_left_word=24'h001000; model_right_word=0;
 $display("--- SAFE_FIELD_NORMAL_ACOUSTIC_CAPTURE ---");
 @(posedge dut.internal_reset_n);
 @(posedge i2s_sck); edge_time=$time; @(posedge i2s_sck);
 check_value("SCK period is six simulation sys_clk cycles",60,$time-edge_time);
 timeout_count=0;
 while((left_samples<8 || decimated_edges<2) && timeout_count<40000) begin @(posedge sys_clk); timeout_count=timeout_count+1; end
 @(negedge sys_clk);
 check_value("eight LEFT samples reconstructed",8,left_samples);
 check_value("decimator-by-four emits two GAO clocks",2,decimated_edges);
 check_value("24-bit receiver feeds exact compressed sample",4,{{18{dut.decimated_sample[13]}},dut.decimated_sample});
 check_value("normal pipeline crosses simulated audio threshold",1,dut.sound_active);
 check_value("no I2S frame error latched",0,dut.frame_error_latched);
 check_value("audio ACTIVE drives LED",1,led);
 pi_signal=1; #1; check_value("GPIO17 override remains integrated",1,led);
 $display("checks=%0d errors=%0d left_samples=%0d decimated_edges=%0d",checks,errors,left_samples,decimated_edges);
 if(errors==0) $display("TEST_RESULT: PASS"); else $display("TEST_RESULT: FAIL");
 $finish;
end
endmodule
