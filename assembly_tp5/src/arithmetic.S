.text
// Widened signed 32-bit result with 15 fractional bits.
// (-1)*(-1)=32768 is VALID: the result has not been narrowed to 16 bits.
.global sf_q15_mul
.type sf_q15_mul,%function
sf_q15_mul:
    sxth w0,w0
    sxth w1,w1
    smull x2,w0,w1
    asr x2,x2,#15
    mov w0,w2
    ret
// Explicit narrowing to signed Q1.15; saturate instead of wraparound.
.global sf_q15_mul_sat16
.type sf_q15_mul_sat16,%function
sf_q15_mul_sat16:
    sxth w0,w0
    sxth w1,w1
    smull x2,w0,w1
    asr x2,x2,#15
    mov x3,#32767
    cmp x2,x3
    csel x2,x3,x2,gt
    mov x3,#-32768
    cmp x2,x3
    csel x2,x3,x2,lt
    mov w0,w2
    ret
.global sf_add128
.type sf_add128,%function
// x0=alo,x1=ahi,x2=blo,x3=bhi,x4=out[2]; sum modulo 2^128.
sf_add128:
    adds x5,x0,x2
    adc x6,x1,x3
    stp x5,x6,[x4]
    ret
.section .note.GNU-stack,"",%progbits
