`timescale 1ns/1ps

module tb_safe_field_pcm_packet_tx_gain8;
localparam integer CLKS_PER_BIT = 4;
reg clk = 1'b0;
reg reset_n = 1'b0;
reg signed [23:0] sample_data = 24'sd0;
reg sample_valid = 1'b0;
reg sample_channel = 1'b0;
wire uart_tx;
wire busy;
wire [31:0] accepted_sample_count;
wire [31:0] dropped_sample_count;
wire overrun_latched;
reg [7:0] received [0:77];
integer received_count = 0;
integer errors = 0;
integer i;
integer timeout;
integer signed decoded;
integer signed expected;
reg [15:0] expected_crc;
reg [15:0] observed_crc;

always #5 clk = ~clk;

safe_field_pcm_packet_tx_gain8 #(.UART_CLKS_PER_BIT(CLKS_PER_BIT)) dut (
    .clk(clk), .reset_n(reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(sample_channel),
    .frame_error(1'b0), .status_flags(6'b001001),
    .uart_tx(uart_tx), .busy(busy),
    .accepted_sample_count(accepted_sample_count),
    .dropped_sample_count(dropped_sample_count),
    .overrun_latched(overrun_latched)
);

function signed [23:0] stimulus;
    input integer index;
    begin
        case (index)
            0: stimulus = 24'sd0;
            1: stimulus = 24'sd32;
            2: stimulus = -24'sd32;
            3: stimulus = 24'sd1048575;
            4: stimulus = -24'sd1048576;
            5: stimulus = 24'sh7FFFFF;
            6: stimulus = 24'sh800000;
            default: stimulus = (index - 16) <<< 5;
        endcase
    end
endfunction

function signed [15:0] expected_sample;
    input integer index;
    begin
        case (index)
            0: expected_sample = 16'sd0;
            1: expected_sample = 16'sd1;
            2: expected_sample = -16'sd1;
            3: expected_sample = 16'sd32767;
            4: expected_sample = -16'sd32768;
            5: expected_sample = 16'sd32767;
            6: expected_sample = -16'sd32768;
            default: expected_sample = index - 16;
        endcase
    end
endfunction

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
    input signed [23:0] value;
    input channel;
    begin
        @(negedge clk);
        sample_data = value;
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
            $display("FAIL framing: stop bit not HIGH at byte %0d", received_count);
            errors = errors + 1;
        end
        received[received_count] = value;
        received_count = received_count + 1;
        repeat (CLKS_PER_BIT/2) @(posedge clk);
    end
endtask

initial begin
    repeat (8) @(posedge clk);
    reset_n = 1'b1;
    fork
        begin
            emit_sample(24'sh7FFFFF, 1'b1); // RIGHT must still be ignored.
            for (i = 0; i < 32; i = i + 1)
                emit_sample(stimulus(i), 1'b0);
            while (received_count < 78) @(posedge clk);
        end
        begin
            while (received_count < 78) receive_uart_byte();
        end
        begin
            timeout = 0;
            while (received_count < 78 && timeout < 100000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (timeout >= 100000) begin
                $display("FAIL timeout received=%0d/78", received_count);
                $finish;
            end
        end
    join_any
    disable fork;

    if (received_count !== 78) begin
        $display("FAIL byte count expected=78 actual=%0d", received_count);
        errors = errors + 1;
    end else begin
        if (received[0] !== 8'hA5 || received[1] !== 8'hC3 ||
            received[2] !== 8'h01 || received[3] !== 8'h20 ||
            received[10] !== 8'd32 || received[11] !== 8'b00100100) begin
            $display("FAIL protocol header/type/count/flags changed");
            errors = errors + 1;
        end
        if ({received[5], received[4]} !== 16'd0 ||
            {received[9], received[8], received[7], received[6]} !== 32'd0) begin
            $display("FAIL initial sequence/counter");
            errors = errors + 1;
        end
        for (i = 0; i < 32; i = i + 1) begin
            decoded = $signed({received[13+(2*i)], received[12+(2*i)]});
            expected = expected_sample(i);
            if (decoded !== expected) begin
                $display("FAIL payload sample=%0d expected=%0d actual=%0d",
                         i, expected, decoded);
                errors = errors + 1;
            end
        end
        expected_crc = 16'hFFFF;
        for (i = 2; i <= 75; i = i + 1)
            expected_crc = crc16_update(expected_crc, received[i]);
        observed_crc = {received[77], received[76]};
        if (observed_crc !== expected_crc) begin
            $display("FAIL CRC expected=%04x actual=%04x", expected_crc, observed_crc);
            errors = errors + 1;
        end
    end
    if (accepted_sample_count !== 32 || dropped_sample_count !== 0 || overrun_latched !== 0) begin
        $display("FAIL counters accepted=%0d dropped=%0d overrun=%0d",
                 accepted_sample_count, dropped_sample_count, overrun_latched);
        errors = errors + 1;
    end
    if (errors == 0)
        $display("TEST_RESULT: PASS (gain8 payload, saturation, protocol, CRC, LEFT filter)");
    else
        $display("TEST_RESULT: FAIL errors=%0d", errors);
    $finish;
end
endmodule
