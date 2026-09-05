`timescale 1ns/1ps

// Sustained-rate proof at the real clock ratios:
// one LEFT sample per 640 sys_clk cycles and UART divisor 18.
module tb_safe_field_pcm_sustained;
reg clk = 1'b0;
reg reset_n = 1'b0;
reg signed [23:0] sample_data = 24'sd0;
reg sample_valid = 1'b0;
wire uart_tx;
wire busy;
wire [31:0] accepted_sample_count;
wire [31:0] dropped_sample_count;
wire overrun_latched;
integer i;
integer timeout;
integer errors = 0;

always #5 clk = ~clk;

safe_field_pcm_packet_tx #(.UART_CLKS_PER_BIT(18)) dut (
    .clk(clk), .reset_n(reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(1'b0),
    .frame_error(1'b0), .status_flags(6'd0),
    .uart_tx(uart_tx), .busy(busy),
    .accepted_sample_count(accepted_sample_count),
    .dropped_sample_count(dropped_sample_count),
    .overrun_latched(overrun_latched)
);

initial begin
    repeat (8) @(posedge clk);
    reset_n = 1'b1;
    for (i = 0; i < 320; i = i + 1) begin
        @(negedge clk);
        sample_data = (i - 160) <<< 8;
        sample_valid = 1'b1;
        @(negedge clk);
        sample_valid = 1'b0;
        repeat (638) @(negedge clk);
    end

    timeout = 0;
    while (busy && timeout < 100000) begin
        @(posedge clk);
        timeout = timeout + 1;
    end
    if (timeout >= 100000) begin
        $display("FAIL sustained timeout");
        errors = errors + 1;
    end
    if (accepted_sample_count !== 320) begin
        $display("FAIL accepted expected=320 actual=%0d", accepted_sample_count);
        errors = errors + 1;
    end
    if (dropped_sample_count !== 0 || overrun_latched !== 0) begin
        $display("FAIL sustained loss dropped=%0d overrun=%0d",
                 dropped_sample_count, overrun_latched);
        errors = errors + 1;
    end
    if (dut.next_sequence !== 16'd10) begin
        $display("FAIL packets expected=10 actual=%0d", dut.next_sequence);
        errors = errors + 1;
    end
    if (errors == 0)
        $display("TEST_RESULT: PASS (320 samples, 10 packets, physical rate, zero overrun)");
    else
        $display("TEST_RESULT: FAIL errors=%0d", errors);
    $finish;
end
endmodule
