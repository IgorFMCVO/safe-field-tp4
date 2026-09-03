`timescale 1ns/1ps

// Receives the 24 significant bits from each 32-bit I2S channel slot.
// capture_bit_index=0 is the mandatory I2S one-clock delay; indices 1..24
// carry the 24-bit two's-complement sample, MSB first.
module i2s_rx_24 (
    input  wire               clk,
    input  wire               reset_n,
    input  wire               capture_strobe,
    input  wire [5:0]         capture_bit_index,
    input  wire               channel_ws,
    input  wire               serial_data,
    output reg signed [23:0]  sample_data,
    output reg                sample_valid,
    output reg                sample_channel,
    output reg                frame_error
);

reg [23:0] shift_register;
reg [5:0] expected_bit_index;
reg slot_channel;
reg synchronized;

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        shift_register     <= 24'd0;
        sample_data        <= 24'sd0;
        sample_valid       <= 1'b0;
        sample_channel     <= 1'b0;
        frame_error        <= 1'b0;
        expected_bit_index <= 6'd0;
        slot_channel       <= 1'b0;
        synchronized       <= 1'b0;
    end else begin
        sample_valid <= 1'b0;
        frame_error  <= 1'b0;

        if (capture_strobe) begin
            if (synchronized && capture_bit_index != expected_bit_index)
                frame_error <= 1'b1;

            synchronized <= 1'b1;
            if (capture_bit_index == 31)
                expected_bit_index <= 6'd0;
            else
                expected_bit_index <= capture_bit_index + 1'b1;

            if (capture_bit_index == 0) begin
                slot_channel <= channel_ws;
            end else if (channel_ws != slot_channel) begin
                // WS is required to remain constant throughout a channel slot.
                frame_error <= 1'b1;
            end

            if (capture_bit_index >= 1 && capture_bit_index <= 24) begin
                shift_register <= {shift_register[22:0], serial_data};

                if (capture_bit_index == 24) begin
                    sample_data    <= {shift_register[22:0], serial_data};
                    sample_channel <= slot_channel;
                    sample_valid   <= 1'b1;
                end
            end
        end
    end
end

endmodule
