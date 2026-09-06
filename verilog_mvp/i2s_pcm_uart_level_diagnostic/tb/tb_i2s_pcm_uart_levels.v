`timescale 1ns/1ps

// Simulation-only sensitivity proof for the complete digital receive path.
// No production or frozen RTL is redefined here.
module tb_i2s_pcm_uart_levels;
localparam integer CLKS_PER_BIT = 4;
localparam signed [23:0] RIGHT_POISON = 24'sh5A1234;

reg clk = 1'b0;
reg reset_n = 1'b0;
reg serial_data = 1'b1; // Poison the initial I2S delay bit for LEFT sample 0.
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
wire transport_busy;
wire [31:0] accepted_sample_count;
wire [31:0] dropped_sample_count;
wire overrun_latched;
wire gated_capture_strobe = capture_strobe & rx_enable;

reg [7:0] received [0:77];
integer received_count = 0;
integer left_seen = 0;
integer right_seen = 0;
integer errors = 0;
integer timeout = 0;
integer i;
integer signed decoded;
integer signed expected;
integer upcoming_bit_index;
integer sck_rises_since_ws = 0;
reg last_sample_valid = 1'b0;
reg signed [23:0] drive_value;
reg [15:0] expected_crc;
reg [15:0] observed_crc;

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

safe_field_pcm_packet_tx_gain8 #(
    .UART_CLKS_PER_BIT(CLKS_PER_BIT), .PCM_ARITH_SHIFT(5)
) transport (
    .clk(clk), .reset_n(reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(sample_channel),
    .frame_error(frame_error), .status_flags(6'b001001),
    .uart_tx(uart_tx), .busy(transport_busy),
    .accepted_sample_count(accepted_sample_count),
    .dropped_sample_count(dropped_sample_count),
    .overrun_latched(overrun_latched)
);

// Peak amplitudes are round((2^23-1) * 10^(dBFS/20)). Both polarities are
// tested because arithmetic right shift rounds negative values toward -inf.
function signed [23:0] level_sample;
    input integer index;
    begin
        case (index % 14)
             0: level_sample =  24'sd839;      // -80 dBFS
             1: level_sample = -24'sd839;
             2: level_sample =  24'sd8389;     // -60 dBFS
             3: level_sample = -24'sd8389;
             4: level_sample =  24'sd26527;    // -50 dBFS
             5: level_sample = -24'sd26527;
             6: level_sample =  24'sd83886;    // -40 dBFS
             7: level_sample = -24'sd83886;
             8: level_sample =  24'sd265271;   // -30 dBFS
             9: level_sample = -24'sd265271;
            10: level_sample =  24'sd838861;   // -20 dBFS
            11: level_sample = -24'sd838861;
            12: level_sample =  24'sd4204263;  // -6 dBFS, saturates gain8
            default: level_sample = -24'sd4204263;
        endcase
    end
endfunction

function integer level_dbfs;
    input integer index;
    begin
        case ((index % 14) / 2)
            0: level_dbfs = -80;
            1: level_dbfs = -60;
            2: level_dbfs = -50;
            3: level_dbfs = -40;
            4: level_dbfs = -30;
            5: level_dbfs = -20;
            default: level_dbfs = -6;
        endcase
    end
endfunction

// Independent expected mapping; constants deliberately do not call DUT RTL.
function signed [15:0] expected_pcm16;
    input integer index;
    begin
        case (index % 14)
             0: expected_pcm16 =  16'sd26;
             1: expected_pcm16 = -16'sd27;
             2: expected_pcm16 =  16'sd262;
             3: expected_pcm16 = -16'sd263;
             4: expected_pcm16 =  16'sd828;
             5: expected_pcm16 = -16'sd829;
             6: expected_pcm16 =  16'sd2621;
             7: expected_pcm16 = -16'sd2622;
             8: expected_pcm16 =  16'sd8289;
             9: expected_pcm16 = -16'sd8290;
            10: expected_pcm16 =  16'sd26214;
            11: expected_pcm16 = -16'sd26215;
            12: expected_pcm16 =  16'sd32767;
            default: expected_pcm16 = -16'sd32768;
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

// Model an I2S transmitter: SD changes on SCK falling edges. Index 0 is an
// explicit poison/delay bit, indices 1..24 are signed PCM MSB first, and the
// remaining slot clocks are padding poison. Reading i2s_ws after #1 observes
// the WS value updated on the slot-boundary falling edge.
always @(negedge i2s_sck) begin
    if (reset_n && rx_enable) begin
        #1;
        upcoming_bit_index = (capture_bit_index == 31) ? 0
                                                       : capture_bit_index + 1;
        drive_value = i2s_ws ? RIGHT_POISON : level_sample(left_seen);
        if (upcoming_bit_index == 0)
            serial_data = ~drive_value[23];
        else if (upcoming_bit_index >= 1 && upcoming_bit_index <= 24)
            serial_data = drive_value[24-upcoming_bit_index];
        else
            serial_data = upcoming_bit_index[0];
    end
end

// WS must only change while SCK is LOW and exactly 32 rising SCK edges must
// occur per slot.
always @(posedge i2s_sck) begin
    if (reset_n)
        sck_rises_since_ws = sck_rises_since_ws + 1;
end

always @(i2s_ws) begin
    if (reset_n) begin
        #1;
        if (i2s_sck !== 1'b0) begin
            $display("FAIL WS changed while SCK was not LOW");
            errors = errors + 1;
        end
        if (sck_rises_since_ws !== 32) begin
            $display("FAIL slot length expected=32 actual=%0d", sck_rises_since_ws);
            errors = errors + 1;
        end
        sck_rises_since_ws = 0;
    end
end

// Observe the registered receiver outputs after nonblocking assignments settle.
always @(posedge clk) begin
    #1;
    if (!reset_n) begin
        last_sample_valid = 1'b0;
    end else begin
        if (frame_error) begin
            $display("FAIL receiver frame_error at left=%0d right=%0d",
                     left_seen, right_seen);
            errors = errors + 1;
        end
        if (sample_valid && last_sample_valid) begin
            $display("FAIL sample_valid wider than one sys_clk");
            errors = errors + 1;
        end
        if (sample_valid) begin
            if (!sample_channel) begin
                if (left_seen >= 32) begin
                    $display("FAIL unexpected extra LEFT sample");
                    errors = errors + 1;
                end else if (sample_data !== level_sample(left_seen)) begin
                    $display("FAIL I2S LEFT index=%0d dBFS=%0d expected24=%0d actual24=%0d",
                             left_seen, level_dbfs(left_seen),
                             level_sample(left_seen), sample_data);
                    errors = errors + 1;
                end else begin
                    $display("PASS I2S LEFT index=%0d dBFS=%0d sample24=%0d",
                             left_seen, level_dbfs(left_seen), sample_data);
                end
                left_seen = left_seen + 1;
                if (left_seen == 32)
                    rx_enable = 1'b0;
            end else begin
                if (sample_data !== RIGHT_POISON) begin
                    $display("FAIL I2S RIGHT poison expected=%0d actual=%0d",
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
            while (received_count < 78)
                receive_uart_byte();
        end
        begin
            timeout = 0;
            while (received_count < 78 && timeout < 100000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (timeout >= 100000) begin
                $display("FAIL timeout received=%0d/78", received_count);
                errors = errors + 1;
            end
        end
    join_any
    disable fork;
    repeat (4) @(posedge clk);

    if (received_count !== 78) begin
        $display("FAIL UART byte count expected=78 actual=%0d", received_count);
        errors = errors + 1;
    end else begin
        if (received[0] !== 8'hA5 || received[1] !== 8'hC3 ||
            received[2] !== 8'h01 || received[3] !== 8'h20) begin
            $display("FAIL UART sync/version/type");
            errors = errors + 1;
        end
        if ({received[5], received[4]} !== 16'd0 ||
            {received[9], received[8], received[7], received[6]} !== 32'd0 ||
            received[10] !== 8'd32 || received[11] !== 8'h24) begin
            $display("FAIL UART sequence/counter/count/flags");
            errors = errors + 1;
        end

        for (i = 0; i < 32; i = i + 1) begin
            decoded = $signed({received[13+(2*i)], received[12+(2*i)]});
            expected = expected_pcm16(i);
            if (decoded !== expected) begin
                $display("FAIL UART PCM index=%0d dBFS=%0d sample24=%0d expected16=%0d actual16=%0d",
                         i, level_dbfs(i), level_sample(i), expected, decoded);
                errors = errors + 1;
            end else begin
                $display("PASS UART PCM index=%0d dBFS=%0d sample24=%0d expected16=%0d actual16=%0d",
                         i, level_dbfs(i), level_sample(i), expected, decoded);
            end
        end

        expected_crc = 16'hFFFF;
        for (i = 2; i <= 75; i = i + 1)
            expected_crc = crc16_update(expected_crc, received[i]);
        observed_crc = {received[77], received[76]};
        if (observed_crc !== expected_crc) begin
            $display("FAIL CRC expected=%04x actual=%04x",
                     expected_crc, observed_crc);
            errors = errors + 1;
        end else begin
            $display("PASS CRC expected=%04x actual=%04x",
                     expected_crc, observed_crc);
        end
        $write("UART_FRAME_HEX=");
        for (i = 0; i < 78; i = i + 1)
            $write("%02x", received[i]);
        $display("");
    end

    if (left_seen !== 32 || right_seen !== 31) begin
        $display("FAIL receiver counts LEFT expected=32 actual=%0d RIGHT expected=31 actual=%0d",
                 left_seen, right_seen);
        errors = errors + 1;
    end
    if (accepted_sample_count !== 32 || dropped_sample_count !== 0 ||
        overrun_latched !== 0) begin
        $display("FAIL transport counters accepted=%0d dropped=%0d overrun=%0d",
                 accepted_sample_count, dropped_sample_count, overrun_latched);
        errors = errors + 1;
    end

    if (errors == 0)
        $display("TEST_RESULT: PASS (I2S delay/24-bit/sign/LEFT/sample_valid -> gain8 PCM16/saturation -> UART LE/CRC; levels -80,-60,-50,-40,-30,-20,-6 dBFS)");
    else
        $display("TEST_RESULT: FAIL errors=%0d", errors);
    $finish;
end
endmodule
