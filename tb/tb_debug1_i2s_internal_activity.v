`timescale 1ns/1ps

module tb_debug1_i2s_internal_activity;
integer checks;
integer errors;
integer timeout_count;
integer left_valid_count;
integer right_valid_count;
reg sys_clk;
reg pi_signal;
reg i2s_sd;
wire i2s_sck;
wire i2s_ws;
wire led;

debug_i2s_internal_activity #(
    .POR_BITS(2),
    .FRAMES_PER_HALF_PERIOD(2)
) dut (
    .sys_clk(sys_clk), .pi_signal(pi_signal), .i2s_sd(i2s_sd),
    .i2s_sck(i2s_sck), .i2s_ws(i2s_ws), .led(led)
);

initial begin
    sys_clk = 1'b0;
    forever #5 sys_clk = ~sys_clk;
end

always @(posedge sys_clk) begin
    if (dut.sample_valid) begin
        if (dut.sample_channel)
            right_valid_count = right_valid_count + 1;
        else
            left_valid_count = left_valid_count + 1;
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
    left_valid_count = 0;
    right_valid_count = 0;
    pi_signal = 1'b0;
    i2s_sd = 1'b0;
    $display("--- DEBUG 1 I2S_INTERNAL_ACTIVITY ---");

    while (led !== 1'b1 && timeout_count < 3000) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    check_value("frame-derived LED first half-period before timeout", 0,
                timeout_count >= 3000);
    check_value("LED toggled ON", 1, led);
    check_value("at least two LEFT samples advanced", 1, left_valid_count >= 2);
    check_value("at least two RIGHT samples completed frames", 1, right_valid_count >= 2);

    timeout_count = 0;
    while (led !== 1'b0 && timeout_count < 2000) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    check_value("frame-derived LED second half-period before timeout", 0,
                timeout_count >= 2000);
    check_value("LED toggled OFF", 0, led);

    pi_signal = 1'b1;
    #1;
    check_value("GPIO17 HIGH override preserved", 1, led);

    $display("DEBUG1_COUNTS left=%0d right=%0d", left_valid_count, right_valid_count);
    $display("checks=%0d errors=%0d", checks, errors);
    if (errors == 0) $display("TEST_RESULT: PASS");
    else $display("TEST_RESULT: FAIL");
    $finish;
end
endmodule
