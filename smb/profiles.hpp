// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "op15_smb_protocol.hpp"

#include <array>
#include <cerrno>
#include <cstdio>
#include <fcntl.h>
#include <fstream>
#include <linux/fscrypt.h>
#include <sstream>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace op15_smb {
using Login = std::array<std::string, 6>;
using Location = std::array<std::string, 3>;
constexpr char ProfileFile[] = "profiles.v1";
constexpr std::string_view ProfileMagic = "TWRP-SMB1\n";
constexpr size_t ProfileCountMax = 64;
constexpr size_t ProfileBytesMax = ProfileMagic.size() + ProfileCountMax * 6 * 256;

inline Location ProfileLocation(const Login& record) {
    std::string host = record[0];
    for (char& c : host) if (c >= 'A' && c <= 'Z') c = c - 'A' + 'a';
    return {host, std::to_string(Port(record[1])), record[2]};
}

inline bool ValidLogin(const Login& record) {
    return Host(record[0]) && Port(record[1]) && (record[2].empty() || Component(record[2])) &&
        std::all_of(record.begin(), record.end(), [](const auto& s) {
            return s.size() <= 255 && s.find('\0') == std::string::npos;
        }) && (!record[3].empty() || record[4].empty());
}

struct Profiles {
    std::vector<Login> records;
    ~Profiles() { for (auto& record : records) Wipe(record[4]); }
};

inline bool DecodeProfiles(std::string_view bytes, Profiles* profiles) {
    if (bytes.size() > ProfileBytesMax || bytes.substr(0, ProfileMagic.size()) != ProfileMagic) return false;
    bytes.remove_prefix(ProfileMagic.size());
    profiles->records.reserve(ProfileCountMax);
    while (!bytes.empty()) {
        if (profiles->records.size() >= ProfileCountMax) return false;
        auto& entry = profiles->records.emplace_back();
        for (auto& field : entry) {
            auto end = bytes.find('\0');
            if (end == std::string_view::npos || end > 255) return false;
            field.assign(bytes.substr(0, end));
            bytes.remove_prefix(end + 1);
        }
        if (!ValidLogin(entry)) return false;
        const auto key = ProfileLocation(entry);
        if (std::any_of(profiles->records.begin(), profiles->records.end() - 1,
                        [&](const auto& other) { return ProfileLocation(other) == key; })) return false;
    }
    return true;
}

inline bool DataVolumeMounted(std::istream& mounts) {
    std::string line;
    bool found = false;
    while (std::getline(mounts, line)) {
        std::istringstream row(line);
        std::string id, parent, dev, root, target, field, fs, source;
        if (!(row >> id >> parent >> dev >> root >> target >> field) || target != "/data") continue;
        while (field != "-" && (row >> field)) {}
        if (found || !(row >> fs >> source) || root != "/" ||
            (fs != "f2fs" && fs != "ext4") || source.rfind("/dev/block/", 0) != 0) return false;
        found = true;
    }
    return found && !mounts.bad();
}

inline int OpenProfileDirectory(bool create) {
    std::ifstream mounts("/proc/self/mountinfo");
    if (geteuid() != 0 || !DataVolumeMounted(mounts)) return -1;
    int fd = open("/data", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    struct stat data {};
    if (fstat(fd, &data) != 0) { close(fd); return -1; }
    for (const char* component : {"twrp", "smb"}) {
        if (create && mkdirat(fd, component, 0700) && errno != EEXIST) { close(fd); return -1; }
        const int child = openat(fd, component, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        close(fd);
        if (child < 0) return -1;
        struct stat st {};
        if (fstat(child, &st) || st.st_dev != data.st_dev || st.st_uid != 0 || (st.st_mode & 0777) != 0700) {
            close(child);
            return -1;
        }
        fd = child;
    }
    // Same availability as the Wi-Fi profile: the mounted, metadata-encrypted
    // Data volume is required, but the directory must not depend on the PIN key.
    fscrypt_get_policy_ex_arg policy{};
    policy.policy_size = sizeof(policy.policy);
    if (ioctl(fd, FS_IOC_GET_ENCRYPTION_POLICY_EX, &policy) >= 0 || errno != ENODATA) {
        close(fd);
        return -1;
    }
    return fd;
}

inline bool ReadProfiles(int directory, Profiles* profiles) {
    int fd = openat(directory, ProfileFile, O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return errno == ENOENT;
    struct stat st {};
    bool ok = fstat(fd, &st) == 0 && S_ISREG(st.st_mode) && st.st_uid == geteuid() && st.st_nlink == 1 &&
        (st.st_mode & 0777) == 0600 && st.st_size >= 0 && static_cast<uint64_t>(st.st_size) <= ProfileBytesMax;
    std::string bytes(ok ? st.st_size : 0, '\0');
    size_t read_bytes = 0;
    while (ok && read_bytes < bytes.size()) {
        const auto n = read(fd, bytes.data() + read_bytes, bytes.size() - read_bytes);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) ok = false;
        else read_bytes += n;
    }
    char extra;
    if (ok) {
        ssize_t n;
        do { n = read(fd, &extra, 1); } while (n < 0 && errno == EINTR);
        ok = n == 0;
    }
    close(fd);
    ok = ok && DecodeProfiles(bytes, profiles);
    Wipe(bytes);
    return ok;
}

inline bool UpdateProfile(int directory, const Login& login) {
    if (!ValidLogin(login)) return false;
    Profiles all;
    if (!ReadProfiles(directory, &all)) return false;
    const auto key = ProfileLocation(login);
    auto it = std::find_if(all.records.begin(), all.records.end(),
                           [&](const auto& other) { return ProfileLocation(other) == key; });
    if (it != all.records.end()) {
        // An available guest session is not a reason to discard saved credentials.
        if ((login[3].empty() && !(*it)[3].empty()) || *it == login) return true;
        Wipe((*it)[4]);
        *it = login;
    } else {
        if (all.records.size() >= ProfileCountMax) return false;
        all.records.push_back(login);
    }
    std::string bytes(ProfileMagic);
    for (const auto& record : all.records) for (const auto& field : record) { bytes += field; bytes.push_back('\0'); }
    const auto temp = ".profiles.tmp-" + std::to_string(getpid());
    const int fd = openat(directory, temp.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    bool ok = fd >= 0;
    size_t sent = 0;
    while (ok && sent < bytes.size()) {
        const auto n = write(fd, bytes.data() + sent, bytes.size() - sent);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) ok = false;
        else sent += n;
    }
    Wipe(bytes);
    if (fd < 0) return false;
    ok = ok && fsync(fd) == 0;
    ok = close(fd) == 0 && ok;
    if (ok) ok = renameat(directory, temp.c_str(), directory, ProfileFile) == 0;
    if (!ok) unlinkat(directory, temp.c_str(), 0);
    return ok && fsync(directory) == 0;
}
}
