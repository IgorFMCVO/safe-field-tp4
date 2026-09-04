`timescale 1ns/1ps

module tb_debug3_nonzero_sample;
integer checks;
integer errors;
integer timeout_count;
reg sys_clk;
reg pi_signal;
reg i2s_sd;
wire i2s_sck;
wire i2s_ws;
wire led;
reg [23:0] model_left_word;
reg model_ws;
integer model_bit_index;

debug_nonzero_sample #(
    .POR_BITS(2),
    .SAMPLE_THRESHOLD(24'd512),
    .LED_HOLD_CLKS(24'd64)
) dut (
    .sys_clk(sys_clk), .pi_signal(pi_signal), .i2s_sd(i2s_sd),
    .i2s_sck(i2s_sck), .i2s_ws(i2s_ws), .led(led)
);

initial begin
    sys_clk = 1'b0;
    forever #5 sys_clk = ~sys_clk;
end

// LEFT INMP441 behavioral source; RIGHT slot is high-Z represented as zero.
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
    pi_signal = 1'b0;
    model_left_word = 24'd0;
    $display("--- DEBUG 3 NONZERO_SAMPLE ---");

    wait (dut.reset_n === 1'b1);
    while (dut.zero_sample_count < 2 && timeout_count < 3000) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    check_value("zero LEFT samples counted before timeout", 0, timeout_count >= 3000);
    check_value("zero sample counter advanced", 1, dut.zero_sample_count >= 2);
    check_value("no nonzero samples yet", 0, dut.nonzero_sample_count);
    check_value("zero samples below threshold leave LED off", 0, led);

    model_left_word = 24'd513;
    timeout_count = 0;
    while (led !== 1'b1 && timeout_count < 2000) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    @(negedge sys_clk);
    check_value("magnitude 513 detected before timeout", 0, timeout_count >= 2000);
    check_value("sample reconstructed exactly", 513, dut.sample_data);
    check_value("nonzero sample counter advanced", 1, dut.nonzero_sample_count >= 1);
    check_value("sample over 512 sets LED hold", 1, led);

    model_left_word = 24'd0;
    repeat (32) @(posedge sys_clk);
    check_value("LED remains held after triggering sample", 1, led);

    timeout_count = 0;
    while (led !== 1'b0 && timeout_count < 1000) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    check_value("LED hold expires after source returns zero", 0, timeout_count >= 1000);

    $display("DEBUG3_SAMPLE_COUNTS zero=%0d nonzero=%0d",
             dut.zero_sample_count, dut.nonzero_sample_count);
    $display("checks=%0d errors=%0d", checks, errors);
    if (errors == 0) $display("TEST_RESULT: PASS");
    else $display("TEST_RESULT: FAIL");
    $finish;
end
endmodule
