.macro PUSH2 r1, r2
    stp \r1, \r2, [sp, #-16]!
.endm
.macro POP2 r1, r2
    ldp \r1, \r2, [sp], #16
.endm
.macro LOAD_ADDR reg, sym
    adrp \reg, \sym
    add  \reg, \reg, :lo12:\sym
.endm
.macro LINUX_SYSCALL nr
    mov x8, #\nr
    svc #0
.endm
