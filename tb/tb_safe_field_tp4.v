`timescale 1ns/1ps

module tb_safe_field_tp4;

integer errors;
integer checks;
reg clk;

initial begin
    clk = 1'b0;
    forever #5 clk = ~clk;
end

task check_value;
    input [8*48-1:0] label_text;
    input [31:0] expected;
    input [31:0] obtained;
    begin
        checks = checks + 1;
        if (obtained === expected)
            $display("PASS %-48s expected=%0d (0x%08h) obtained=%0d (0x%08h)",
                     label_text, expected, expected, obtained, obtained);
        else begin
            errors = errors + 1;
            $display("FAIL %-48s expected=%0d (0x%08h) obtained=%0d (0x%08h)",
                     label_text, expected, expected, obtained, obtained);
        end
    end
endtask

// -------------------------------------------------------------------------
// Clock generator checks
// -------------------------------------------------------------------------
reg clock_reset_n;
wire test_sck;
wire test_ws;
wire test_capture_strobe;
wire [5:0] test_capture_index;

i2s_clock_gen clock_dut (
    .clk(clk),
    .reset_n(clock_reset_n),
    .i2s_sck(test_sck),
    .i2s_ws(test_ws),
    .capture_strobe(test_capture_strobe),
    .capture_bit_index(test_capture_index)
);

integer edge_number;
time previous_edge_time;
time first_ws_edge_time;

task test_clock_generator;
    begin
        $display("--- CLOCK GENERATOR ---");
        clock_reset_n = 1'b0;
        repeat (3) @(negedge clk);
        clock_reset_n = 1'b1;

        @(posedge test_sck);
        previous_edge_time = $time;
        for (edge_number = 0; edge_number < 20; edge_number = edge_number + 1) begin
            @(test_sck);
            check_value("SCK half-period (5 sys_clk cycles)", 32'd50,
                        $time - previous_edge_time);
            previous_edge_time = $time;
        end

        @(posedge test_ws);
        first_ws_edge_time = $time;
        @(negedge test_ws);
        check_value("WS half-frame (32 SCK periods)", 32'd3200,
                    $time - first_ws_edge_time);
        @(posedge test_ws);
        check_value("WS full frame (64 SCK periods)", 32'd6400,
                    $time - first_ws_edge_time);
    end
endtask

// -------------------------------------------------------------------------
// Receiver checks with explicit I2S bit positions
// -------------------------------------------------------------------------
reg rx_reset_n;
reg rx_capture;
reg [5:0] rx_index;
reg rx_channel;
reg rx_sd;
wire signed [23:0] rx_sample;
wire rx_valid;
wire rx_sample_channel;
wire rx_frame_error;

i2s_rx_24 receiver_dut (
    .clk(clk),
    .reset_n(rx_reset_n),
    .capture_strobe(rx_capture),
    .capture_bit_index(rx_index),
    .channel_ws(rx_channel),
    .serial_data(rx_sd),
    .sample_data(rx_sample),
    .sample_valid(rx_valid),
    .sample_channel(rx_sample_channel),
    .frame_error(rx_frame_error)
);

task rx_pulse;
    input [5:0] index_value;
    input channel_value;
    input data_value;
    begin
        @(negedge clk);
        rx_index   = index_value;
        rx_channel = channel_value;
        rx_sd      = data_value;
        rx_capture = 1'b1;
        @(negedge clk);
        rx_capture = 1'b0;
    end
endtask

task send_slot;
    input channel_value;
    input [23:0] word_value;
    integer bit_position;
    begin
        rx_pulse(0, channel_value, 1'b0);
        for (bit_position = 23; bit_position >= 0; bit_position = bit_position - 1)
            rx_pulse(24 - bit_position, channel_value, word_value[bit_position]);
        for (bit_position = 25; bit_position <= 31; bit_position = bit_position + 1)
            rx_pulse(bit_position, channel_value, 1'b0);
    end
endtask

task test_receiver;
    begin
        $display("--- I2S RECEIVER ---");
        rx_reset_n = 1'b0;
        rx_capture = 1'b0;
        rx_index   = 6'd0;
        rx_channel = 1'b0;
        rx_sd      = 1'b0;
        repeat (3) @(negedge clk);
        rx_reset_n = 1'b1;

        send_slot(1'b0, 24'h123456);
        check_value("left channel signed sample", 32'h00123456,
                    {{8{rx_sample[23]}}, rx_sample});
        check_value("left channel tag", 32'd0, rx_sample_channel);

        send_slot(1'b1, 24'hFEDCBB);
        check_value("right channel negative sample", 32'hFFFEDCBB,
                    {{8{rx_sample[23]}}, rx_sample});
        check_value("right channel tag", 32'd1, rx_sample_channel);

        // A skipped bit index must raise the one-cycle framing error pulse.
        rx_reset_n = 1'b0;
        repeat (2) @(negedge clk);
        rx_reset_n = 1'b1;
        rx_pulse(0, 1'b0, 1'b0);
        rx_pulse(2, 1'b0, 1'b0);
        check_value("skipped I2S bit error", 32'd1, rx_frame_error);

        // A WS transition inside a slot is also malformed.
        rx_reset_n = 1'b0;
        repeat (2) @(negedge clk);
        rx_reset_n = 1'b1;
        rx_pulse(0, 1'b0, 1'b0);
        rx_pulse(1, 1'b1, 1'b0);
        check_value("mid-slot WS error", 32'd1, rx_frame_error);
    end
endtask

// -------------------------------------------------------------------------
// Magnitude, frame selection, moving energy and hysteresis FSM checks
// -------------------------------------------------------------------------
reg energy_reset_n;
reg signed [23:0] energy_sample;
reg energy_valid;
reg energy_channel;
wire [23:0] energy_magnitude;
wire energy_frame_valid;
wire [23:0] energy_average;
wire energy_active;

audio_energy_detector #(
    .WINDOW_LOG2(2),
    .THRESHOLD_ON(24'd1000),
    .THRESHOLD_OFF(24'd500)
) energy_dut (
    .clk(clk),
    .reset_n(energy_reset_n),
    .sample_data(energy_sample),
    .sample_valid(energy_valid),
    .sample_channel(energy_channel),
    .magnitude(energy_magnitude),
    .frame_valid(energy_frame_valid),
    .energy(energy_average),
    .sound_active(energy_active)
);

task energy_pulse;
    input channel_value;
    input signed [23:0] value;
    begin
        @(negedge clk);
        energy_channel = channel_value;
        energy_sample  = value;
        energy_valid   = 1'b1;
        @(negedge clk);
        energy_valid   = 1'b0;
    end
endtask

task send_energy_frame;
    input signed [23:0] left_value;
    input signed [23:0] right_value;
    begin
        energy_pulse(1'b0, left_value);
        energy_pulse(1'b1, right_value);
    end
endtask

task send_energy_window;
    input signed [23:0] left_value;
    input signed [23:0] right_value;
    integer frame_number;
    begin
        for (frame_number = 0; frame_number < 4; frame_number = frame_number + 1)
            send_energy_frame(left_value, right_value);
    end
endtask

task test_energy_detector;
    begin
        $display("--- ENERGY DETECTOR AND FSM ---");
        energy_reset_n = 1'b0;
        energy_sample  = 24'sd0;
        energy_valid   = 1'b0;
        energy_channel = 1'b0;
        repeat (3) @(negedge clk);
        energy_reset_n = 1'b1;

        send_energy_window(24'sd0, 24'sd0);
        check_value("silence average", 32'd0, energy_average);
        check_value("silence state QUIET", 32'd0, energy_active);

        send_energy_window(24'sd600, -24'sd200);
        check_value("below-on-threshold average", 32'd600, energy_average);
        check_value("below-on-threshold remains QUIET", 32'd0, energy_active);

        send_energy_window(-24'sd1500, 24'sd100);
        check_value("signal average uses absolute magnitude", 32'd1500,
                    energy_average);
        check_value("signal crosses threshold -> ACTIVE", 32'd1, energy_active);

        send_energy_window(24'sd700, -24'sd650);
        check_value("hysteresis-band average", 32'd700, energy_average);
        check_value("hysteresis holds ACTIVE", 32'd1, energy_active);

        send_energy_window(24'sd400, -24'sd100);
        check_value("below-off-threshold average", 32'd400, energy_average);
        check_value("below-off-threshold -> QUIET", 32'd0, energy_active);

        send_energy_window(24'sh800000, 24'sd0);
        check_value("most-negative boundary magnitude", 32'h00800000,
                    energy_average);
        check_value("boundary signal -> ACTIVE", 32'd1, energy_active);

        // Verify max(left,right) selection on an isolated frame.
        energy_reset_n = 1'b0;
        repeat (2) @(negedge clk);
        energy_reset_n = 1'b1;
        send_energy_frame(24'sd100, -24'sd200);
        check_value("frame max selects right magnitude", 32'd200,
                    energy_magnitude);
        check_value("one frame_valid pulse was generated", 32'd1,
                    energy_frame_valid);
    end
endtask

initial begin
    errors = 0;
    checks = 0;
    clock_reset_n  = 1'b0;
    rx_reset_n     = 1'b0;
    energy_reset_n = 1'b0;
    rx_capture     = 1'b0;
    energy_valid   = 1'b0;

    test_clock_generator;
    test_receiver;
    test_energy_detector;

    $display("--- SUMMARY ---");
    $display("checks=%0d errors=%0d", checks, errors);
    if (errors == 0)
        $display("TEST_RESULT: PASS");
    else
        $display("TEST_RESULT: FAIL");
    $finish;
end

endmodule
