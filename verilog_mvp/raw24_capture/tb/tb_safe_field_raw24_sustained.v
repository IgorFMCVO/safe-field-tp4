`timescale 1ns/1ps

// Throughput proof at the physical 27 MHz ratios: one LEFT source sample every
// 640 sys_clk cycles, stride two, and UART divisor 18 (exactly 1.5 Mbaud).
module tb_safe_field_raw24_sustained;
localparam integer CLKS_PER_BIT = 18;
localparam integer FRAME_BYTES = 95;
localparam integer FRAME_COUNT = 20;
reg clk = 1'b0;
reg reset_n = 1'b0;
reg signed [23:0] sample_data = 24'sd0;
reg sample_valid = 1'b0;
wire uart_tx;
wire busy;
wire [31:0] source_sample_count;
wire [31:0] accepted_sample_count;
wire [31:0] dropped_sample_count;
wire overrun_latched;
integer i;
integer timeout;
integer errors = 0;
integer received_count = 0;
integer frame_number;
integer byte_number;
reg [15:0] received_crc;

always #5 clk = ~clk;

safe_field_raw24_packet_tx #(
    .UART_CLKS_PER_BIT(CLKS_PER_BIT), .PCM_ARITH_SHIFT(5)
) dut (
    .clk(clk), .reset_n(reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(1'b0),
    .frame_error(1'b0), .status_flags(6'd0), .uart_tx(uart_tx),
    .busy(busy), .source_sample_count(source_sample_count),
    .accepted_sample_count(accepted_sample_count),
    .dropped_sample_count(dropped_sample_count),
    .overrun_latched(overrun_latched)
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

function [7:0] expected_frame_byte;
    input integer packet_index;
    input integer index_in_frame;
    integer pair_index;
    integer byte_in_pair;
    integer source_index;
    reg signed [23:0] expected_raw;
    reg signed [15:0] expected_pcm;
    reg [31:0] expected_first_counter;
    begin
        expected_first_counter = packet_index * 32;
        expected_frame_byte = 8'd0;
        case (index_in_frame)
            0: expected_frame_byte = 8'hA5;
            1: expected_frame_byte = 8'hC4;
            2: expected_frame_byte = 8'h01;
            3: expected_frame_byte = 8'h21;
            4: expected_frame_byte = packet_index[7:0];
            5: expected_frame_byte = packet_index[15:8];
            6: expected_frame_byte = expected_first_counter[7:0];
            7: expected_frame_byte = expected_first_counter[15:8];
            8: expected_frame_byte = expected_first_counter[23:16];
            9: expected_frame_byte = expected_first_counter[31:24];
            10: expected_frame_byte = 8'd16;
            11: expected_frame_byte = 8'd2;
            12: expected_frame_byte = 8'd0;
            default: begin
                if (index_in_frame >= 13 && index_in_frame <= 92) begin
                    pair_index = (index_in_frame - 13) / 5;
                    byte_in_pair = (index_in_frame - 13) % 5;
                    source_index = packet_index * 32 + pair_index * 2;
                    // The source is generated as (i - 320) <<< 5.  The
                    // configured gain-8 conversion shifts that exact value
                    // back to (i - 320), without saturation in this range.
                    expected_raw = (source_index - 320) <<< 5;
                    expected_pcm = source_index - 320;
                    case (byte_in_pair)
                        0: expected_frame_byte = expected_raw[7:0];
                        1: expected_frame_byte = expected_raw[15:8];
                        2: expected_frame_byte = expected_raw[23:16];
                        3: expected_frame_byte = expected_pcm[7:0];
                        default: expected_frame_byte = expected_pcm[15:8];
                    endcase
                end
            end
        endcase
    end
endfunction

task receive_and_validate_uart_byte;
    input integer packet_index;
    input integer index_in_frame;
    integer bit_number;
    reg [7:0] value;
    reg [7:0] expected_value;
    begin
        @(negedge uart_tx);
        repeat (CLKS_PER_BIT + (CLKS_PER_BIT / 2)) @(posedge clk);
        for (bit_number = 0; bit_number < 8; bit_number = bit_number + 1) begin
            value[bit_number] = uart_tx;
            repeat (CLKS_PER_BIT) @(posedge clk);
        end
        if (uart_tx !== 1'b1) begin
            $display("FAIL UART stop bit frame=%0d byte=%0d", packet_index,
                     index_in_frame);
            errors = errors + 1;
        end

        if (index_in_frame < 93)
            expected_value = expected_frame_byte(packet_index, index_in_frame);
        else if (index_in_frame == 93)
            expected_value = received_crc[7:0];
        else
            expected_value = received_crc[15:8];

        if (value !== expected_value) begin
            $display("FAIL UART byte frame=%0d byte=%0d expected=%02x actual=%02x",
                     packet_index, index_in_frame, expected_value, value);
            errors = errors + 1;
        end
        if (index_in_frame >= 2 && index_in_frame <= 92)
            received_crc = crc16_update(received_crc, value);
        received_count = received_count + 1;
        repeat (CLKS_PER_BIT / 2) @(posedge clk);
    end
endtask

initial begin
    repeat (8) @(posedge clk);
    reset_n = 1'b1;

    fork
        begin : source_driver
            // 640 source samples -> 320 retained -> 20 complete packets.
            for (i = 0; i < 640; i = i + 1) begin
                @(negedge clk);
                sample_data = (i - 320) <<< 5;
                sample_valid = 1'b1;
                @(negedge clk);
                sample_valid = 1'b0;
                repeat (638) @(negedge clk);
            end
        end
        begin : uart_receiver
            // Validate every physical 8-N-1 byte of every emitted packet.
            for (frame_number = 0; frame_number < FRAME_COUNT;
                 frame_number = frame_number + 1) begin
                received_crc = 16'hFFFF;
                for (byte_number = 0; byte_number < FRAME_BYTES;
                     byte_number = byte_number + 1)
                    receive_and_validate_uart_byte(frame_number, byte_number);
            end
        end
    join

    timeout = 0;
    while (busy && timeout < 100000) begin
        @(posedge clk);
        timeout = timeout + 1;
    end
    if (timeout >= 100000) begin
        $display("FAIL sustained timeout");
        errors = errors + 1;
    end
    if (source_sample_count !== 640 || accepted_sample_count !== 320) begin
        $display("FAIL sample counts source expected=640 actual=%0d accepted expected=320 actual=%0d",
                 source_sample_count, accepted_sample_count);
        errors = errors + 1;
    end
    if (dropped_sample_count !== 0 || overrun_latched !== 0) begin
        $display("FAIL sustained loss dropped=%0d overrun=%0d",
                 dropped_sample_count, overrun_latched);
        errors = errors + 1;
    end
    if (received_count !== FRAME_COUNT * FRAME_BYTES) begin
        $display("FAIL UART byte count expected=%0d actual=%0d",
                 FRAME_COUNT * FRAME_BYTES, received_count);
        errors = errors + 1;
    end
    if (dut.next_sequence !== 16'd20) begin
        $display("FAIL packets expected=20 actual=%0d", dut.next_sequence);
        errors = errors + 1;
    end
    if (errors == 0)
        $display("TEST_RESULT: PASS (20 x 95 UART bytes validated, physical rate, 1.5 Mbaud, zero loss)");
    else
        $display("TEST_RESULT: FAIL errors=%0d", errors);
    $finish;
end
endmodule
