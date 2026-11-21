// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <fstream>
#include <set>
#include <sstream>
#include <string>
#include <string_view>

namespace op15_network_sessions {
inline constexpr char Root[] = "/tmp/twrp-network-sessions";
using Sockets = std::set<std::string>;

inline bool Digits(std::string_view text) {
    return !text.empty() && text.find_first_not_of("0123456789") == std::string_view::npos;
}

inline std::string StartTime(const std::string& process) {
    std::ifstream stat(process + "/stat");
    std::string line, field;
    if (!std::getline(stat, line)) return {};
    // comm is parenthesized and can itself contain spaces and parentheses.
    const auto end = line.rfind(") ");
    if (end == std::string::npos) return {};
    std::istringstream fields(line.substr(end + 2));
    for (int i = 3; i <= 22; ++i) if (!(fields >> field)) return {};
    return Digits(field) ? field : std::string{};
}

inline void RegisterSmb(int socket_fd) {
    struct stat socket{};
    if (fstat(socket_fd, &socket) != 0 || !S_ISSOCK(socket.st_mode)) return;
    const std::string process = std::to_string(getpid());
    const auto start = StartTime("/proc/" + process);
    if (start.empty()) return;
    const std::string directory = std::string(Root) + "/smb";
    mkdir(Root, 0700);
    mkdir(directory.c_str(), 0700);
    // The SMB client is non-dumpable. Register its own socket inode instead
    // of making the GUI read its protected /proc/<pid>/fd directory.
    const auto file = directory + "/" + process + "." + start + "." + std::to_string(socket.st_ino);
    const int fd = open(file.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd >= 0) close(fd);
}

inline Sockets SessionSockets(const std::string& directory, const std::string& proc,
                              bool registered_inode = false) {
    Sockets result;
    DIR* sessions = opendir(directory.c_str());
    if (!sessions) return result;
    while (const auto* session = readdir(sessions)) {
        const std::string name(session->d_name);
        const auto dot = name.find('.');
        if (dot == std::string::npos) continue;
        const auto pid = name.substr(0, dot);
        const auto inode_dot = name.find('.', dot + 1);
        if ((inode_dot != std::string::npos) != registered_inode) continue;
        const auto start = name.substr(dot + 1, inode_dot == std::string::npos
                                      ? std::string::npos : inode_dot - dot - 1);
        const auto registered = registered_inode ? name.substr(inode_dot + 1) : std::string{};
        if (registered_inode && !Digits(registered)) continue;
        if (!Digits(pid) || !Digits(start)) continue;
        const auto process = proc + "/" + pid;
        const auto running = StartTime(process);
        if (running != start) {
            // Include the generation in the filename, so removing an old
            // marker can't remove a new session that reused the same PID.
            if (!running.empty() || access(process.c_str(), F_OK) != 0)
                unlink((directory + "/" + name).c_str());
            continue;
        }
        if (registered_inode) {
            result.emplace(registered);
            continue;
        }
        const auto fd_path = process + "/fd/";
        DIR* fds = opendir(fd_path.c_str());
        if (!fds) continue;
        Sockets owned;
        while (const auto* fd = readdir(fds)) {
            if (!Digits(fd->d_name)) continue;
            char link[64];
            const auto size = readlink((fd_path + fd->d_name).c_str(), link, sizeof(link));
            if (size < 10 || size >= static_cast<ssize_t>(sizeof(link))) continue;
            const std::string_view target(link, size);
            if (target.substr(0, 8) != "socket:[" || target.back() != ']') continue;
            const auto inode = target.substr(8, target.size() - 9);
            if (Digits(inode)) owned.emplace(inode);
        }
        closedir(fds);
        if (StartTime(process) == start) result.merge(owned);
    }
    closedir(sessions);
    return result;
}

inline bool Established(std::istream& input, const Sockets& sockets) {
    std::string line;
    while (std::getline(input, line)) {
        std::istringstream row(line);
        std::string slot, local, remote, state, queues, timer, retries, uid, wait, inode;
        if (row >> slot >> local >> remote >> state >> queues >> timer >> retries >> uid >> wait >> inode) {
            // TCP_ESTABLISHED only. LISTEN, SYN_SENT, CLOSE_WAIT and TIME_WAIT
            // do not indicate an active TWRP session.
            if (state == "01" && sockets.count(inode)) return true;
        }
    }
    return false;
}

inline bool Connected(const char* kind) {
    const auto sockets = SessionSockets(std::string(Root) + "/" + kind, "/proc",
                                        std::string_view(kind) == "smb");
    if (sockets.empty()) return false;
    std::ifstream ipv4("/proc/net/tcp");
    if (Established(ipv4, sockets)) return true;
    std::ifstream ipv6("/proc/net/tcp6");
    return Established(ipv6, sockets);
}
}
