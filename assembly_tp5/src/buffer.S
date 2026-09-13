.text
.global sf_memzero
.type sf_memzero,%function
// x0=valid writable buffer, x1=length. Zero length performs no access.
sf_memzero:
    cbz x1,2f
1:  strb wzr,[x0],#1
    subs x1,x1,#1
    b.ne 1b
2:  ret
.global sf_ring_push
.type sf_ring_push,%function
// Cyclic overwrite buffer, NOT a producer/consumer FIFO.
// x0=base,x1=capacity,x2=index_ptr,w3=value -> x0=new index.
// UINT64_MAX on capacity=0 or index>=capacity; no write on error.
// Callers still own the validity/lifetime of memory pointers.
sf_ring_push:
    cbz x1,3f
    ldr x4,[x2]
    cmp x4,x1
    b.hs 3f
    strb w3,[x0,x4]
    add x4,x4,#1
    cmp x4,x1
    csel x4,xzr,x4,eq
    str x4,[x2]
    mov x0,x4
    ret
3:  mov x0,#-1
    ret
.section .note.GNU-stack,"",%progbits
