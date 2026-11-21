// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <algorithm>
#include <cstdint>
#include <string>
#include <string_view>

namespace op15_smb {
constexpr int LoginRefused = 3;
constexpr const char* Root = "/mnt/smb/share";
constexpr const char* Fs = "fuse.twrp-smb";
constexpr const char* Source = "twrp-smb";

inline void Wipe(std::string& value) {
    volatile char* bytes = value.data();
    for (size_t i = 0; i < value.size(); ++i) bytes[i] = 0;
    value.clear();
}

inline bool Below(std::string_view root, std::string_view candidate) {
    return !root.empty() && (candidate == root || (candidate.size() > root.size() &&
        candidate.compare(0, root.size(), root) == 0 && candidate[root.size()] == '/'));
}
inline bool NetworkPath(std::string_view p) { return Below(Root, p); }

inline bool Component(std::string_view word) {
    if (word.empty() || word.size() > 255 || word == "." || word == ".." ||
        word.back() == '.' || word.back() == ' ') return false;
    // Native recovery has some shell-based archive helpers. Restrict remote
    // path components to literal filename characters before they reach them.
    for (unsigned char c : word)
        if (!(c >= 128 || (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') ||
              (c >= 'a' && c <= 'z') || c == ' ' ||
              std::string_view("-_.+@()[]{}").find(c) != std::string_view::npos)) return false;
    return true;
}

inline bool Path(std::string_view path) {
    if (path.empty() || path.front() != '/' || path.size() >= 4096) return false;
    if (path.size() == 1) return true;
    path.remove_prefix(1);
    while (!path.empty()) {
        auto slash = path.find('/');
        if (!Component(path.substr(0, slash))) return false;
        if (slash == std::string_view::npos) return true;
        path.remove_prefix(slash + 1);
    }
    return false;
}

inline bool Host(std::string_view host) {
    if (host.empty() || host.size() > 253 || host.front() == '.' || host.back() == '.') return false;
    return std::all_of(host.begin(), host.end(), [](unsigned char c) {
        return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
            (c >= '0' && c <= '9') || c == '.' || c == '-';
    });
}

inline int Port(std::string_view text) {
    if (text.empty()) return 445;
    if (text.size() > 5) return 0;
    int port = 0;
    for (auto c : text) {
        if (c < '0' || c > '9') return 0;
        port = 10 * port + c - '0';
    }
    return port <= 65535 ? port : 0;
}

struct Lan {
    uint32_t ip = 0, mask = 0; // host order
    bool Contains(uint32_t peer) const {
        if (!ip || !mask || mask >= 0xfffffffe || peer == ip) return false;
        const auto net = ip & mask;
        return (peer & mask) == net && peer != net && peer != (net | ~mask);
    }
    uint32_t Start() const { return ip & std::max(mask, 0xffffff00U); }
    uint32_t End() const { return ip | ~std::max(mask, 0xffffff00U); }
};
}
