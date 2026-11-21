#include <cassert>
#include "op15_double_tap_wake.hpp"

int main() {
    op15_touch::DoubleTap wake;
    auto sample = [&](bool down, int x, int y, uint64_t ms) { return wake.Observe(down, x, y, ms, 1272); };
    assert(!sample(false, 600, 600, 1000)); // An isolated release cannot start a tap.
    assert(!sample(true, 600, 600, 1030));
    assert(!sample(false, 600, 600, 1100));
    assert(!sample(true, 615, 605, 1200));
    assert(sample(false, 615, 605, 1250));

    assert(!sample(true, 600, 600, 2000));
    assert(!sample(false, 600, 600, 2060));
    assert(!sample(true, 601, 603, 2200));
    assert(!sample(true, 800, 605, 2250));
    assert(!sample(false, 601, 603, 2290)); // A returned drag still rejects the gesture.
    assert(!sample(true, 600, 600, 2400));
    assert(!sample(false, 600, 600, 2690)); // A hold isn't a tap.

    assert(!sample(true, 600, 600, 3000));
    assert(!sample(false, 600, 600, 3045));
    assert(!sample(true, 600, 600, 3500));
    assert(!sample(false, 600, 600, 3550)); // Too much time between taps.
    assert(!sample(true, 820, 600, 3670));
    assert(!sample(false, 820, 600, 3720)); // Different areas aren't a double tap.
    wake.Reset();
    assert(!sample(true, 820, 600, 3790));
    assert(!sample(false, 820, 600, 3850));
}
