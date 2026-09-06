`timescale 1ns/1ps

module tb_safe_field_raw24_packet_tx;
localparam integer CLKS_PER_BIT = 4;
localparam signed [23:0] RIGHT_POISON = 24'sh5A1234;

reg clk = 1'b0;
reg reset_n = 1'b0;
reg serial_data = 1'b0;
reg rx_enable = 1'b1;
wire i2s_sck;
wire i2s_ws;
wire capture_strobe;
wire [5:0] capture_bit_index;
wire signed [23:0] sample_data;
wire sample_valid;
wire sample_channel;
wire frame_error;
wire uart_tx;
wire busy;
wire [31:0] source_sample_count;
wire [31:0] accepted_sample_count;
wire [31:0] dropped_sample_count;
wire overrun_latched;
wire gated_capture_strobe = capture_strobe & rx_enable;

reg [7:0] received [0:94];
integer received_count = 0;
integer source_left_seen = 0;
integer right_seen = 0;
integer errors = 0;
integer timeout = 0;
integer upcoming_bit_index;
integer i;
integer offset;
integer signed decoded_raw;
integer signed decoded_pcm;
reg signed [23:0] drive_value;
reg [15:0] expected_crc;
reg [15:0] observed_crc;
reg last_sample_valid = 1'b0;

always #5 clk = ~clk;

i2s_clock_gen #(.HALF_PERIOD_CLKS(5), .SLOT_BITS(32)) clock_master (
    .clk(clk), .reset_n(reset_n), .i2s_sck(i2s_sck), .i2s_ws(i2s_ws),
    .capture_strobe(capture_strobe), .capture_bit_index(capture_bit_index)
);

i2s_rx_24 receiver (
    .clk(clk), .reset_n(reset_n), .capture_strobe(gated_capture_strobe),
    .capture_bit_index(capture_bit_index), .channel_ws(i2s_ws),
    .serial_data(serial_data), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(sample_channel),
    .frame_error(frame_error)
);

safe_field_raw24_packet_tx #(
    .UART_CLKS_PER_BIT(CLKS_PER_BIT), .PCM_ARITH_SHIFT(5)
) dut (
    .clk(clk), .reset_n(reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(sample_channel),
    .frame_error(frame_error), .status_flags(6'b001001),
    .uart_tx(uart_tx), .busy(busy),
    .source_sample_count(source_sample_count),
    .accepted_sample_count(accepted_sample_count),
    .dropped_sample_count(dropped_sample_count),
    .overrun_latched(overrun_latched)
);

// The retained even source indexes exactly match the Python protocol fixture.
function signed [23:0] retained_raw;
    input integer retained_index;
    begin
        case (retained_index)
             0: retained_raw = 24'sh800000;  // -8388608
             1: retained_raw = -24'sd1048576;
             2: retained_raw = -24'sd8389;
             3: retained_raw = -24'sd32;
             4: retained_raw = -24'sd1;
             5: retained_raw = 24'sd0;
             6: retained_raw = 24'sd1;
             7: retained_raw = 24'sd31;
             8: retained_raw = 24'sd32;
             9: retained_raw = 24'sd839;
            10: retained_raw = 24'sd26527;
            11: retained_raw = 24'sd265271;
            12: retained_raw = 24'sd1048575;
            13: retained_raw = 24'sd4204263;
            14: retained_raw = 24'sd8388606;
            default: retained_raw = 24'sd8388607;
        endcase
    end
endfunction

function signed [23:0] source_raw;
    input integer source_index;
    begin
        if (!source_index[0])
            source_raw = retained_raw(source_index / 2);
        else
            source_raw = 24'sd100000 + source_index; // Must be discarded.
    end
endfunction

function signed [15:0] expected_pcm;
    input integer retained_index;
    begin
        case (retained_index)
             0: expected_pcm = -16'sd32768;
             1: expected_pcm = -16'sd32768;
             2: expected_pcm = -16'sd263;
             3: expected_pcm = -16'sd1;
             4: expected_pcm = -16'sd1;
             5: expected_pcm = 16'sd0;
             6: expected_pcm = 16'sd0;
             7: expected_pcm = 16'sd0;
             8: expected_pcm = 16'sd1;
             9: expected_pcm = 16'sd26;
            10: expected_pcm = 16'sd828;
            11: expected_pcm = 16'sd8289;
            12: expected_pcm = 16'sd32767;
            13: expected_pcm = 16'sd32767;
            14: expected_pcm = 16'sd32767;
            default: expected_pcm = 16'sd32767;
        endcase
    end
endfunction

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

// I2S transmitter model: delay bit 0 is poison, bits 1..24 are MSB-first.
always @(negedge i2s_sck) begin
    if (reset_n && rx_enable) begin
        #1;
        upcoming_bit_index = (capture_bit_index == 31) ? 0
                                                       : capture_bit_index + 1;
        drive_value = i2s_ws ? RIGHT_POISON : source_raw(source_left_seen);
        if (upcoming_bit_index == 0)
            serial_data = ~drive_value[23];
        else if (upcoming_bit_index >= 1 && upcoming_bit_index <= 24)
            serial_data = drive_value[24-upcoming_bit_index];
        else
            serial_data = ~upcoming_bit_index[0];
    end
end

always @(posedge clk) begin
    #1;
    if (!reset_n) begin
        last_sample_valid = 1'b0;
    end else begin
        if (frame_error) begin
            $display("FAIL I2S frame_error source_index=%0d", source_left_seen);
            errors = errors + 1;
        end
        if (sample_valid && last_sample_valid) begin
            $display("FAIL sample_valid wider than one sys_clk");
            errors = errors + 1;
        end
        if (sample_valid) begin
            if (!sample_channel) begin
                if (sample_data !== source_raw(source_left_seen)) begin
                    $display("FAIL decoded LEFT source=%0d expected=%0d actual=%0d",
                             source_left_seen, source_raw(source_left_seen), sample_data);
                    errors = errors + 1;
                end
                source_left_seen = source_left_seen + 1;
                if (source_left_seen == 32)
                    rx_enable = 1'b0;
            end else begin
                if (sample_data !== RIGHT_POISON) begin
                    $display("FAIL decoded RIGHT poison expected=%0d actual=%0d",
                             RIGHT_POISON, sample_data);
                    errors = errors + 1;
                end
                right_seen = right_seen + 1;
            end
        end
        last_sample_valid = sample_valid;
    end
end

task receive_uart_byte;
    integer bit_number;
    reg [7:0] value;
    begin
        @(negedge uart_tx);
        repeat (CLKS_PER_BIT + (CLKS_PER_BIT/2)) @(posedge clk);
        for (bit_number = 0; bit_number < 8; bit_number = bit_number + 1) begin
            value[bit_number] = uart_tx;
            repeat (CLKS_PER_BIT) @(posedge clk);
        end
        if (uart_tx !== 1'b1) begin
            $display("FAIL UART stop bit byte=%0d", received_count);
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
            while (received_count < 95)
                receive_uart_byte();
        end
        begin
            timeout = 0;
            while (received_count < 95 && timeout < 100000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (timeout >= 100000) begin
                $display("FAIL timeout received=%0d/95", received_count);
                errors = errors + 1;
            end
        end
    join_any
    disable fork;
    repeat (4) @(posedge clk);

    if (received_count !== 95) begin
        $display("FAIL frame bytes expected=95 actual=%0d", received_count);
        errors = errors + 1;
    end else begin
        if (received[0] !== 8'hA5 || received[1] !== 8'hC4 ||
            received[2] !== 8'h01 || received[3] !== 8'h21) begin
            $display("FAIL sync/version/type");
            errors = errors + 1;
        end
        if ({received[5], received[4]} !== 16'd0 ||
            {received[9], received[8], received[7], received[6]} !== 32'd0 ||
            received[10] !== 8'd16 || received[11] !== 8'd2 ||
            received[12] !== 8'h24) begin
            $display("FAIL sequence/source-counter/count/stride/flags");
            errors = errors + 1;
        end

        for (i = 0; i < 16; i = i + 1) begin
            offset = 13 + 5*i;
            decoded_raw = $signed({received[offset+2], received[offset+1],
                                   received[offset]});
            decoded_pcm = $signed({received[offset+4], received[offset+3]});
            if (decoded_raw !== retained_raw(i) ||
                decoded_pcm !== expected_pcm(i)) begin
                $display("FAIL pair=%0d raw expected=%0d actual=%0d pcm expected=%0d actual=%0d",
                         i, retained_raw(i), decoded_raw,
                         expected_pcm(i), decoded_pcm);
                errors = errors + 1;
            end else begin
                $display("PASS pair=%0d source_counter=%0d raw24=%0d pcm16=%0d",
                         i, i*2, decoded_raw, decoded_pcm);
            end
        end

        expected_crc = 16'hFFFF;
        for (i = 2; i <= 92; i = i + 1)
            expected_crc = crc16_update(expected_crc, received[i]);
        observed_crc = {received[94], received[93]};
        // 16'h69B9 is independently generated by the matching Python encoder.
        if (expected_crc !== 16'h69B9 || observed_crc !== expected_crc) begin
            $display("FAIL CRC expected=%04x actual=%04x",
                     expected_crc, observed_crc);
            errors = errors + 1;
        end else begin
            $display("PASS CRC expected=%04x actual=%04x",
                     expected_crc, observed_crc);
        end
    end

    if (source_left_seen !== 32 || right_seen !== 31 ||
        source_sample_count !== 32 || accepted_sample_count !== 16 ||
        dropped_sample_count !== 0 || overrun_latched !== 0) begin
        $display("FAIL counters left=%0d right=%0d source=%0d accepted=%0d dropped=%0d overrun=%0d",
                 source_left_seen, right_seen, source_sample_count,
                 accepted_sample_count, dropped_sample_count, overrun_latched);
        errors = errors + 1;
    end

    if (errors == 0)
        $display("TEST_RESULT: PASS (95 bytes, RAW24 LE + gain8 PCM16 LE, stride2 LEFT, CRC bytes2..92)");
    else
        $display("TEST_RESULT: FAIL errors=%0d", errors);
    $finish;
end
endmodule
