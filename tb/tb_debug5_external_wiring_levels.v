`timescale 1ns/1ps

module tb_debug5_external_wiring_levels;
integer checks;
integer errors;
integer cycle_count;
reg sys_clk;
reg pi_signal;
reg i2s_sd;
wire i2s_sck;
wire i2s_ws;
wire led;

debug5_external_wiring_levels #(
    .POR_BITS(2),
    .PHASE_CLKS(8)
) dut (
    .sys_clk(sys_clk),
    .pi_signal(pi_signal),
    .i2s_sd(i2s_sd),
    .i2s_sck(i2s_sck),
    .i2s_ws(i2s_ws),
    .led(led)
);

initial begin
    sys_clk = 1'b0;
    forever #5 sys_clk = ~sys_clk;
end

task check_value;
    input [8*64-1:0] label_text;
    input expected;
    input obtained;
    begin
        checks = checks + 1;
        if (obtained === expected)
            $display("PASS %-64s expected=%0d obtained=%0d", label_text, expected, obtained);
        else begin
            errors = errors + 1;
            $display("FAIL %-64s expected=%0d obtained=%0d", label_text, expected, obtained);
        end
    end
endtask

task check_complement;
    begin
        check_value("pin 42 WS is inverse of pin 41 SCK", 1'b1,
                    i2s_sck ^ i2s_ws);
    end
endtask

initial begin
    checks = 0;
    errors = 0;
    pi_signal = 1'b0;
    i2s_sd = 1'b0;
    $display("--- DEBUG5_EXTERNAL_WIRING_LEVELS ---");

    #1;
    check_value("initial pin 41 SCK LOW", 1'b0, i2s_sck);
    check_value("initial pin 42 WS HIGH", 1'b1, i2s_ws);
    check_value("initial LED follows LOW phase", 1'b0, led);
    check_complement;

    // Wait until the small simulation POR has completed.
    wait (dut.reset_n === 1'b1);
    @(negedge sys_clk);

    // The first phase must last eight complete enabled clock cycles.
    for (cycle_count = 0; cycle_count < 7; cycle_count = cycle_count + 1) begin
        @(posedge sys_clk);
        @(negedge sys_clk);
        check_value("SCK remains LOW before first boundary", 1'b0, i2s_sck);
        check_complement;
    end
    @(posedge sys_clk);
    @(negedge sys_clk);
    check_value("pin 41 SCK HIGH at first boundary", 1'b1, i2s_sck);
    check_value("pin 42 WS LOW at first boundary", 1'b0, i2s_ws);
    check_value("LED indicates HIGH phase", 1'b1, led);
    check_complement;

    // The second eight-cycle interval returns to the initial phase.
    repeat (8) @(posedge sys_clk);
    @(negedge sys_clk);
    check_value("pin 41 SCK LOW at second boundary", 1'b0, i2s_sck);
    check_value("pin 42 WS HIGH at second boundary", 1'b1, i2s_ws);
    check_value("LED returns to LOW phase", 1'b0, led);
    check_complement;

    // GPIO17 remains the validated independent HIGH override.
    pi_signal = 1'b1;
    #1;
    check_value("GPIO17 HIGH override preserved", 1'b1, led);
    pi_signal = 1'b0;

    // Exercise the pin-43 input path and check that it is sampled internally.
    i2s_sd = 1'b1;
    @(posedge sys_clk);
    @(negedge sys_clk);
    check_value("pin 43 input HIGH is observed internally", 1'b1,
                dut.i2s_sd_observed);
    i2s_sd = 1'b0;
    @(posedge sys_clk);
    @(negedge sys_clk);
    check_value("pin 43 input LOW is observed internally", 1'b0,
                dut.i2s_sd_observed);

    $display("checks=%0d errors=%0d", checks, errors);
    if (errors == 0) $display("TEST_RESULT: PASS");
    else $display("TEST_RESULT: FAIL");
    $finish;
end
endmodule
