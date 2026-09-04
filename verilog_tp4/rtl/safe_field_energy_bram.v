`timescale 1ns/1ps

// Functional 256 x 32-bit audio-power buffer plus a block average. Memory is
// read synchronously and is not reset, matching dedicated BSRAM behavior.
module safe_field_energy_bram (
    input wire clk,
    input wire reset_n,
    input wire power_valid,
    input wire [31:0] power_value,
    input wire [7:0] read_address,
    output reg [31:0] read_data,
    output reg [31:0] window_average,
    output reg window_valid,
    output reg [7:0] write_address
) /* synthesis syn_ramstyle = "block_ram" */;
reg [31:0] memory [0:255] /* synthesis syn_ramstyle = "block_ram" */;
reg [39:0] window_sum;

always @(posedge clk) begin
    read_data <= memory[read_address];
    if (power_valid)
        memory[write_address] <= power_value;
end

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        write_address <= 8'd0;
        window_sum <= 40'd0;
        window_average <= 32'd0;
        window_valid <= 1'b0;
    end else begin
        window_valid <= 1'b0;
        if (power_valid) begin
            if (write_address == 8'hFF) begin
                window_average <= (window_sum + power_value) >> 8;
                window_sum <= 40'd0;
                write_address <= 8'd0;
                window_valid <= 1'b1;
            end else begin
                window_sum <= window_sum + power_value;
                write_address <= write_address + 1'b1;
            end
        end
    end
end
endmodule
