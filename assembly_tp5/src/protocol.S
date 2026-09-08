.text
.global sf_crc8_atm
.type sf_crc8_atm,%function
// x0=ptr x1=len -> w0=crc8/atm init0 poly07
sf_crc8_atm:
    mov w2,#0
    mov x3,#0
1:  cmp x3,x1
    b.hs 4f
    ldrb w4,[x0,x3]
    eor w2,w2,w4
    mov w5,#8
2:  tst w2,#0x80
    lsl w2,w2,#1
    and w2,w2,#0xff
    b.eq 3f
    eor w2,w2,#0x07
3:  subs w5,w5,#1
    b.ne 2b
    add x3,x3,#1
    b 1b
4:  mov w0,w2
    ret

.global sf_build_command
.type sf_build_command,%function
// w0=cmd, w1=seq, w2=payload, x3=out[11] -> x0=len
sf_build_command:
    stp x19,x30,[sp,#-16]!
    mov x19,x3
    mov w4,#0xA6
    strb w4,[x19,#0]
    mov w4,#0x6A
    strb w4,[x19,#1]
    mov w4,#0x05
    strb w4,[x19,#2]
    strb w0,[x19,#3]
    lsr w4,w1,#8
    strb w4,[x19,#4]
    strb w1,[x19,#5]
    lsr w4,w2,#24
    strb w4,[x19,#6]
    lsr w4,w2,#16
    strb w4,[x19,#7]
    lsr w4,w2,#8
    strb w4,[x19,#8]
    strb w2,[x19,#9]
    add x0,x19,#2
    mov x1,#8
    bl sf_crc8_atm
    strb w0,[x19,#10]
    mov x0,#11
    ldp x19,x30,[sp],#16
    ret
