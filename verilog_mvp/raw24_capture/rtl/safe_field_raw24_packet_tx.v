`timescale 1ns/1ps

// Additive RAW_I2S_24_CAPTURE diagnostic transport.
//
// Fixed 95-byte UART frame, 8-N-1:
//   0..1    sync A5 C4
//   2       version 01
//   3       type 21 (RAW24_WITH_GAIN8_PCM16)
//   4..5    packet sequence, little-endian
//   6..9    source counter of first retained LEFT sample, little-endian
//   10      retained sample count (16)
//   11      source stride (2)
//   12      flags (bit0 frame error, bit1 overrun, bits7:2 status_flags)
//   13..92  16 pairs: signed RAW24 LE (3 bytes), signed PCM16 LE (2 bytes)
//   93..94  CRC-16/CCITT-FALSE over bytes 2..92, little-endian
//
// Every LEFT sample advances source_sample_counter. Source counters 0,2,4...
// are retained. Two banks permit acquisition while the previous frame is sent.
module safe_field_raw24_packet_tx #(
    parameter integer UART_CLKS_PER_BIT = 18,
    parameter integer PCM_ARITH_SHIFT = 5
) (
    input  wire               clk,
    input  wire               reset_n,
    input  wire signed [23:0] sample_data,
    input  wire               sample_valid,
    input  wire               sample_channel,
    input  wire               frame_error,
    input  wire [5:0]         status_flags,
    output wire               uart_tx,
    output wire               busy,
    output reg  [31:0]        source_sample_count,
    output reg  [31:0]        accepted_sample_count,
    output reg  [31:0]        dropped_sample_count,
    output reg                overrun_latched
);
localparam integer BLOCK_SAMPLES = 16;
localparam [7:0] PROTOCOL_VERSION = 8'h01;
localparam [7:0] PACKET_TYPE_RAW24 = 8'h21;
localparam [7:0] SOURCE_STRIDE = 8'd2;
localparam [6:0] LAST_BYTE_INDEX = 7'd94;

reg signed [23:0] raw_bank0 [0:BLOCK_SAMPLES-1];
reg signed [23:0] raw_bank1 [0:BLOCK_SAMPLES-1];
reg signed [15:0] pcm_bank0 [0:BLOCK_SAMPLES-1];
reg signed [15:0] pcm_bank1 [0:BLOCK_SAMPLES-1];
reg [1:0] bank_full;
reg write_bank;
reg read_bank;
reg [4:0] write_index;
reg [31:0] bank_first_counter0;
reg [31:0] bank_first_counter1;
reg [7:0] bank_flags0;
reg [7:0] bank_flags1;
reg frame_error_sticky;
reg decimation_phase;

reg packet_sending;
reg send_bank;
reg [6:0] byte_index;
reg [15:0] next_sequence;
reg [15:0] packet_sequence;
reg [31:0] packet_first_counter;
reg [7:0] packet_flags;
reg [15:0] packet_crc;
reg [7:0] uart_data;
reg signed [23:0] selected_raw24;
reg signed [15:0] selected_pcm16;
wire uart_ready;
wire uart_busy;
wire left_sample = sample_valid && !sample_channel;
wire retain_left_sample = left_sample && !decimation_phase;
wire signed [15:0] converted_pcm16;
wire [6:0] pair_payload_offset = byte_index - 7'd13;
wire [6:0] payload_sample_index_full = pair_payload_offset / 5;
wire [4:0] payload_sample_index = payload_sample_index_full[4:0];
wire [2:0] payload_byte_in_pair = pair_payload_offset % 5;

safe_field_pcm_s24_to_s16_sat #(.SHIFT(PCM_ARITH_SHIFT)) converter (
    .sample_in(sample_data),
    .sample_out(converted_pcm16)
);

function [15:0] crc16_update;
    input [15:0] crc_in;
    input [7:0] data_in;
    integer bit_number;
    reg [15:0] c;
    begin
        c = crc_in ^ {data_in, 8'h00};
        for (bit_number = 0; bit_number < 8; bit_number = bit_number + 1)
            c = c[15] ? ((c << 1) ^ 16'h1021) : (c << 1);
        crc16_update = c;
    end
endfunction

always @* begin
    selected_raw24 = 24'sd0;
    selected_pcm16 = 16'sd0;
    if (byte_index >= 7'd13 && byte_index <= 7'd92) begin
        if (send_bank) begin
            selected_raw24 = raw_bank1[payload_sample_index];
            selected_pcm16 = pcm_bank1[payload_sample_index];
        end else begin
            selected_raw24 = raw_bank0[payload_sample_index];
            selected_pcm16 = pcm_bank0[payload_sample_index];
        end
    end

    if (byte_index == 7'd0) uart_data = 8'hA5;
    else if (byte_index == 7'd1) uart_data = 8'hC4;
    else if (byte_index == 7'd2) uart_data = PROTOCOL_VERSION;
    else if (byte_index == 7'd3) uart_data = PACKET_TYPE_RAW24;
    else if (byte_index == 7'd4) uart_data = packet_sequence[7:0];
    else if (byte_index == 7'd5) uart_data = packet_sequence[15:8];
    else if (byte_index == 7'd6) uart_data = packet_first_counter[7:0];
    else if (byte_index == 7'd7) uart_data = packet_first_counter[15:8];
    else if (byte_index == 7'd8) uart_data = packet_first_counter[23:16];
    else if (byte_index == 7'd9) uart_data = packet_first_counter[31:24];
    else if (byte_index == 7'd10) uart_data = 8'd16;
    else if (byte_index == 7'd11) uart_data = SOURCE_STRIDE;
    else if (byte_index == 7'd12) uart_data = packet_flags;
    else if (byte_index >= 7'd13 && byte_index <= 7'd92) begin
        case (payload_byte_in_pair)
            3'd0: uart_data = selected_raw24[7:0];
            3'd1: uart_data = selected_raw24[15:8];
            3'd2: uart_data = selected_raw24[23:16];
            3'd3: uart_data = selected_pcm16[7:0];
            default: uart_data = selected_pcm16[15:8];
        endcase
    end else if (byte_index == 7'd93) uart_data = packet_crc[7:0];
    else uart_data = packet_crc[15:8];
end

assign busy = packet_sending | uart_busy | (bank_full != 2'b00);

uart_tx_byte #(.CLKS_PER_BIT(UART_CLKS_PER_BIT)) byte_transmitter (
    .clk(clk), .reset_n(reset_n), .data(uart_data),
    .data_valid(packet_sending), .data_ready(uart_ready),
    .tx(uart_tx), .busy(uart_busy)
);

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        bank_full <= 2'b00;
        write_bank <= 1'b0;
        read_bank <= 1'b0;
        write_index <= 5'd0;
        bank_first_counter0 <= 32'd0;
        bank_first_counter1 <= 32'd0;
        bank_flags0 <= 8'd0;
        bank_flags1 <= 8'd0;
        frame_error_sticky <= 1'b0;
        decimation_phase <= 1'b0;
        packet_sending <= 1'b0;
        send_bank <= 1'b0;
        byte_index <= 7'd0;
        next_sequence <= 16'd0;
        packet_sequence <= 16'd0;
        packet_first_counter <= 32'd0;
        packet_flags <= 8'd0;
        packet_crc <= 16'hFFFF;
        source_sample_count <= 32'd0;
        accepted_sample_count <= 32'd0;
        dropped_sample_count <= 32'd0;
        overrun_latched <= 1'b0;
    end else begin
        if (frame_error)
            frame_error_sticky <= 1'b1;

        if (left_sample) begin
            source_sample_count <= source_sample_count + 1'b1;
            decimation_phase <= ~decimation_phase;

            if (retain_left_sample) begin
                if (!bank_full[write_bank]) begin
                    if (write_bank) begin
                        raw_bank1[write_index] <= sample_data;
                        pcm_bank1[write_index] <= converted_pcm16;
                    end else begin
                        raw_bank0[write_index] <= sample_data;
                        pcm_bank0[write_index] <= converted_pcm16;
                    end

                    if (write_index == 0) begin
                        if (write_bank)
                            bank_first_counter1 <= source_sample_count;
                        else
                            bank_first_counter0 <= source_sample_count;
                    end

                    accepted_sample_count <= accepted_sample_count + 1'b1;
                    if (write_index == BLOCK_SAMPLES - 1) begin
                        bank_full[write_bank] <= 1'b1;
                        if (write_bank)
                            bank_flags1 <= {status_flags, overrun_latched,
                                            (frame_error_sticky | frame_error)};
                        else
                            bank_flags0 <= {status_flags, overrun_latched,
                                            (frame_error_sticky | frame_error)};
                        write_index <= 5'd0;
                        frame_error_sticky <= 1'b0;
                        overrun_latched <= 1'b0;
                        write_bank <= ~write_bank;
                    end else begin
                        write_index <= write_index + 1'b1;
                    end
                end else begin
                    dropped_sample_count <= dropped_sample_count + 1'b1;
                    overrun_latched <= 1'b1;
                end
            end
        end

        if (!packet_sending) begin
            if (bank_full[read_bank] || bank_full[~read_bank]) begin
                if (!bank_full[read_bank])
                    send_bank <= ~read_bank;
                else
                    send_bank <= read_bank;

                if (bank_full[read_bank]) begin
                    packet_first_counter <= read_bank ? bank_first_counter1
                                                      : bank_first_counter0;
                    packet_flags <= read_bank ? bank_flags1 : bank_flags0;
                end else begin
                    packet_first_counter <= read_bank ? bank_first_counter0
                                                      : bank_first_counter1;
                    packet_flags <= read_bank ? bank_flags0 : bank_flags1;
                end
                packet_sequence <= next_sequence;
                next_sequence <= next_sequence + 1'b1;
                packet_crc <= 16'hFFFF;
                byte_index <= 7'd0;
                packet_sending <= 1'b1;
            end
        end else if (uart_ready) begin
            if (byte_index >= 7'd2 && byte_index <= 7'd92)
                packet_crc <= crc16_update(packet_crc, uart_data);

            if (byte_index == LAST_BYTE_INDEX) begin
                packet_sending <= 1'b0;
                bank_full[send_bank] <= 1'b0;
                read_bank <= ~send_bank;
                byte_index <= 7'd0;
            end else begin
                byte_index <= byte_index + 1'b1;
            end
        end
    end
end
endmodule
