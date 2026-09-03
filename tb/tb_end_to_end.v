`timescale 1ns/1ps

// End-to-end behavioral model: the testbench behaves like an INMP441 on SD
// while the FPGA top generates SCK/WS and processes the recovered audio.
module tb_end_to_end;

integer checks;
integer errors;
integer wait_cycles;
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

safe_field_tp4 #(
    .POR_BITS(3),
    .WINDOW_LOG2(2),
    .THRESHOLD_ON(24'd1000),
    .THRESHOLD_OFF(24'd500)
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
    input [8*52-1:0] label_text;
    input [31:0] expected;
    input [31:0] obtained;
    begin
        checks = checks + 1;
        if (obtained === expected)
            $display("PASS %-52s expected=%0d (0x%08h) obtained=%0d (0x%08h)",
                     label_text, expected, expected, obtained, obtained);
        else begin
            errors = errors + 1;
            $display("FAIL %-52s expected=%0d (0x%08h) obtained=%0d (0x%08h)",
                     label_text, expected, expected, obtained, obtained);
        end
    end
endtask

task wait_for_energy;
    input [23:0] expected_energy;
    begin
        wait_cycles = 0;
        while (dut.energy !== expected_energy && wait_cycles < 100000) begin
            @(posedge sys_clk);
            wait_cycles = wait_cycles + 1;
        end
        check_value("energy update reached before timeout", 32'd0,
                    (wait_cycles >= 100000));
        check_value("end-to-end energy", expected_energy, dut.energy);
    end
endtask

// INMP441 behavioral drive. SD changes on SCK falling edges and is stable for
// the FPGA's delayed sampling point in the following SCK-high interval.
initial begin
    i2s_sd          = 1'b0;
    model_ws        = 1'b0;
    model_bit_index = 0;

    wait (i2s_sck === 1'b1);
    forever begin
        @(negedge i2s_sck);

        if (i2s_ws != model_ws) begin
            model_ws        = i2s_ws;
            model_bit_index = 0;
        end else begin
            model_bit_index = model_bit_index + 1;
        end

        if (model_ws)
            selected_model_word = model_right_word;
        else
            selected_model_word = model_left_word;

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
    model_left_word  = 24'd0;
    model_right_word = 24'd0;

    $display("--- END-TO-END TOP ---");

    // Four complete quiet frames establish the first energy window.
    @(posedge dut.internal_reset_n);
    wait_for_energy(24'd0);
    check_value("silence leaves audio state QUIET", 32'd0, dut.sound_active);
    check_value("silence with GPIO17 LOW leaves LED off", 32'd0, led);

    // Exercise exact signed sample recovery through generated SCK/WS.
    model_left_word = 24'h123456;
    model_right_word = 24'd0;
    wait_cycles = 0;
    while (!(dut.sample_valid && !dut.sample_channel) && wait_cycles < 20000) begin
        @(posedge sys_clk);
        wait_cycles = wait_cycles + 1;
    end
    @(negedge sys_clk);
    check_value("left sample_valid reached before timeout", 32'd0,
                (wait_cycles >= 20000));
    check_value("generated-clock I2S sample recovery", 32'h00123456,
                {{8{dut.sample_data[23]}}, dut.sample_data});

    // Use a fresh constant window and verify the deterministic physical output.
    model_left_word = 24'd1500;
    model_right_word = 24'd0;
    wait_for_energy(24'd1500);
    check_value("signal drives FSM ACTIVE", 32'd1, dut.sound_active);
    check_value("audio event drives LED with GPIO17 LOW", 32'd1, led);

    model_left_word = 24'd0;
    model_right_word = 24'd0;
    wait_for_energy(24'd0);
    check_value("return to silence drives FSM QUIET", 32'd0, dut.sound_active);
    check_value("return to silence clears audio LED", 32'd0, led);
    check_value("well-formed stream has no frame error", 32'd0,
                dut.i2s_frame_error);

    // The physically validated Raspberry GPIO17 path remains a HIGH override.
    pi_signal = 1'b1;
    #1;
    check_value("GPIO17 HIGH override drives LED", 32'd1, led);
    pi_signal = 1'b0;
    #1;
    check_value("GPIO17 LOW returns control to quiet audio", 32'd0, led);

    $display("--- END-TO-END SUMMARY ---");
    $display("checks=%0d errors=%0d", checks, errors);
    if (errors == 0)
        $display("TEST_RESULT: PASS");
    else
        $display("TEST_RESULT: FAIL");
    $finish;
end

endmodule
