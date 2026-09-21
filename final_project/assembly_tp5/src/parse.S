.include "include/macros.inc"
.text
.global sf_ascii_to_u64
.type sf_ascii_to_u64,%function
// x0=ptr, x1=len -> x0=value, x1=status (0 ok, 1 invalid, 2 overflow)
sf_ascii_to_u64:
    mov x2,#0
    mov x3,#0
    cbz x1,9f
1:  ldrb w4,[x0,x3]
    cmp w4,#'0'
    b.lt 9f
    cmp w4,#'9'
    b.gt 9f
    sub w4,w4,#'0'
    mov x5,#10
    umulh x6,x2,x5
    cbnz x6,8f
    mul x7,x2,x5
    adds x7,x7,x4
    b.cs 8f
    mov x2,x7
    add x3,x3,#1
    cmp x3,x1
    b.lo 1b
    mov x0,x2
    mov x1,#0
    ret
8:  mov x0,#0
    mov x1,#2
    ret
9:  mov x0,#0
    mov x1,#1
    ret

.global sf_u64_to_ascii
.type sf_u64_to_ascii,%function
// x0=value, x1=buffer, x2=capacity -> x0=len, x1=status
sf_u64_to_ascii:
    PUSH2 x19,x20
    mov x19,x1
    mov x20,x2
    cmp x20,#1
    b.lo 8f
    cbnz x0,1f
    mov w3,#'0'
    strb w3,[x19]
    mov x0,#1
    mov x1,#0
    POP2 x19,x20
    ret
1:  sub sp,sp,#32
    mov x3,#0
    mov x4,#10
2:  udiv x5,x0,x4
    msub x6,x5,x4,x0
    add w6,w6,#'0'
    strb w6,[sp,x3]
    add x3,x3,#1
    mov x0,x5
    cbnz x0,2b
    cmp x3,x20
    b.hi 7f
    mov x7,#0
3:  sub x8,x3,x7
    sub x8,x8,#1
    ldrb w9,[sp,x8]
    strb w9,[x19,x7]
    add x7,x7,#1
    cmp x7,x3
    b.lo 3b
    add sp,sp,#32
    mov x0,x3
    mov x1,#0
    POP2 x19,x20
    ret
7:  add sp,sp,#32
8:  mov x0,#0
    mov x1,#1
    POP2 x19,x20
    ret
