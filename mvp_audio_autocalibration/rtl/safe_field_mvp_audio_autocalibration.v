`timescale 1ns/1ps

// Branch-only MVP variant. Frozen TP4 source files and bitstreams are not
// modified. Runtime detector parameters live only in FPGA SRAM/registers.
module safe_field_mvp_audio_autocalibration #(
    parameter integer POR_BITS = 8,
    parameter integer WINDOW_LOG2 = 8,
    parameter integer HALF_PERIOD_CLKS = 5,
    parameter integer UART_CLKS_PER_BIT = 234
) (
    input wire sys_clk,
    input wire pi_signal,
    input wire i2s_sd,
    input wire uart_rx,
    output wire i2s_sck,
    output wire i2s_ws,
    output wire led,
    output wire uart_tx
);
reg [POR_BITS-1:0] por_counter = {POR_BITS{1'b0}};
reg internal_reset_n = 1'b0;
always @(posedge sys_clk) begin
    if (por_counter != {POR_BITS{1'b1}}) begin
        por_counter <= por_counter + 1'b1;
        internal_reset_n <= 1'b0;
    end else internal_reset_n <= 1'b1;
end

wire capture_strobe;
wire [5:0] capture_bit_index;
wire signed [23:0] sample_data;
wire sample_valid;
wire sample_channel;
wire i2s_frame_error;
wire [23:0] magnitude;
wire frame_valid;
wire [23:0] energy;
wire energy_valid;
wire sound_active;
wire [5:0] vote_count;
wire gpio_led;

reg [23:0] cfg_threshold_on;
reg [23:0] cfg_threshold_off;
reg [5:0] cfg_k;
reg [5:0] cfg_n;
reg [7:0] cfg_attack;
reg [7:0] cfg_release;
reg [7:0] cfg_hangover;

i2s_clock_gen #(.HALF_PERIOD_CLKS(HALF_PERIOD_CLKS), .SLOT_BITS(32)) clock_master (
    .clk(sys_clk), .reset_n(internal_reset_n), .i2s_sck(i2s_sck), .i2s_ws(i2s_ws),
    .capture_strobe(capture_strobe), .capture_bit_index(capture_bit_index)
);
i2s_rx_24 receiver (
    .clk(sys_clk), .reset_n(internal_reset_n), .capture_strobe(capture_strobe),
    .capture_bit_index(capture_bit_index), .channel_ws(i2s_ws), .serial_data(i2s_sd),
    .sample_data(sample_data), .sample_valid(sample_valid),
    .sample_channel(sample_channel), .frame_error(i2s_frame_error)
);
audio_energy_detector_runtime #(.WINDOW_LOG2(WINDOW_LOG2)) detector (
    .clk(sys_clk), .reset_n(internal_reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(sample_channel),
    .threshold_on(cfg_threshold_on), .threshold_off(cfg_threshold_off),
    .cfg_k(cfg_k), .cfg_n(cfg_n), .attack_windows(cfg_attack),
    .release_windows(cfg_release), .hangover_windows(cfg_hangover),
    .magnitude(magnitude), .frame_valid(frame_valid), .energy(energy),
    .energy_valid(energy_valid), .sound_active(sound_active), .vote_count(vote_count)
);
rasp_to_tang gpio17_baseline (.pi_signal(pi_signal), .led(gpio_led));
assign led = gpio_led | sound_active;

wire command_valid;
wire [7:0] command_id;
wire [15:0] command_sequence;
wire [31:0] command_payload;
wire command_checksum_error;
wire command_framing_error;
safe_field_command_rx #(.UART_CLKS_PER_BIT(UART_CLKS_PER_BIT)) commands (
    .clk(sys_clk), .reset_n(internal_reset_n), .uart_rx(uart_rx),
    .command_valid(command_valid), .command_id(command_id),
    .command_sequence(command_sequence), .command_payload(command_payload),
    .checksum_error(command_checksum_error), .framing_error(command_framing_error)
);

reg command_job_pending;
reg signed [15:0] command_job_operand;
reg [15:0] command_job_sequence;
reg [7:0] command_job_id;
wire audio_dsp_valid = sample_valid && !sample_channel;
wire command_dsp_inject = command_job_pending && !audio_dsp_valid;
wire dsp_input_valid = audio_dsp_valid || command_dsp_inject;
wire signed [23:0] dsp_input_sample = command_dsp_inject ?
    {command_job_operand, 8'b0} : sample_data;
wire dsp_power_valid;
wire dsp_power_is_command;
wire [31:0] dsp_power;
safe_field_audio_energy_dsp power_dsp (
    .clk(sys_clk), .reset_n(internal_reset_n), .input_valid(dsp_input_valid),
    .input_is_command(command_dsp_inject), .sample_signed(dsp_input_sample),
    .result_valid(dsp_power_valid), .result_is_command(dsp_power_is_command),
    .sample_power(dsp_power)
);

reg [7:0] bram_read_address;
wire [31:0] bram_read_data;
wire [31:0] power_window_average;
wire power_window_valid;
wire [7:0] bram_write_address;
safe_field_energy_bram energy_buffer (
    .clk(sys_clk), .reset_n(internal_reset_n),
    .power_valid(dsp_power_valid && !dsp_power_is_command),
    .power_value(dsp_power), .read_address(bram_read_address),
    .read_data(bram_read_data), .window_average(power_window_average),
    .window_valid(power_window_valid), .write_address(bram_write_address)
);

reg response_pending;
reg [7:0] response_command;
reg [15:0] response_sequence;
reg [31:0] response_result;
reg response_error;
reg [1:0] bram_read_wait;
reg [7:0] bram_command_id;
reg [15:0] bram_command_sequence;
reg command_error_latched;
reg command_sequence_seen;
reg [15:0] last_command_sequence;

reg [31:0] frame_counter;
reg [WINDOW_LOG2-1:0] telemetry_window_count;
reg telemetry_pending;
reg telemetry_event_valid;
wire telemetry_event_ready;
reg telemetry_state;
reg [23:0] telemetry_energy;
reg [31:0] telemetry_frame_counter;
reg [7:0] telemetry_flags;
reg frame_error_latched;
reg sample_nonzero_latched;
reg telemetry_overrun_latched;

wire command_engine_busy = command_job_pending || (bram_read_wait != 0) || response_pending;
wire config_values_valid = (cfg_threshold_on > cfg_threshold_off) &&
    (cfg_k != 0) && (cfg_n != 0) && (cfg_n <= 32) && (cfg_k <= cfg_n);

always @(posedge sys_clk or negedge internal_reset_n) begin
    if (!internal_reset_n) begin
        cfg_threshold_on <= 24'd12000;
        cfg_threshold_off <= 24'd6000;
        cfg_k <= 6'd8;
        cfg_n <= 6'd24;
        cfg_attack <= 8'd1;
        cfg_release <= 8'd16;
        cfg_hangover <= 8'd82;
        command_job_pending <= 1'b0;
        command_job_operand <= 16'sd0;
        command_job_sequence <= 16'd0;
        command_job_id <= 8'd0;
        bram_read_address <= 8'd0;
        response_pending <= 1'b0;
        response_command <= 8'd0;
        response_sequence <= 16'd0;
        response_result <= 32'd0;
        response_error <= 1'b0;
        bram_read_wait <= 2'd0;
        bram_command_id <= 8'd0;
        bram_command_sequence <= 16'd0;
        command_error_latched <= 1'b0;
        command_sequence_seen <= 1'b0;
        last_command_sequence <= 16'd0;
        frame_counter <= 32'd0;
        telemetry_window_count <= {WINDOW_LOG2{1'b0}};
        telemetry_pending <= 1'b0;
        telemetry_event_valid <= 1'b0;
        telemetry_state <= 1'b0;
        telemetry_energy <= 24'd0;
        telemetry_frame_counter <= 32'd0;
        telemetry_flags <= 8'd0;
        frame_error_latched <= 1'b0;
        sample_nonzero_latched <= 1'b0;
        telemetry_overrun_latched <= 1'b0;
    end else begin
        if (telemetry_event_valid && telemetry_event_ready)
            telemetry_event_valid <= 1'b0;
        if (i2s_frame_error) frame_error_latched <= 1'b1;
        if (sample_valid && (sample_data != 0)) sample_nonzero_latched <= 1'b1;
        if (command_checksum_error || command_framing_error)
            command_error_latched <= 1'b1;

        if (frame_valid) begin
            frame_counter <= frame_counter + 1'b1;
            if (&telemetry_window_count) begin
                telemetry_window_count <= {WINDOW_LOG2{1'b0}};
                if (telemetry_pending) telemetry_overrun_latched <= 1'b1;
                else telemetry_pending <= 1'b1;
            end else telemetry_window_count <= telemetry_window_count + 1'b1;
        end

        if (command_dsp_inject) command_job_pending <= 1'b0;
        if (dsp_power_valid && dsp_power_is_command) begin
            response_pending <= 1'b1;
            response_command <= command_job_id;
            response_sequence <= command_job_sequence;
            response_result <= dsp_power;
            response_error <= 1'b0;
        end
        if (bram_read_wait != 0) begin
            bram_read_wait <= bram_read_wait - 1'b1;
            if (bram_read_wait == 1) begin
                response_pending <= 1'b1;
                response_command <= bram_command_id;
                response_sequence <= bram_command_sequence;
                response_result <= bram_read_data;
                response_error <= 1'b0;
            end
        end

        if (command_valid) begin
            if (command_sequence_seen && (command_sequence != last_command_sequence + 1'b1))
                command_error_latched <= 1'b1;
            command_sequence_seen <= 1'b1;
            last_command_sequence <= command_sequence;
            if (command_engine_busy) begin
                command_error_latched <= 1'b1;
            end else case (command_id)
                8'h01: begin
                    command_job_pending <= 1'b1;
                    command_job_operand <= command_payload[15:0];
                    command_job_sequence <= command_sequence;
                    command_job_id <= command_id;
                end
                8'h02: begin
                    bram_read_address <= command_payload[7:0];
                    bram_read_wait <= 2'd2;
                    bram_command_id <= command_id;
                    bram_command_sequence <= command_sequence;
                end
                8'h03: begin
                    response_pending <= 1'b1;
                    response_command <= command_id;
                    response_sequence <= command_sequence;
                    response_result <= power_window_average;
                    response_error <= 1'b0;
                end
                8'h10: begin
                    response_pending <= 1'b1;
                    response_command <= command_id;
                    response_sequence <= command_sequence;
                    response_result <= {8'd0, command_payload[23:0]};
                    response_error <= (command_payload[23:0] <= cfg_threshold_off);
                    if (command_payload[23:0] > cfg_threshold_off)
                        cfg_threshold_on <= command_payload[23:0];
                end
                8'h11: begin
                    response_pending <= 1'b1;
                    response_command <= command_id;
                    response_sequence <= command_sequence;
                    response_result <= {8'd0, command_payload[23:0]};
                    response_error <= (command_payload[23:0] >= cfg_threshold_on);
                    if (command_payload[23:0] < cfg_threshold_on)
                        cfg_threshold_off <= command_payload[23:0];
                end
                8'h12: begin
                    response_pending <= 1'b1;
                    response_command <= command_id;
                    response_sequence <= command_sequence;
                    response_result <= command_payload;
                    response_error <= (command_payload[5:0] == 0) ||
                        (command_payload[13:8] == 0) || (command_payload[13:8] > 32) ||
                        (command_payload[5:0] > command_payload[13:8]);
                    if ((command_payload[5:0] != 0) && (command_payload[13:8] != 0) &&
                        (command_payload[13:8] <= 32) &&
                        (command_payload[5:0] <= command_payload[13:8])) begin
                        cfg_k <= command_payload[5:0];
                        cfg_n <= command_payload[13:8];
                    end
                end
                8'h13: begin
                    cfg_attack <= command_payload[7:0];
                    response_pending <= 1'b1; response_command <= command_id;
                    response_sequence <= command_sequence; response_result <= command_payload;
                    response_error <= 1'b0;
                end
                8'h14: begin
                    cfg_release <= command_payload[7:0];
                    response_pending <= 1'b1; response_command <= command_id;
                    response_sequence <= command_sequence; response_result <= command_payload;
                    response_error <= 1'b0;
                end
                8'h15: begin
                    cfg_hangover <= command_payload[7:0];
                    response_pending <= 1'b1; response_command <= command_id;
                    response_sequence <= command_sequence; response_result <= command_payload;
                    response_error <= 1'b0;
                end
                8'h16: begin
                    response_pending <= 1'b1; response_command <= command_id;
                    response_sequence <= command_sequence;
                    response_result <= {cfg_k, cfg_n, cfg_attack, cfg_release, cfg_hangover[3:0]};
                    response_error <= !config_values_valid;
                end
                default: begin
                    response_pending <= 1'b1;
                    response_command <= command_id;
                    response_sequence <= command_sequence;
                    response_result <= 32'hFFFFFFFF;
                    response_error <= 1'b1;
                end
            endcase
        end

        if (!telemetry_event_valid) begin
            if (response_pending) begin
                telemetry_state <= sound_active;
                telemetry_energy <= {response_command, response_sequence};
                telemetry_frame_counter <= response_result;
                telemetry_flags <= {1'b1, response_error, command_error_latched,
                    1'b0, pi_signal, sample_nonzero_latched,
                    telemetry_overrun_latched, frame_error_latched};
                telemetry_event_valid <= 1'b1;
                response_pending <= 1'b0;
            end else if (telemetry_pending) begin
                telemetry_state <= sound_active;
                telemetry_energy <= energy;
                telemetry_frame_counter <= frame_counter;
                telemetry_flags <= {2'b00, command_error_latched, 1'b0,
                    pi_signal, sample_nonzero_latched,
                    telemetry_overrun_latched, frame_error_latched};
                telemetry_event_valid <= 1'b1;
                telemetry_pending <= 1'b0;
            end
        end
    end
end

safe_field_telemetry_tx #(.UART_CLKS_PER_BIT(UART_CLKS_PER_BIT)) telemetry (
    .clk(sys_clk), .reset_n(internal_reset_n),
    .event_valid(telemetry_event_valid), .event_ready(telemetry_event_ready),
    .event_state(telemetry_state), .event_energy(telemetry_energy),
    .event_frame_counter(telemetry_frame_counter), .event_flags(telemetry_flags),
    .uart_tx(uart_tx), .busy()
);
endmodule
