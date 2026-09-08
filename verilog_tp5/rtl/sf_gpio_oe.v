`timescale 1ns/1ps
module sf_gpio_oe(input wire data_out,input wire output_enable,inout wire pin,output wire data_in);assign pin=output_enable?data_out:1'bz;assign data_in=pin;endmodule
