`timescale 1ns/1ps

module tb_safe_field_tp4_gao;
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

safe_field_tp4_gao #(
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
            $display("PASS %-52s expected=%0d obtained=%0d", label_text, expected, obtained);
        else begin
            errors = errors + 1;
            $display("FAIL %-52s expected=%0d obtained=%0d", label_text, expected, obtained);
        end
    end
endtask

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
    model_right_word = 24'd0;

    @(posedge dut.internal_reset_n);
    wait_cycles = 0;
    while (dut.left_sample_count < 1 && wait_cycles < 20000) begin
        @(posedge sys_clk);
        wait_cycles = wait_cycles + 1;
    end
    @(negedge sys_clk);
    check_value("left sample counter advances", 32'd1, dut.left_sample_count);
    check_value("captured LEFT sample", 32'h00123456,
                {{8{dut.sample_data[23]}}, dut.sample_data});
    check_value("nonzero LEFT counter", 32'd1, dut.nonzero_left_count);
    check_value("zero LEFT counter initially", 32'd0, dut.zero_left_count);
    check_value("sample-valid event toggle", 32'd1, dut.sample_valid_toggle);
    check_value("raw SD transitions observed", 32'd1,
                (dut.sd_transition_count != 0));
    check_value("no frame errors", 32'd0, dut.frame_error_count);

    model_left_word = 24'd1500;
    wait_cycles = 0;
    while (!dut.sound_active && wait_cycles < 100000) begin
        @(posedge sys_clk);
        wait_cycles = wait_cycles + 1;
    end
    // Observe after nonblocking assignments from the detecting clock edge.
    @(negedge sys_clk);
    check_value("instrumented production FSM reaches ACTIVE", 32'd1,
                dut.sound_active);
    check_value("instrumentation preserves audio LED", 32'd1, led);
    check_value("energy update toggle changes", 32'd1,
                dut.energy_update_toggle);

    pi_signal = 1'b1;
    #1;
    check_value("GPIO17 HIGH override preserved", 32'd1, led);

    $display("--- GAO INSTRUMENTATION SUMMARY ---");
    $display("checks=%0d errors=%0d", checks, errors);
    if (errors == 0)
        $display("TEST_RESULT: PASS");
    else
        $display("TEST_RESULT: FAIL");
    $finish;
end
endmodule
