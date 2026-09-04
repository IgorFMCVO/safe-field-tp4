`timescale 1ns/1ps
module tb_safe_field_mvp_hw_bridge;
reg sys_clk,pi_signal,i2s_sd;
wire i2s_sck,i2s_ws,led,uart_tx;
reg [23:0] model_left_word,model_right_word,selected_model_word;
reg model_ws;integer model_bit_index,checks,errors,timeout_count;

safe_field_mvp_hw_bridge #(
 .POR_BITS(2),.WINDOW_LOG2(2),.HALF_PERIOD_CLKS(3),
 .THRESHOLD_ON(24'd1000),.THRESHOLD_OFF(24'd500),
 .ATTACK_WINDOWS(2),.RELEASE_WINDOWS(3),.UART_CLKS_PER_BIT(4)
)dut(.sys_clk(sys_clk),.pi_signal(pi_signal),.i2s_sd(i2s_sd),
 .i2s_sck(i2s_sck),.i2s_ws(i2s_ws),.led(led),.uart_tx(uart_tx));

initial begin sys_clk=0;forever #5 sys_clk=~sys_clk;end
initial begin #5000000; $display("FAIL testbench timeout"); $display("TEST_RESULT: FAIL"); $finish; end
task check_value;input[8*56-1:0]label_text;input[31:0]expected;input[31:0]obtained;
 begin checks=checks+1;if(obtained===expected)$display("PASS %-56s expected=%0d obtained=%0d",label_text,expected,obtained);
 else begin errors=errors+1;$display("FAIL %-56s expected=%0d obtained=%0d",label_text,expected,obtained);end end
endtask

initial begin i2s_sd=0;model_ws=0;model_bit_index=0;wait(i2s_sck===1'b1);
 forever begin @(negedge i2s_sck);if(i2s_ws!=model_ws)begin model_ws=i2s_ws;model_bit_index=0;end
 else model_bit_index=model_bit_index+1;selected_model_word=model_ws?model_right_word:model_left_word;
 if(model_bit_index>=1&&model_bit_index<=24)i2s_sd=selected_model_word[24-model_bit_index];else i2s_sd=0;end
end

initial begin
 checks=0;errors=0;pi_signal=0;model_left_word=24'h001000;model_right_word=0;
 @(posedge dut.internal_reset_n);timeout_count=0;
 while(!dut.telemetry_event_valid&&timeout_count<200000)begin@(posedge sys_clk);timeout_count=timeout_count+1;end
 check_value("telemetry event follows real I2S frame counting",1,dut.telemetry_event_valid);
 check_value("captured LEFT sample is nonzero",1,dut.sample_nonzero_latched);
 check_value("valid I2S has no frame error",0,dut.i2s_frame_error);
 wait(uart_tx==1'b0);check_value("telemetry drives UART start bit LOW",0,uart_tx);
 timeout_count=0;while(!dut.sound_active&&timeout_count<300000)begin@(posedge sys_clk);timeout_count=timeout_count+1;end
 check_value("frozen audio pipeline reaches ACTIVE",1,dut.sound_active);
 check_value("ACTIVE continues to drive LED",1,led);
 pi_signal=1;#1;check_value("GPIO17 HIGH keeps baseline override",1,led);
 model_left_word=0;pi_signal=0;timeout_count=0;
 while(dut.sound_active&&timeout_count<500000)begin@(posedge sys_clk);timeout_count=timeout_count+1;end
 check_value("silence returns frozen pipeline to QUIET",0,dut.sound_active);
 check_value("GPIO17 LOW and QUIET clear LED",0,led);
 $display("checks=%0d errors=%0d",checks,errors);
 if(errors==0)$display("TEST_RESULT: PASS");else $display("TEST_RESULT: FAIL");$finish;
end
endmodule
