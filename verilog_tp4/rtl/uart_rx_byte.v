`timescale 1ns/1ps

// Oversampling-free UART RX. Samples start at half a bit and data/stop at the
// center of each following bit. RX is synchronized before use.
module uart_rx_byte #(
    parameter integer CLKS_PER_BIT = 234
) (
    input wire clk,
    input wire reset_n,
    input wire rx,
    output reg [7:0] data,
    output reg data_valid,
    output reg framing_error
);
localparam [1:0] ST_IDLE = 2'd0;
localparam [1:0] ST_START = 2'd1;
localparam [1:0] ST_DATA = 2'd2;
localparam [1:0] ST_STOP = 2'd3;
localparam integer HALF_BIT = CLKS_PER_BIT / 2;

reg rx_meta;
reg rx_sync;
reg [1:0] state;
reg [15:0] counter;
reg [2:0] bit_index;
reg [7:0] shift;

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        rx_meta <= 1'b1;
        rx_sync <= 1'b1;
    end else begin
        rx_meta <= rx;
        rx_sync <= rx_meta;
    end
end

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        state <= ST_IDLE;
        counter <= 16'd0;
        bit_index <= 3'd0;
        shift <= 8'd0;
        data <= 8'd0;
        data_valid <= 1'b0;
        framing_error <= 1'b0;
    end else begin
        data_valid <= 1'b0;
        framing_error <= 1'b0;
        case (state)
            ST_IDLE: if (!rx_sync) begin
                counter <= HALF_BIT - 1;
                state <= ST_START;
            end
            ST_START: if (counter == 0) begin
                if (!rx_sync) begin
                    counter <= CLKS_PER_BIT - 1;
                    bit_index <= 3'd0;
                    state <= ST_DATA;
                end else state <= ST_IDLE;
            end else counter <= counter - 1'b1;
            ST_DATA: if (counter == 0) begin
                shift[bit_index] <= rx_sync;
                counter <= CLKS_PER_BIT - 1;
                if (bit_index == 3'd7) state <= ST_STOP;
                else bit_index <= bit_index + 1'b1;
            end else counter <= counter - 1'b1;
            default: if (counter == 0) begin
                data <= shift;
                data_valid <= rx_sync;
                framing_error <= !rx_sync;
                state <= ST_IDLE;
            end else counter <= counter - 1'b1;
        endcase
    end
end
endmodule
