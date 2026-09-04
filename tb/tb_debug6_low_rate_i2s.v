`timescale 1ns/1ps

module tb_debug6_low_rate_i2s;
integer checks;
integer errors;
integer edge_index;
integer timeout_count;
time previous_edge_time;
time ws_rise_time;
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

debug6_low_rate_i2s #(
    .POR_BITS(2),
    .HALF_PERIOD_CLKS(3)
) dut (
    .sys_clk(sys_clk), .pi_signal(pi_signal), .i2s_sd(i2s_sd),
    .i2s_sck(i2s_sck), .i2s_ws(i2s_ws), .led(led)
);

initial begin
    sys_clk = 1'b0;
    forever #5 sys_clk = ~sys_clk;
end

task check_value;
    input [8*60-1:0] label_text;
    input [31:0] expected;
    input [31:0] obtained;
    begin
        checks = checks + 1;
        if (obtained === expected)
            $display("PASS %-60s expected=%0d obtained=%0d", label_text,
                     expected, obtained);
        else begin
            errors = errors + 1;
            $display("FAIL %-60s expected=%0d obtained=%0d", label_text,
                     expected, obtained);
        end
    end
endtask

// Model an I2S transmitter: update SD on each falling SCK edge. Index zero is
// the one-bit I2S delay, followed by 24 data bits and seven padding bits.
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

initial begin
    checks = 0;
    errors = 0;
    pi_signal = 1'b0;
    model_left_word = 24'h123456;
    model_right_word = 24'hFEDCBA;
    $display("--- DEBUG6_LOW_RATE_I2S ---");

    @(posedge dut.internal_reset_n);

    // HALF_PERIOD_CLKS=3 in simulation gives a full SCK period of six clocks.
    @(posedge i2s_sck);
    previous_edge_time = $time;
    for (edge_index = 0; edge_index < 4; edge_index = edge_index + 1) begin
        @(posedge i2s_sck);
        check_value("SCK period is 6 sys_clk cycles", 32'd60,
                    $time - previous_edge_time);
        previous_edge_time = $time;
    end

    // 32 SCK periods per WS half-frame and 64 per full frame.
    @(posedge i2s_ws);
    ws_rise_time = $time;
    @(negedge i2s_ws);
    check_value("WS half-frame is 32 SCK periods", 32'd1920,
                $time - ws_rise_time);
    @(posedge i2s_ws);
    check_value("WS full frame is 64 SCK periods", 32'd3840,
                $time - ws_rise_time);

    timeout_count = 0;
    while (dut.left_sample_count < 2 && timeout_count < 2000) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    @(negedge sys_clk);
    check_value("at least two LEFT samples captured", 32'd1,
                dut.left_sample_count >= 2);
    check_value("decoded LEFT sample is exact", 32'h00123456,
                {{8{dut.sample_data[23]}}, dut.sample_data});
    check_value("nonzero LEFT counter advances", 32'd1,
                dut.nonzero_left_count >= 2);
    check_value("zero LEFT counter remains zero", 32'd0,
                dut.zero_left_count);
    check_value("raw SD transitions observed", 32'd1,
                dut.sd_transition_count != 0);
    check_value("no frame errors", 32'd0, dut.frame_error_count);
    check_value("nonzero sample drives diagnostic LED", 32'd1, led);

    pi_signal = 1'b1;
    #1;
    check_value("GPIO17 HIGH override preserved", 32'd1, led);

    $display("checks=%0d errors=%0d left=%0d zero=%0d nonzero=%0d sd_edges=%0d frame_errors=%0d",
             checks, errors, dut.left_sample_count, dut.zero_left_count,
             dut.nonzero_left_count, dut.sd_transition_count,
             dut.frame_error_count);
    if (errors == 0) $display("TEST_RESULT: PASS");
    else $display("TEST_RESULT: FAIL");
    $finish;
end
endmodule
