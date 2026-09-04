`timescale 1ns/1ps

// SAFE-FIELD telemetry protocol v1, fixed 16-byte frame, 8-N-1 UART.
// CRC-8/ATM (poly 0x07, init 0x00) covers bytes 2 through 14.
module safe_field_telemetry_tx #(
    parameter integer UART_CLKS_PER_BIT = 234
) (
    input wire clk,
    input wire reset_n,
    input wire event_valid,
    output wire event_ready,
    input wire event_state,
    input wire [23:0] event_energy,
    input wire [31:0] event_frame_counter,
    input wire [7:0] event_flags,
    output wire uart_tx,
    output wire busy
);
localparam [7:0] PROTOCOL_VERSION = 8'h01;
localparam [7:0] PAYLOAD_LENGTH = 8'h0B;

reg sending;
reg [3:0] byte_index;
reg [15:0] next_sequence;
reg [15:0] packet_sequence;
reg packet_state;
reg [23:0] packet_energy;
reg [31:0] packet_frame_counter;
reg [7:0] packet_flags;
reg [7:0] packet_crc;
reg [7:0] uart_data;
wire uart_ready;
wire uart_busy;

function [7:0] crc8_update;
    input [7:0] crc_in;
    input [7:0] data_in;
    integer i;
    reg [7:0] c;
    begin
        c = crc_in ^ data_in;
        for (i = 0; i < 8; i = i + 1)
            c = c[7] ? ((c << 1) ^ 8'h07) : (c << 1);
        crc8_update = c;
    end
endfunction

function [7:0] crc8_packet;
    input [15:0] seq;
    input state_value;
    input [23:0] energy_value;
    input [31:0] frame_value;
    input [7:0] flags_value;
    reg [7:0] c;
    begin
        c = 8'h00;
        c = crc8_update(c, PROTOCOL_VERSION);
        c = crc8_update(c, PAYLOAD_LENGTH);
        c = crc8_update(c, seq[7:0]);
        c = crc8_update(c, seq[15:8]);
        c = crc8_update(c, {7'd0, state_value});
        c = crc8_update(c, energy_value[7:0]);
        c = crc8_update(c, energy_value[15:8]);
        c = crc8_update(c, energy_value[23:16]);
        c = crc8_update(c, frame_value[7:0]);
        c = crc8_update(c, frame_value[15:8]);
        c = crc8_update(c, frame_value[23:16]);
        c = crc8_update(c, frame_value[31:24]);
        c = crc8_update(c, flags_value);
        crc8_packet = c;
    end
endfunction

always @* begin
    case (byte_index)
        4'd0: uart_data = 8'hA5;
        4'd1: uart_data = 8'h5A;
        4'd2: uart_data = PROTOCOL_VERSION;
        4'd3: uart_data = PAYLOAD_LENGTH;
        4'd4: uart_data = packet_sequence[7:0];
        4'd5: uart_data = packet_sequence[15:8];
        4'd6: uart_data = {7'd0, packet_state};
        4'd7: uart_data = packet_energy[7:0];
        4'd8: uart_data = packet_energy[15:8];
        4'd9: uart_data = packet_energy[23:16];
        4'd10: uart_data = packet_frame_counter[7:0];
        4'd11: uart_data = packet_frame_counter[15:8];
        4'd12: uart_data = packet_frame_counter[23:16];
        4'd13: uart_data = packet_frame_counter[31:24];
        4'd14: uart_data = packet_flags;
        default: uart_data = packet_crc;
    endcase
end

assign event_ready = ~sending;
assign busy = sending | uart_busy;

uart_tx_byte #(.CLKS_PER_BIT(UART_CLKS_PER_BIT)) byte_uart (
    .clk(clk), .reset_n(reset_n), .data(uart_data),
    .data_valid(sending), .data_ready(uart_ready),
    .tx(uart_tx), .busy(uart_busy)
);

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        sending <= 1'b0;
        byte_index <= 4'd0;
        next_sequence <= 16'd0;
        packet_sequence <= 16'd0;
        packet_state <= 1'b0;
        packet_energy <= 24'd0;
        packet_frame_counter <= 32'd0;
        packet_flags <= 8'd0;
        packet_crc <= 8'd0;
    end else if (!sending) begin
        if (event_valid) begin
            packet_sequence <= next_sequence;
            packet_state <= event_state;
            packet_energy <= event_energy;
            packet_frame_counter <= event_frame_counter;
            packet_flags <= event_flags;
            packet_crc <= crc8_packet(next_sequence, event_state, event_energy,
                                      event_frame_counter, event_flags);
            next_sequence <= next_sequence + 1'b1;
            byte_index <= 4'd0;
            sending <= 1'b1;
        end
    end else if (uart_ready) begin
        if (byte_index == 4'd15) begin
            sending <= 1'b0;
            byte_index <= 4'd0;
        end else begin
            byte_index <= byte_index + 1'b1;
        end
    end
end
endmodule
