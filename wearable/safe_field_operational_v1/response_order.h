#pragma once
#include <stdint.h>
// UI-owned; never read from a network task. Epochs invalidate in-flight polls.
class ResponseOrder {
  uint32_t epoch_ = 0, command_ = 0;
 public:
  void invalidate() { ++epoch_; }
  uint32_t epoch() const { return epoch_; }
  uint32_t beginCommand(uint32_t id) { command_ = id; return ++epoch_; }
  bool accept(uint32_t epoch, uint32_t id, bool poll) const {
    return epoch == epoch_ && (poll || id == command_);
  }
};
