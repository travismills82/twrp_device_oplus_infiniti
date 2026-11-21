// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "op15_smb_protocol.hpp"
#include <fcntl.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <unistd.h>
#include <fstream>
#include <mutex>
#include <sstream>
#include <vector>

namespace op15_smb {
enum class BackDestination { Leave, Servers, Connected };

inline BackDestination BrowserBack(std::string_view view, bool has_mount) {
    if (view.empty() || view == "servers" || view == "connected") return BackDestination::Leave;
    return has_mount ? BackDestination::Connected : BackDestination::Servers;
}

inline std::recursive_mutex Session;
inline std::mutex UIQueueLock;
inline std::vector<std::pair<std::string, std::string>> UIQueue;
inline void Queue(std::string key, std::string value) {
    std::lock_guard lock(UIQueueLock);
    UIQueue.emplace_back(std::move(key), std::move(value));
}
inline std::string MountId(std::istream& input) {
    std::string line, result;
    while (std::getline(input, line)) {
        std::istringstream row(line);
        std::string id, parent, dev, root, target, field, type, source;
        if (!(row >> id >> parent >> dev >> root >> target >> field) || target != Root) continue;
        while (field != "-" && (row >> field)) {}
        if (!(row >> type >> source) || root != "/" || type != Fs || source != Source ||
            !result.empty()) return {};
        result = id;
    }
    return input.bad() ? "" : result;
}
inline std::string MountId() {
    std::ifstream mounts("/proc/self/mountinfo");
    return MountId(mounts);
}
inline bool WifiUp() {
    ifaddrs* list = nullptr;
    if (getifaddrs(&list)) return false;
    bool live = false;
    for (auto p = list; p; p = p->ifa_next) {
        if (std::string_view(p->ifa_name) == "wlan0" && p->ifa_addr &&
            p->ifa_addr->sa_family == AF_INET &&
            (p->ifa_flags & (IFF_UP | IFF_RUNNING)) == (IFF_UP | IFF_RUNNING)) live = true;
    }
    freeifaddrs(list);
    return live;
}
inline bool Directory(const std::string& path, const std::string& id) {
    if (id.empty() || MountId() != id || !WifiUp() || !NetworkPath(path)) return false;
    const auto suffix = path.substr(std::string_view(Root).size());
    if (!suffix.empty() && !Path(suffix)) return false;
    char canonical[4096];
    struct stat root {}, dir {};
    return realpath(path.c_str(), canonical) && path == canonical &&
        stat(Root, &root) == 0 && stat(path.c_str(), &dir) == 0 &&
        S_ISDIR(dir.st_mode) && root.st_dev == dir.st_dev && MountId() == id;
}
inline bool Capacity(const std::string& path, uint64_t* free) {
    struct statvfs usage {};
    if (statvfs(path.c_str(), &usage) != 0 || !usage.f_frsize ||
        usage.f_bavail > UINT64_MAX / usage.f_frsize) return false;
    *free = static_cast<uint64_t>(usage.f_bavail) * usage.f_frsize;
    return true;
}
inline bool Writable(const std::string& path) {
    std::string probe = path + "/.twrp-write-test-XXXXXX";
    const int fd = mkostemp(probe.data(), O_CLOEXEC);
    if (fd < 0) return false;
    const bool synced = write(fd, "1", 1) == 1 && fsync(fd) == 0;
    const bool closed = close(fd) == 0;
    const bool removed = unlink(probe.c_str()) == 0;
    return synced && closed && removed;
}
}
