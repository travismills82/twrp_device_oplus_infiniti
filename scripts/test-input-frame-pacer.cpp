// SPDX-License-Identifier: Apache-2.0
#include "op15_input_frame_pacer.hpp"

#include <cassert>
#include <iostream>
#include <vector>

int main() {
    using namespace op15_input;
    constexpr auto ms = NanosecondsPerMs;
    constexpr uint64_t frame = 1000000000ULL / 30;
    uint64_t time = 1000 * ms;
    const auto now = [&] { return time; };

    // A continuously ready event fd must yield for visuals every frame,
    // with no dependency on a gap in the incoming events.
    unsigned dispatched = 0;
    uint64_t previous = time;
    for (int i = 0; i < 25; ++i) {
        const auto result = ServiceFrame(previous, frame, 0, true, now, [&](int timeout) {
            assert(timeout >= 0 && timeout <= 34);
            time += ms / 4;
            ++dispatched;
            return true;
        });
        assert(result - previous >= frame && result - previous < 34 * ms);
        previous = result;
    }
    assert(dispatched > 3000);

    // When genuinely idle, keep the efficient full wait and return after
    // it times out instead of spinning/redrawing.
    unsigned calls = 0;
    previous = time;
    ServiceFrame(previous, frame, 1000, false, now, [&](int timeout) {
        assert(timeout == 1000);
        ++calls;
        time += timeout * ms;
        return false;
    });
    assert(calls == 1 && time - previous == 1000 * ms);

    // Idle touch: first raw event wakes poll, the rest of the multitouch
    // packet is drained, then the UI can draw within the short wake window.
    calls = 0;
    previous = time;
    ServiceFrame(previous, frame, 1000, false, now, [&](int timeout) {
        ++calls;
        if (calls == 1) {
            assert(timeout == 1000);
            time += 420 * ms;
            return true;
        }
        assert(timeout <= 8);
        if (calls <= 5) {
            time += ms / 4;
            return true;
        }
        time += timeout * ms;
        return false;
    });
    assert(calls >= 6 && time - previous >= 428 * ms && time - previous < 429 * ms);

    // A held touch/key isn't idle, even if the previous frame was visually
    // quiet: hold/repeat timers must not be coarsened to a one-second poll.
    previous = time;
    ServiceFrame(previous, frame, 1000, true, now, [&](int timeout) {
        assert(timeout > 0 && timeout <= 34);
        time += timeout * ms;
        return false;
    });
    assert(time - previous == 34 * ms);

    // If a render already took too long, still allow a burst to drain.
    previous = time;
    time += 92 * ms;
    dispatched = 0;
    ServiceFrame(previous, frame, 0, false, now, [&](int timeout) {
        assert(timeout <= 8);
        time += ms / 4;
        ++dispatched;
        return true;
    });
    assert(dispatched == 32 && time - previous == 100 * ms);
    std::cout << "Touch frame pacing PASS: sustained input, idle wake, held keys and overdue frames\n";
}
