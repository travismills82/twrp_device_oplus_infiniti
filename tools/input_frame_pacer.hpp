// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <cstdint>

namespace op15_input {
constexpr uint64_t NanosecondsPerMs = 1000000;
// A ready input fd may contain only the first raw event of a multitouch
// report. Give it a short bounded drain, rather than delaying idle taps by
// a complete frame or redrawing after every low-level event.
constexpr uint64_t WakeDrainNs = 8 * NanosecondsPerMs;

inline int PollTimeoutMs(uint64_t now, uint64_t deadline) {
    if (now >= deadline) return 0;
    return static_cast<int>((deadline - now + NanosecondsPerMs - 1) / NanosecondsPerMs);
}

template <class Clock, class Poll>
uint64_t ServiceFrame(uint64_t previous, uint64_t budget, int idle_timeout_ms, bool held,
                      Clock now, Poll poll) {
    auto deadline = previous + budget;
    const auto wake_drain = budget < WakeDrainNs ? budget : WakeDrainNs;
    // Keep the existing long idle wait when nothing is held. The input fd
    // wakes that wait immediately; a held input still gets frame-rate timers.
    if (idle_timeout_ms > 0 && !held) {
        if (!poll(idle_timeout_ms)) return now();
        deadline = now() + wake_drain;
    } else {
        const auto after_render = now();
        if (after_render >= deadline) deadline = after_render + wake_drain;
    }
    do {
        // Drain touch reports without ever starting a long poll in an
        // active frame, even after an expensive render exceeded its slot.
        poll(PollTimeoutMs(now(), deadline));
    } while (now() < deadline);
    return now();
}
}
