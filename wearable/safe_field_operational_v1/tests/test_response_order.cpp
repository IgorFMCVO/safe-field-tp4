#include "../response_order.h"
#include <cassert>
#include <cstdint>
int main() {
  ResponseOrder order;
  const auto oldPoll = order.epoch();
  assert(order.accept(oldPoll, 1, true));
  order.invalidate(); // tap invalidates poll BEFORE deferred POST
  assert(!order.accept(oldPoll, 1, true));
  const auto start = order.beginCommand(2);
  assert(order.accept(start, 2, false));
  assert(!order.accept(start, 1, false));
  const auto stop = order.beginCommand(3);
  assert(!order.accept(start, 2, false));
  assert(order.accept(stop, 3, false));
  assert(!order.accept(start, 10, true));
  assert(order.accept(stop, 10, true));
  return 0;
}
