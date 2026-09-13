/* C drives/checks tests; the implementation under test is the Assembly .a.
 * Pair returns exercise the actual AAPCS64 x0/x1 ABI, not a Python clone. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <time.h>
typedef struct { uint64_t value, status; } sf_result;
extern sf_result sf_ascii_to_u64(const char *, uint64_t);
extern sf_result sf_u64_to_ascii(uint64_t, char *, uint64_t);
extern int32_t sf_q15_mul(int32_t, int32_t);
extern void sf_add128(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t *);
extern void sf_memzero(void *, uint64_t);
extern uint64_t sf_ring_push(void *, uint64_t, uint64_t *, uint32_t);
extern uint32_t sf_crc8_atm(const void *, uint64_t);
extern uint64_t sf_build_command(uint32_t, uint32_t, uint32_t, void *);
extern int64_t sf_read_exact(int64_t, void *, uint64_t);
extern int64_t sf_write_all(int64_t, const void *, uint64_t);
extern int64_t sf_clock_gettime(struct timespec *);
extern int64_t sf_close(int64_t);
static unsigned checks, failures;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; printf("FAIL line=%d: %s\n", __LINE__, #c); } } while (0)
static uint8_t refcrc(const uint8_t *p, size_t n) {
 uint8_t c=0;size_t i;unsigned k;
 for(i=0;i<n;++i){c^=p[i];for(k=0;k<8;++k)c=(uint8_t)((c<<1)^((c&128)?7:0));}
 return c;
}
int main(void) {
 const char *good[]={"0","1","12345","18446744073709551615"};
 const uint64_t expected[]={0,1,12345,UINT64_MAX};
 char out[32];sf_result r;unsigned i,j;
 for(i=0;i<4;++i){
  r=sf_ascii_to_u64(good[i],strlen(good[i]));CHECK(r.status==0 && r.value==expected[i]);
  memset(out,0x55,sizeof out);r=sf_u64_to_ascii(expected[i],out,sizeof out);
  CHECK(r.status==0 && r.value==strlen(good[i]));
  CHECK(memcmp(out,good[i],strlen(good[i]))==0);CHECK(out[strlen(good[i])]==0x55);
 }
 CHECK(sf_ascii_to_u64("",0).status==1);
 CHECK(sf_ascii_to_u64("-1",2).status==1);
 CHECK(sf_ascii_to_u64("12x",3).status==1);
 CHECK(sf_ascii_to_u64("18446744073709551616",20).status==2);
 CHECK(sf_ascii_to_u64("99999999999999999999",20).status==2);
 memset(out,0x55,sizeof out);r=sf_u64_to_ascii(UINT64_MAX,out,19);
 CHECK(r.status!=0 && out[0]==0x55 && out[19]==0x55);
 CHECK(sf_u64_to_ascii(0,out,0).status!=0);
 r=sf_u64_to_ascii(0,out,1);CHECK(r.status==0 && r.value==1 && out[0]=='0');
 int32_t v[]={-32768,-32767,-1,0,1,16384,32766,32767};
 for(i=0;i<8;++i)for(j=0;j<8;++j){
  int64_t prod=(int64_t)v[i]*v[j];
  int64_t q=prod>=0?prod/32768:-((-prod+32767)/32768);
  if(q>32767)q=32767;
  if(q< -32768)q=-32768;
  CHECK(sf_q15_mul(v[i],v[j])==q);
 }
 uint64_t sum[2];sf_add128(UINT64_MAX,0,1,0,sum);CHECK(sum[0]==0 && sum[1]==1);
 sf_add128(UINT64_MAX,UINT64_MAX,1,0,sum);CHECK(sum[0]==0 && sum[1]==0);
 uint8_t b[6]={9,8,7,6,5,4};sf_memzero(b+1,4);CHECK(b[0]==9 && b[5]==4);
 CHECK(b[1]==0 && b[2]==0 && b[3]==0 && b[4]==0);sf_memzero(b,0);CHECK(b[0]==9);
 uint64_t idx=0;for(i=0;i<10;++i)CHECK(sf_ring_push(b,4,&idx,i)==(i+1)%4);
 CHECK(idx==2 && b[0]==8 && b[1]==9 && b[2]==6 && b[3]==7 && b[5]==4);
 uint8_t before=b[0];CHECK(sf_ring_push(b,0,&idx,99)==UINT64_MAX && idx==2 && b[0]==before);
 idx=4;CHECK(sf_ring_push(b,4,&idx,99)==UINT64_MAX && idx==4 && b[0]==before);
 CHECK(sf_crc8_atm("123456789",9)==0xF4);CHECK(sf_crc8_atm(b,0)==0);
 uint8_t frame[13];memset(frame,0xCC,sizeof frame);
 CHECK(sf_build_command(0x10,0x1234,0xABCD0102,frame)==11);
 const uint8_t header[]={0xA6,0x6A,0x05,0x10,0x12,0x34,0xAB,0xCD,1,2};
 CHECK(memcmp(frame,header,10)==0 && frame[10]==refcrc(frame+2,8));
 CHECK(frame[11]==0xCC && frame[12]==0xCC);
 int fds[2];int ok=pipe(fds);CHECK(ok==0);
 if(ok==0){CHECK(sf_write_all(fds[1],"ABC",3)==0);close(fds[1]);
  CHECK(sf_read_exact(fds[0],out,3)==0 && memcmp(out,"ABC",3)==0);
  CHECK(sf_read_exact(fds[0],out,1)==-61);CHECK(sf_close(fds[0])==0);}
 ok=pipe(fds);CHECK(ok==0);
 if(ok==0){CHECK(write(fds[1],"X",1)==1);close(fds[1]);CHECK(sf_read_exact(fds[0],out,2)==-61);close(fds[0]);}
 CHECK(sf_write_all(-1,"A",1)<0);CHECK(sf_read_exact(-1,out,1)<0);
 CHECK(sf_read_exact(-1,out,0)==0);CHECK(sf_write_all(-1,out,0)==0);
 struct timespec t1,t2;CHECK(sf_clock_gettime(&t1)==0);CHECK(sf_clock_gettime(&t2)==0);
 CHECK(t2.tv_sec>t1.tv_sec || (t2.tv_sec==t1.tv_sec && t2.tv_nsec>=t1.tv_nsec));
 printf("ASSEMBLY_ABI_TESTS: %s checks=%u failures=%u\n",failures?"FAIL":"PASS",checks,failures);
 return failures?1:0;
}
