`timescale 1ns/1ps

// Continuous signed PCM transport for the SAFE-FIELD MVP.
//
// Protocol v1, fixed 78-byte UART frame (8-N-1):
//   0..1   sync A5 C3
//   2      version 01
//   3      type 20 (PCM_S16_LE)
//   4..5   packet sequence, little-endian
//   6..9   first sample counter, little-endian
//   10     sample count (32)
//   11     flags (bit0 frame error, bit1 overrun, bit2 RX LOW, bit3 GPIO17 HIGH)
//   12..75 32 signed PCM16 samples, little-endian
//   76..77 CRC-16/CCITT-FALSE over bytes 2..75, little-endian
//
// Two sample banks let acquisition continue while the preceding bank is sent.
module safe_field_pcm_packet_tx #(
    parameter integer UART_CLKS_PER_BIT = 18
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
    output reg  [31:0]         accepted_sample_count,
    output reg  [31:0]         dropped_sample_count,
    output reg                 overrun_latched
);
localparam integer BLOCK_SAMPLES = 32;
localparam [7:0] PROTOCOL_VERSION = 8'h01;
localparam [7:0] PACKET_TYPE_PCM16 = 8'h20;
localparam [6:0] LAST_BYTE_INDEX = 7'd77;

reg signed [15:0] sample_bank0 [0:BLOCK_SAMPLES-1];
reg signed [15:0] sample_bank1 [0:BLOCK_SAMPLES-1];
reg [1:0] bank_full;
reg write_bank;
reg read_bank;
reg [5:0] write_index;
reg [31:0] bank_first_counter0;
reg [31:0] bank_first_counter1;
reg [7:0] bank_flags0;
reg [7:0] bank_flags1;
reg frame_error_sticky;

reg packet_sending;
reg send_bank;
reg [6:0] byte_index;
reg [15:0] next_sequence;
reg [15:0] packet_sequence;
reg [31:0] packet_first_counter;
reg [7:0] packet_flags;
reg [15:0] packet_crc;
reg [7:0] uart_data;
reg signed [15:0] selected_sample;
wire uart_ready;
wire uart_busy;
wire left_sample = sample_valid && !sample_channel;
wire [6:0] payload_offset = byte_index - 7'd12;
wire [5:0] payload_sample_index = payload_offset[6:1];

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
    selected_sample = 16'sd0;
    if (byte_index >= 7'd12 && byte_index <= 7'd75) begin
        if (send_bank)
            selected_sample = sample_bank1[payload_sample_index];
        else
            selected_sample = sample_bank0[payload_sample_index];
    end

    if (byte_index == 7'd0) uart_data = 8'hA5;
    else if (byte_index == 7'd1) uart_data = 8'hC3;
    else if (byte_index == 7'd2) uart_data = PROTOCOL_VERSION;
    else if (byte_index == 7'd3) uart_data = PACKET_TYPE_PCM16;
    else if (byte_index == 7'd4) uart_data = packet_sequence[7:0];
    else if (byte_index == 7'd5) uart_data = packet_sequence[15:8];
    else if (byte_index == 7'd6) uart_data = packet_first_counter[7:0];
    else if (byte_index == 7'd7) uart_data = packet_first_counter[15:8];
    else if (byte_index == 7'd8) uart_data = packet_first_counter[23:16];
    else if (byte_index == 7'd9) uart_data = packet_first_counter[31:24];
    else if (byte_index == 7'd10) uart_data = 8'd32;
    else if (byte_index == 7'd11) uart_data = packet_flags;
    else if (byte_index >= 7'd12 && byte_index <= 7'd75)
        uart_data = payload_offset[0] ? selected_sample[15:8] : selected_sample[7:0];
    else if (byte_index == 7'd76) uart_data = packet_crc[7:0];
    else uart_data = packet_crc[15:8];
end

assign busy = packet_sending | uart_busy | (bank_full != 2'b00);

uart_tx_byte #(.CLKS_PER_BIT(UART_CLKS_PER_BIT)) byte_transmitter (
    .clk(clk),
    .reset_n(reset_n),
    .data(uart_data),
    .data_valid(packet_sending),
    .data_ready(uart_ready),
    .tx(uart_tx),
    .busy(uart_busy)
);

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        bank_full <= 2'b00;
        write_bank <= 1'b0;
        read_bank <= 1'b0;
        write_index <= 6'd0;
        bank_first_counter0 <= 32'd0;
        bank_first_counter1 <= 32'd0;
        bank_flags0 <= 8'd0;
        bank_flags1 <= 8'd0;
        frame_error_sticky <= 1'b0;
        packet_sending <= 1'b0;
        send_bank <= 1'b0;
        byte_index <= 7'd0;
        next_sequence <= 16'd0;
        packet_sequence <= 16'd0;
        packet_first_counter <= 32'd0;
        packet_flags <= 8'd0;
        packet_crc <= 16'hFFFF;
        accepted_sample_count <= 32'd0;
        dropped_sample_count <= 32'd0;
        overrun_latched <= 1'b0;
    end else begin
        if (frame_error)
            frame_error_sticky <= 1'b1;

        // Only LEFT samples are transported (INMP441 L/R is physically LOW).
        if (left_sample) begin
            if (!bank_full[write_bank]) begin
                if (write_bank)
                    sample_bank1[write_index] <= sample_data[23:8];
                else
                    sample_bank0[write_index] <= sample_data[23:8];

                if (write_index == 0) begin
                    if (write_bank)
                        bank_first_counter1 <= accepted_sample_count + dropped_sample_count;
                    else
                        bank_first_counter0 <= accepted_sample_count + dropped_sample_count;
                end

                accepted_sample_count <= accepted_sample_count + 1'b1;
                if (write_index == BLOCK_SAMPLES - 1) begin
                    bank_full[write_bank] <= 1'b1;
                    if (write_bank)
                        bank_flags1 <= {status_flags, overrun_latched, (frame_error_sticky | frame_error)};
                    else
                        bank_flags0 <= {status_flags, overrun_latched, (frame_error_sticky | frame_error)};
                    write_index <= 6'd0;
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

        if (!packet_sending) begin
            if (bank_full[read_bank] || bank_full[~read_bank]) begin
                if (!bank_full[read_bank])
                    send_bank <= ~read_bank;
                else
                    send_bank <= read_bank;

                if (bank_full[read_bank]) begin
                    packet_first_counter <= read_bank ? bank_first_counter1 : bank_first_counter0;
                    packet_flags <= read_bank ? bank_flags1 : bank_flags0;
                end else begin
                    packet_first_counter <= read_bank ? bank_first_counter0 : bank_first_counter1;
                    packet_flags <= read_bank ? bank_flags0 : bank_flags1;
                end
                packet_sequence <= next_sequence;
                next_sequence <= next_sequence + 1'b1;
                packet_crc <= 16'hFFFF;
                byte_index <= 7'd0;
                packet_sending <= 1'b1;
            end
        end else if (uart_ready) begin
            if (byte_index >= 7'd2 && byte_index <= 7'd75)
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
