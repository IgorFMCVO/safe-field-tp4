`timescale 1ns/1ps

module tb_debug4_low_threshold_audio;
integer checks;
integer errors;
integer timeout_count;
integer frame_count;
reg sys_clk;
reg pi_signal;
reg i2s_sd;
wire i2s_sck;
wire i2s_ws;
wire led;
reg [23:0] model_left_word;
reg model_ws;
integer model_bit_index;

debug_low_threshold_audio #(
    .POR_BITS(2),
    .WINDOW_LOG2(2)
) dut (
    .sys_clk(sys_clk), .pi_signal(pi_signal), .i2s_sd(i2s_sd),
    .i2s_sck(i2s_sck), .i2s_ws(i2s_ws), .led(led)
);

initial begin
    sys_clk = 1'b0;
    forever #5 sys_clk = ~sys_clk;
end

initial begin
    i2s_sd = 1'b0;
    model_ws = 1'b0;
    model_bit_index = 0;
    wait (i2s_sck === 1'b1);
    forever begin
        @(negedge i2s_sck);
        if (i2s_ws != model_ws) begin
            model_ws = i2s_ws;
            model_bit_index = 0;
        end else begin
            model_bit_index = model_bit_index + 1;
        end
        if (!model_ws && model_bit_index >= 1 && model_bit_index <= 24)
            i2s_sd = model_left_word[24 - model_bit_index];
        else
            i2s_sd = 1'b0;
    end
end

task check_value;
    input [8*52-1:0] label_text;
    input [31:0] expected;
    input [31:0] obtained;
    begin
        checks = checks + 1;
        if (obtained === expected)
            $display("PASS %-52s expected=%0d obtained=%0d", label_text, expected, obtained);
        else begin
            errors = errors + 1;
            $display("FAIL %-52s expected=%0d obtained=%0d", label_text, expected, obtained);
        end
    end
endtask

initial begin
    checks = 0;
    errors = 0;
    timeout_count = 0;
    frame_count = 0;
    pi_signal = 1'b0;
    model_left_word = 24'd0;
    $display("--- DEBUG 4 LOW_THRESHOLD_AUDIO ---");

    wait (dut.pipeline.internal_reset_n === 1'b1);
    while (frame_count < 4) begin
        @(posedge sys_clk);
        if (dut.pipeline.frame_valid)
            frame_count = frame_count + 1;
    end
    @(negedge sys_clk);
    check_value("silence keeps low-threshold pipeline off", 0, led);

    model_left_word = 24'd3000;
    while (led !== 1'b1 && timeout_count < 5000) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    check_value("3000 average crosses ON=2000 before timeout", 0,
                timeout_count >= 5000);
    check_value("low-threshold pipeline LED turns on", 1, led);

    model_left_word = 24'd0;
    timeout_count = 0;
    while (led !== 1'b0 && timeout_count < 5000) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    check_value("silence crosses OFF=1000 before timeout", 0,
                timeout_count >= 5000);
    check_value("low-threshold pipeline LED turns off", 0, led);

    $display("checks=%0d errors=%0d", checks, errors);
    if (errors == 0) $display("TEST_RESULT: PASS");
    else $display("TEST_RESULT: FAIL");
    $finish;
end
endmodule
