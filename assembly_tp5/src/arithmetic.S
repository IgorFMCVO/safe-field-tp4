.text
.global sf_q15_mul
.type sf_q15_mul,%function
// w0=a Q1.15, w1=b Q1.15 -> w0=result Q1.15
sf_q15_mul:
    sxth w0,w0
    sxth w1,w1
    smull x2,w0,w1
    asr x2,x2,#15
    mov w0,w2
    ret

.global sf_add128
.type sf_add128,%function
// x0=alo,x1=ahi,x2=blo,x3=bhi,x4=out ptr
sf_add128:
    adds x5,x0,x2
    adc x6,x1,x3
    stp x5,x6,[x4]
    ret
