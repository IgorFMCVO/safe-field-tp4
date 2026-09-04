`timescale 1ns/1ps

module tb_debug6_acoustic_capture;
integer checks;
integer errors;
integer timeout_count;
integer decimated_edges;
reg sys_clk;
reg pi_signal;
reg i2s_sd;
wire i2s_sck;
wire i2s_ws;
wire led;
reg [23:0] model_left_word;
reg [23:0] model_right_word;
reg model_ws;
integer model_bit_index;
reg [23:0] selected_model_word;

debug6_acoustic_capture #(
    .POR_BITS(2),
    .HALF_PERIOD_CLKS(3),
    .VOICE_TRIGGER_MAGNITUDE(24'd32768)
) dut (
    .sys_clk(sys_clk), .pi_signal(pi_signal), .i2s_sd(i2s_sd),
    .i2s_sck(i2s_sck), .i2s_ws(i2s_ws), .led(led)
);

initial begin
    sys_clk = 1'b0;
    forever #5 sys_clk = ~sys_clk;
end

task check_value;
    input [8*64-1:0] label_text;
    input [31:0] expected;
    input [31:0] obtained;
    begin
        checks = checks + 1;
        if (obtained === expected)
            $display("PASS %-64s expected=%0d obtained=%0d", label_text,
                     expected, obtained);
        else begin
            errors = errors + 1;
            $display("FAIL %-64s expected=%0d obtained=%0d", label_text,
                     expected, obtained);
        end
    end
endtask

// INMP441-compatible I2S model: data changes on falling SCK and appears one
// clock after each WS edge. LEFT is WS=0 because physical L/R is tied to GND.
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
        selected_model_word = model_ws ? model_right_word : model_left_word;
        if (model_bit_index >= 1 && model_bit_index <= 24)
            i2s_sd = selected_model_word[24 - model_bit_index];
        else
            i2s_sd = 1'b0;
    end
end

always @(posedge dut.decimated_sample_clock)
    decimated_edges = decimated_edges + 1;

initial begin
    checks = 0;
    errors = 0;
    decimated_edges = 0;
    pi_signal = 1'b0;
    model_left_word = 24'h001000;
    model_right_word = 24'h000000;
    $display("--- DEBUG6_ACOUSTIC_CAPTURE ---");

    @(posedge dut.internal_reset_n);
    timeout_count = 0;
    while (dut.left_sample_count < 16 && timeout_count < 20000) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    @(negedge sys_clk);
    check_value("sixteen LEFT samples captured", 32'd16,
                dut.left_sample_count);
    check_value("decimator emits two capture clocks", 32'd2,
                decimated_edges);
    check_value("signed sample compression keeps 0x001000 >>> 10", 32'h00000004,
                {{18{dut.decimated_sample[13]}}, dut.decimated_sample});
    check_value("sub-threshold input leaves voice trigger LOW", 32'd0,
                dut.voice_trigger_level);
    check_value("no frame error latched", 32'd0, dut.frame_error_latched);
    check_value("LED remains LOW without audio trigger or GPIO17", 32'd0, led);

    model_left_word = 24'h010000;
    timeout_count = 0;
    while (!dut.voice_trigger_level && timeout_count < 10000) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    @(negedge sys_clk);
    check_value("above-threshold LEFT sample raises trigger", 32'd1,
                dut.voice_trigger_level);
    check_value("audio trigger is observable on LED", 32'd1, led);

    timeout_count = 0;
    while (dut.decimated_sample !== 14'sh0040 && timeout_count < 10000) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    @(negedge sys_clk);
    check_value("decimated voice sample equals 0x010000 >>> 10", 32'h00000040,
                {{18{dut.decimated_sample[13]}}, dut.decimated_sample});

    pi_signal = 1'b1;
    #1;
    check_value("GPIO17 HIGH override remains integrated", 32'd1, led);

    $display("checks=%0d errors=%0d left_samples=%0d decimated_edges=%0d",
             checks, errors, dut.left_sample_count, decimated_edges);
    if (errors == 0) $display("TEST_RESULT: PASS");
    else $display("TEST_RESULT: FAIL");
    $finish;
end
endmodule
