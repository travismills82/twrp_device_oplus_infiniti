#include <cassert>
#include "op15_wifi_traffic.hpp"

int main() {
    using namespace op15_wifi;
    uint64_t parsed = 0;
    assert(DecodeCounter("18446744073709551615", &parsed) && parsed == UINT64_MAX);
    assert(!DecodeCounter("18446744073709551616", &parsed));
    assert(!DecodeCounter("-1", &parsed) && !DecodeCounter("123x", &parsed));

    TrafficSampler s;
    // First connected sample establishes a baseline rather than reporting total bytes.
    assert(s.Update(true, 1000000000, 9000000, 1000000).empty());
    assert(s.Update(true, 2000000000, 10200000, 1400000) == "DL 1.2  UL 0.4 MB/s");
    assert(s.Update(true, 4000000000, 11200000, 3400000) == "DL 0.5  UL 1.0 MB/s");
    assert(s.Update(true, 5000000000, 11200000, 3400000) == "DL 0.0  UL 0.0 MB/s");
    assert(s.Update(false, 6000000000, 0, 0).empty());
    assert(s.Update(true, 7000000000, 500, 300).empty());
    assert(s.Update(true, 8000000000, 300, 100).empty()); // Interface counter reset.
    assert(s.Update(true, 15000000000, 9000000, 1000000).empty()); // No stale sample after sleep.
    assert(s.Update(true, 16000000000, UINT64_MAX, UINT64_MAX) == "DL 9999.9  UL 9999.9 MB/s");
}
