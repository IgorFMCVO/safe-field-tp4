`timescale 1ns/1ps

module tb_debug2_sd_transition_detect;
integer checks;
integer errors;
integer timeout_count;
integer toggle_divider;
reg sys_clk;
reg pi_signal;
reg i2s_sd;
reg toggle_enable;
wire i2s_sck;
wire i2s_ws;
wire led;

debug_sd_transition_detect #(
    .POR_BITS(2),
    .STARTUP_SCK_EDGES(4),
    .WINDOW_CLKS(64),
    .MIN_TRANSITIONS(4),
    .LED_HOLD_CLKS(32)
) dut (
    .sys_clk(sys_clk), .pi_signal(pi_signal), .i2s_sd(i2s_sd),
    .i2s_sck(i2s_sck), .i2s_ws(i2s_ws), .led(led)
);

initial begin
    sys_clk = 1'b0;
    forever #5 sys_clk = ~sys_clk;
end

always @(posedge sys_clk) begin
    if (toggle_enable) begin
        if (toggle_divider == 2) begin
            i2s_sd <= ~i2s_sd;
            toggle_divider <= 0;
        end else begin
            toggle_divider <= toggle_divider + 1;
        end
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
    toggle_divider = 0;
    toggle_enable = 1'b1;
    sys_clk = 1'b0;
    pi_signal = 1'b0;
    i2s_sd = 1'b0;
    $display("--- DEBUG 2 SD_TRANSITION_DETECT ---");

    wait (dut.reset_n === 1'b1);
    check_value("LED stays off during startup gate", 0, led);
    wait (dut.startup_done === 1'b1);

    while (led !== 1'b1 && timeout_count < 200) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    check_value("raw SD activity detected before timeout", 0, timeout_count >= 200);
    check_value("activity sets LED hold", 1, led);

    toggle_enable = 1'b0;
    repeat (20) @(posedge sys_clk);
    check_value("LED remains held after transitions stop", 1, led);

    timeout_count = 0;
    while (led !== 1'b0 && timeout_count < 100) begin
        @(posedge sys_clk);
        timeout_count = timeout_count + 1;
    end
    check_value("LED hold eventually expires", 0, timeout_count >= 100);
    check_value("LED returns OFF", 0, led);

    pi_signal = 1'b1;
    #1;
    check_value("GPIO17 HIGH override preserved", 1, led);

    $display("checks=%0d errors=%0d", checks, errors);
    if (errors == 0) $display("TEST_RESULT: PASS");
    else $display("TEST_RESULT: FAIL");
    $finish;
end
endmodule
