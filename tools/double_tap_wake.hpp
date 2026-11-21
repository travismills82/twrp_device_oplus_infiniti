// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <algorithm>
#include <cstdint>
#include <cstdlib>

namespace op15_touch {
class DoubleTap {
public:
    void Reset() { *this = DoubleTap{}; }

    // A down sample starts a contact; later down samples are movement.
    // Require two short releases near one another, not a hold or swipe.
    bool Observe(bool down, int x, int y, uint64_t now_ms, int width) {
        const int travel = std::max(12, width / 35);
        if (down) {
            if (!pressed) {
                pressed = true;
                moved = false;
                start_x = x;
                start_y = y;
                start_ms = now_ms;
            } else if (Far(x, y, start_x, start_y, travel)) {
                moved = true;
            }
            return false;
        }
        if (!pressed) return false;
        pressed = false;
        if (moved || now_ms < start_ms || now_ms - start_ms > 250 ||
            Far(x, y, start_x, start_y, travel)) {
            first_tap = false;
            return false;
        }
        const auto gap = now_ms - last_ms;
        if (first_tap && now_ms >= last_ms && gap >= 45 && gap <= 400 &&
            !Far(x, y, last_x, last_y, std::max(24, width / 14))) {
            Reset();
            return true;
        }
        first_tap = true;
        last_x = x;
        last_y = y;
        last_ms = now_ms;
        return false;
    }

private:
    static bool Far(int x, int y, int a, int b, int limit) {
        return std::abs(x - a) > limit || std::abs(y - b) > limit;
    }
    bool pressed = false, moved = false, first_tap = false;
    int start_x = 0, start_y = 0, last_x = 0, last_y = 0;
    uint64_t start_ms = 0, last_ms = 0;
};
}
