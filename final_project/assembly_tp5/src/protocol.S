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

.global sf_validate_response
.type sf_validate_response,%function
// x0=frame[12], w1=expected type, w2=expected sequence,
// w3=expected data -> 0 valid, negative reason.
// This deliberately validates every semantic field, not only the CRC.
// A caller that is multiplexing RAW24 may ignore -1/-2/-3 frames and keep
// scanning; -4/-5 identify a response to its own command that is unusable.
sf_validate_response:
    // This is a non-leaf AAPCS64 routine: preserve both callee-saved
    // registers used below and LR, keeping SP 16-byte aligned.
    stp x19,x20,[sp,#-32]!
    str x30,[sp,#16]
    mov x19,x0
    mov w20,w3
    mov w6,w1
    mov w7,w2
    ldrb w4,[x19]
    cmp w4,#0x5a
    b.ne 1f
    ldrb w4,[x19,#1]
    cmp w4,#0xa5
    b.ne 1f
    ldrb w4,[x19,#2]
    cmp w4,#0x05
    b.ne 1f
    // CRC comes before semantics: a damaged RAW24-adjacent frame is recoverable.
    add x0,x19,#2
    mov x1,#9
    bl sf_crc8_atm
    ldrb w1,[x19,#11]
    cmp w0,w1
    b.ne 6f
    ldrb w4,[x19,#3]
    cmp w4,w6
    b.ne 2f
    ldrb w4,[x19,#4]
    ldrb w5,[x19,#5]
    lsl w4,w4,#8
    orr w4,w4,w5
    cmp w4,w7
    b.ne 3f
    ldr w4,[x19,#6]
    rev w4,w4
    cmp w4,w20
    b.ne 4f
    ldrb w4,[x19,#10]
    tbnz w4,#7,5f
    mov x0,#0
    b 7f
1:  mov x0,#-1
    b 7f
2:  mov x0,#-2
    b 7f
3:  mov x0,#-3
    b 7f
4:  mov x0,#-4
    b 7f
5:  mov x0,#-5
    b 7f
6:  mov x0,#-6
7:  ldr x30,[sp,#16]
    ldp x19,x20,[sp],#32
    ret
