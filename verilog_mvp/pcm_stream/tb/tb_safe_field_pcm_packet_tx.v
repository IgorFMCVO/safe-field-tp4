`timescale 1ns/1ps

module tb_safe_field_pcm_packet_tx;
localparam integer CLKS_PER_BIT = 4;
reg clk = 1'b0;
reg reset_n = 1'b0;
reg signed [23:0] sample_data = 24'sd0;
reg sample_valid = 1'b0;
reg sample_channel = 1'b0;
reg frame_error = 1'b0;
wire uart_tx;
wire busy;
wire [31:0] accepted_sample_count;
wire [31:0] dropped_sample_count;
wire overrun_latched;
reg [7:0] received [0:155];
integer received_count = 0;
integer errors = 0;
integer i;
integer timeout;
reg [15:0] expected_crc;
reg [15:0] observed_crc;

always #5 clk = ~clk;

safe_field_pcm_packet_tx #(.UART_CLKS_PER_BIT(CLKS_PER_BIT)) dut (
    .clk(clk), .reset_n(reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(sample_channel),
    .frame_error(frame_error), .status_flags(6'd0),
    .uart_tx(uart_tx), .busy(busy),
    .accepted_sample_count(accepted_sample_count),
    .dropped_sample_count(dropped_sample_count),
    .overrun_latched(overrun_latched)
);

function [15:0] crc16_update;
    input [15:0] crc_in;
    input [7:0] data_in;
    integer n;
    reg [15:0] c;
    begin
        c = crc_in ^ {data_in, 8'h00};
        for (n = 0; n < 8; n = n + 1)
            c = c[15] ? ((c << 1) ^ 16'h1021) : (c << 1);
        crc16_update = c;
    end
endfunction

task emit_sample;
    input integer value;
    input channel;
    begin
        @(negedge clk);
        sample_data = value <<< 8;
        sample_channel = channel;
        sample_valid = 1'b1;
        @(negedge clk);
        sample_valid = 1'b0;
        repeat (78) @(negedge clk);
    end
endtask

task receive_uart_byte;
    integer bit_no;
    reg [7:0] value;
    begin
        @(negedge uart_tx);
        repeat (CLKS_PER_BIT + (CLKS_PER_BIT/2)) @(posedge clk);
        for (bit_no = 0; bit_no < 8; bit_no = bit_no + 1) begin
            value[bit_no] = uart_tx;
            repeat (CLKS_PER_BIT) @(posedge clk);
        end
        if (uart_tx !== 1'b1) begin
            $display("FAIL framing: stop bit was not HIGH at byte %0d", received_count);
            errors = errors + 1;
        end
        received[received_count] = value;
        received_count = received_count + 1;
        repeat (CLKS_PER_BIT/2) @(posedge clk);
    end
endtask

task check_packet;
    input integer base;
    input integer expected_sequence;
    input integer first_sample;
    integer k;
    integer signed decoded;
    begin
        if (received[base] !== 8'hA5 || received[base+1] !== 8'hC3) begin
            $display("FAIL sync packet %0d: got %02x %02x", expected_sequence,
                     received[base], received[base+1]);
            errors = errors + 1;
        end
        if (received[base+2] !== 8'h01 || received[base+3] !== 8'h20 ||
            received[base+10] !== 8'd32) begin
            $display("FAIL metadata packet %0d", expected_sequence);
            errors = errors + 1;
        end
        if ({received[base+5], received[base+4]} !== expected_sequence[15:0]) begin
            $display("FAIL sequence expected=%0d actual=%0d", expected_sequence,
                     {received[base+5], received[base+4]});
            errors = errors + 1;
        end
        if ({received[base+9], received[base+8], received[base+7], received[base+6]} !== first_sample) begin
            $display("FAIL counter expected=%0d actual=%0d", first_sample,
                     {received[base+9], received[base+8], received[base+7], received[base+6]});
            errors = errors + 1;
        end
        for (k = 0; k < 32; k = k + 1) begin
            decoded = $signed({received[base+13+(2*k)], received[base+12+(2*k)]});
            if (decoded !== (first_sample + k - 20)) begin
                $display("FAIL payload packet=%0d sample=%0d expected=%0d actual=%0d",
                         expected_sequence, k, first_sample + k - 20, decoded);
                errors = errors + 1;
            end
        end
        expected_crc = 16'hFFFF;
        for (k = 2; k <= 75; k = k + 1)
            expected_crc = crc16_update(expected_crc, received[base+k]);
        observed_crc = {received[base+77], received[base+76]};
        if (observed_crc !== expected_crc) begin
            $display("FAIL CRC packet=%0d expected=%04x actual=%04x",
                     expected_sequence, expected_crc, observed_crc);
            errors = errors + 1;
        end
    end
endtask

initial begin
    repeat (8) @(posedge clk);
    reset_n = 1'b1;

    fork
        begin
            // RIGHT samples must be ignored.
            emit_sample(999, 1'b1);
            for (i = 0; i < 64; i = i + 1)
                emit_sample(i - 20, 1'b0);
            while (received_count < 156)
                @(posedge clk);
        end
        begin
            while (received_count < 156)
                receive_uart_byte();
        end
        begin
            timeout = 0;
            while (received_count < 156 && timeout < 100000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (timeout >= 100000) begin
                $display("FAIL timeout: received %0d/156 bytes", received_count);
                $finish;
            end
        end
    join_any
    disable fork;

    if (received_count != 156) begin
        $display("FAIL byte count expected=156 actual=%0d", received_count);
        errors = errors + 1;
    end else begin
        check_packet(0, 0, 0);
        check_packet(78, 1, 32);
    end
    if (accepted_sample_count !== 64 || dropped_sample_count !== 0) begin
        $display("FAIL counters accepted=%0d dropped=%0d", accepted_sample_count,
                 dropped_sample_count);
        errors = errors + 1;
    end
    if (errors == 0)
        $display("TEST_RESULT: PASS (framing, payload, sequence, CRC, channel filter, no loss)");
    else
        $display("TEST_RESULT: FAIL errors=%0d", errors);
    $finish;
end
endmodule
