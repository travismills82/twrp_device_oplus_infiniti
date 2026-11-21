// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <algorithm>
#include <charconv>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <string>
#include <string_view>

namespace op15_wifi {
inline bool DecodeCounter(std::string_view text, uint64_t* value) {
    if (text.empty()) return false;
    const auto end = text.data() + text.size();
    const auto number = std::from_chars(text.data(), end, *value);
    return number.ec == std::errc{} && number.ptr == end;
}

inline bool ReadCounter(const char* path, uint64_t* value) {
    std::ifstream input(path);
    char line[32];
    return input.getline(line, sizeof(line)) && DecodeCounter(line, value);
}

class TrafficSampler {
public:
    std::string Sample(bool connected, uint64_t monotonic_ns) {
        uint64_t rx = 0, tx = 0;
        const bool ready = connected &&
            ReadCounter("/sys/class/net/wlan0/statistics/rx_bytes", &rx) &&
            ReadCounter("/sys/class/net/wlan0/statistics/tx_bytes", &tx);
        return Update(ready, monotonic_ns, rx, tx);
    }

    std::string Update(bool valid, uint64_t now, uint64_t rx, uint64_t tx) {
        std::string label;
        if (valid && have_sample && now > sample_time && now - sample_time <= 5000000000ULL &&
            rx >= previous_rx && tx >= previous_tx) {
            // bytes / ns * 1000 = decimal megabytes per second. Cap only
            // impossible display values to keep the status bar bounded.
            const auto rate = [&](uint64_t bytes) {
                return std::min(9999.9, static_cast<double>(bytes) * 1000.0 / (now - sample_time));
            };
            char text[48];
            std::snprintf(text, sizeof(text), "DL %.1f  UL %.1f MB/s",
                          rate(rx - previous_rx), rate(tx - previous_tx));
            label = text;
        }
        have_sample = valid;
        sample_time = now;
        previous_rx = rx;
        previous_tx = tx;
        return label;
    }

private:
    bool have_sample = false;
    uint64_t sample_time = 0, previous_rx = 0, previous_tx = 0;
};
}
