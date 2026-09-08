`timescale 1ns/1ps

// Unit proof for the one intentional diagnostic difference: after inversion,
// WS=0 is ignored and WS=1 is accepted by the unchanged LEFT-only packet TX.
module tb_right_slot_selector;
reg clk = 1'b0;
reg reset_n = 1'b0;
reg signed [23:0] sample_data = 24'sd0;
reg sample_valid = 1'b0;
reg physical_channel = 1'b0;
wire uart_tx;
wire busy;
wire [31:0] accepted;
wire [31:0] dropped;
wire overrun;
integer i;
integer errors = 0;
integer timeout = 0;
always #5 clk = ~clk;

safe_field_pcm_packet_tx_gain8 #(.UART_CLKS_PER_BIT(4)) dut (
    .clk(clk), .reset_n(reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(~physical_channel),
    .frame_error(1'b0), .status_flags(6'd0), .uart_tx(uart_tx), .busy(busy),
    .accepted_sample_count(accepted), .dropped_sample_count(dropped),
    .overrun_latched(overrun)
);

task emit;
    input channel;
    input signed [23:0] value;
    begin
        @(negedge clk); physical_channel=channel; sample_data=value; sample_valid=1'b1;
        @(negedge clk); sample_valid=1'b0;
        repeat (80) @(negedge clk);
    end
endtask

initial begin
    repeat (8) @(posedge clk); reset_n=1'b1;
    emit(1'b0, 24'sh7fffff);
    if (accepted !== 0) begin
        $display("FAIL WS=0 was not ignored accepted=%0d", accepted); errors=errors+1;
    end
    for (i=0; i<32; i=i+1) emit(1'b1, (i-16) <<< 5);
    while (busy && timeout < 100000) begin @(posedge clk); timeout=timeout+1; end
    if (accepted !== 32 || dropped !== 0 || overrun !== 0) begin
        $display("FAIL right selection accepted=%0d dropped=%0d overrun=%0d", accepted,dropped,overrun);
        errors=errors+1;
    end
    if (timeout >= 100000) begin $display("FAIL timeout"); errors=errors+1; end
    if (errors == 0) $display("TEST_RESULT: PASS (WS=1 selected, WS=0 rejected, zero loss)");
    else $display("TEST_RESULT: FAIL errors=%0d", errors);
    $finish;
end
endmodule

