.include "include/syscalls.inc"
.include "include/macros.inc"
.text
.global sf_write_all
.type sf_write_all,%function
// x0=fd, x1=buffer, x2=len -> x0=0 success, negative error
sf_write_all:
    PUSH2 x19,x20
    mov x19,x0
    mov x20,x1
1:  cbz x2,3f
    mov x0,x19
    mov x1,x20
    mov x8,#SYS_write
    svc #0
    cmp x0,#0
    b.le 2f
    add x20,x20,x0
    sub x2,x2,x0
    b 1b
2:  POP2 x19,x20
    ret
3:  mov x0,#0
    POP2 x19,x20
    ret

.global sf_clock_gettime
.type sf_clock_gettime,%function
// x0=timespec pointer
sf_clock_gettime:
    mov x1,x0
    mov x0,#CLOCK_MONOTONIC
    mov x8,#SYS_clock_gettime
    svc #0
    ret

.global sf_read_exact
.type sf_read_exact,%function
// x0=fd, x1=buffer, x2=len -> x0=0 success, negative/EOF error
sf_read_exact:
    PUSH2 x19,x20
    mov x19,x0
    mov x20,x1
5:  cbz x2,7f
    mov x0,x19
    mov x1,x20
    mov x8,#SYS_read
    svc #0
    cmp x0,#0
    b.le 6f
    add x20,x20,x0
    sub x2,x2,x0
    b 5b
6:  POP2 x19,x20
    ret
7:  mov x0,#0
    POP2 x19,x20
    ret

.global sf_open_rw_noctty
.type sf_open_rw_noctty,%function
// x0=path -> x0=fd/error. Serial parameters are configured by stty wrapper.
sf_open_rw_noctty:
    mov x1,x0
    mov x0,#AT_FDCWD
    mov x2,#0x102
    mov x3,#0
    mov x8,#SYS_openat
    svc #0
    ret

.global sf_close
.type sf_close,%function
sf_close:
    mov x8,#SYS_close
    svc #0
    ret
