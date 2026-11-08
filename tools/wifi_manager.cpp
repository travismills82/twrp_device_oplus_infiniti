// SPDX-License-Identifier: Apache-2.0
// Recovery-only saved Wi-Fi profiles. Never print profile contents or keys.
#include <arpa/inet.h>
#include <fcntl.h>
#include <ifaddrs.h>
#include <linux/fscrypt.h>
#include <poll.h>
#include <signal.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#ifndef WIFI_MANAGER_HOST_TEST
#include <android-base/properties.h>
#endif

namespace wifi {
constexpr size_t kMaxConfig = 256 * 1024;
constexpr char kDefault[] = "ctrl_interface=/tmp/recovery/sockets\nupdate_config=1\nap_scan=1\n";
struct Paths {
    std::string data = "/data";
    std::string parent = data + "/twrp";
    std::string saved = parent + "/wifi";
    std::string runtime = "/tmp/recovery/wifi";
    std::string mounts = "/proc/mounts";
    std::string socket = "/tmp/recovery/sockets/wlan0";
    std::string vendor_config = "/vendor/etc/wifi/wpa_supplicant.conf";
    uid_t root = 0, supplicant = 1010;
};
static volatile sig_atomic_t stopping = 0;
static void StopSignal(int) { stopping = 1; }
static void Property(const char* key, const std::string& value) {
#ifndef WIFI_MANAGER_HOST_TEST
    android::base::SetProperty(key, value);
#else
    (void)key; (void)value;
#endif
}
static std::string GetProperty(const char* key) {
#ifndef WIFI_MANAGER_HOST_TEST
    return android::base::GetProperty(key, "");
#else
    (void)key; return "";
#endif
}
static std::string Trim(const std::string& s) {
    const auto first = s.find_first_not_of(" \t\r\n");
    return first == std::string::npos ? "" : s.substr(first, s.find_last_not_of(" \t\r\n") - first + 1);
}
static bool DataMounted(const Paths& p, bool writable = false) {
    std::ifstream input(p.mounts);
    std::string dev, mount, fs, flags, rest;
    while (input >> dev >> mount >> fs >> flags) {
        std::getline(input, rest);
        if (mount == p.data && (fs == "ext4" || fs == "f2fs") &&
            (!writable || ("," + flags + ",").find(",rw,") != std::string::npos))
            return true;
    }
    return false;
}
static bool PlainDirectory(const std::string& path) {
    struct stat st{};
    return lstat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}
static bool SecureDirectory(const std::string& path, uid_t owner) {
    bool created = mkdir(path.c_str(), 0700) == 0;
    if (!created && errno != EEXIST) return false;
    struct stat st{};
    if (lstat(path.c_str(), &st) || !S_ISDIR(st.st_mode)) return false;
    if (created && chown(path.c_str(), owner, owner)) return false;
    if (!created && st.st_uid != owner) return false;
    return chmod(path.c_str(), 0700) == 0;
}
// An unencrypted fscrypt directory is independent of user-0 CE keys. The
// enclosing metadata-encrypted filesystem must still be mountable.
static bool IndependentOfUserKey(const std::string& path) {
#ifdef WIFI_MANAGER_HOST_TEST
    return PlainDirectory(path);
#else
    int fd = open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return false;
    fscrypt_get_policy_ex_arg policy{};
    policy.policy_size = sizeof(policy.policy);
    int result = ioctl(fd, FS_IOC_GET_ENCRYPTION_POLICY_EX, &policy);
    const int error = errno;
    close(fd);
    return result < 0 && error == ENODATA;
#endif
}
static bool StoreReady(const Paths& p, bool create = true) {
    if (!DataMounted(p, create) || !PlainDirectory(p.data)) return false;
    if (create) {
        if (!SecureDirectory(p.parent, p.root) || !SecureDirectory(p.saved, p.root)) return false;
    } else {
        for (const auto& path : {p.parent, p.saved}) {
            struct stat st{};
            if (lstat(path.c_str(), &st) || !S_ISDIR(st.st_mode) || st.st_uid != p.root || (st.st_mode & 0077)) return false;
        }
    }
    return IndependentOfUserKey(p.saved);
}
static bool ReadPrivate(const std::string& file, uid_t owner, std::string& data) {
    int fd = open(file.c_str(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) return false;
    struct stat st{};
    bool ok = fstat(fd, &st) == 0 && S_ISREG(st.st_mode) && st.st_uid == owner &&
        st.st_nlink == 1 && !(st.st_mode & 0007) && st.st_size > 0 && st.st_size <= static_cast<off_t>(kMaxConfig);
    data.clear();
    char buf[4096];
    while (ok) {
        ssize_t n = read(fd, buf, sizeof(buf));
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { ok = false; break; }
        if (!n) break;
        data.append(buf, static_cast<size_t>(n));
        if (data.size() > kMaxConfig) { ok = false; break; }
    }
    close(fd);
    return ok && data.size() == static_cast<size_t>(st.st_size) && data.find('\0') == std::string::npos;
}
static int ProfileCount(const std::string& data) {
    std::istringstream input(data);
    std::string line;
    bool block = false, network = false, ssid = false, writable = false;
    int count = 0;
    while (std::getline(input, line)) {
        line = Trim(line);
        if (line.empty() || line[0] == '#') continue;
        if (line == "update_config=1" && !block) writable = true;
        if (line.size() >= 2 && line.compare(line.size() - 2, 2, "={") == 0) {
            if (block) return -1;
            block = true; network = line == "network={"; ssid = false;
        } else if (line == "}") {
            if (!block || (network && !ssid)) return -1;
            if (network) ++count;
            block = network = false;
        } else if (network && line.compare(0, 5, "ssid=") == 0 && line.size() > 5) ssid = true;
    }
    return !block && writable ? count : -1;
}
static std::string EnabledProfiles(const std::string& data) {
    std::istringstream input(data);
    std::string out, line;
    bool network = false;
    while (std::getline(input, line)) {
        const auto trimmed = Trim(line);
        if (trimmed == "network={") network = true;
        if (network && trimmed == "disabled=1") line = "\tdisabled=0";
        if (trimmed == "}") network = false;
        out += line + "\n";
    }
    return out;
}
static std::string BaseConfig(const Paths& p) {
    // Preserve active-firmware authentication defaults, never vendor networks,
    // credentials, control paths or arbitrary configuration directives.
    const std::string allowed = "|eapol_version|fast_reauth|pmf|oce|sae_pwe|wowlan_disconnect_on_deinit|bss_no_flush_when_down|rsn_overriding|country|";
    std::ifstream input(p.vendor_config);
    char bytes[16384];
    input.read(bytes, sizeof(bytes));
    if (input.gcount() == static_cast<std::streamsize>(sizeof(bytes))) return kDefault;
    std::istringstream lines(std::string(bytes, static_cast<size_t>(input.gcount())));
    std::string out = kDefault, line;
    bool block = false;
    while (std::getline(lines, line)) {
        line = Trim(line);
        if (line.find('{') != std::string::npos) block = true;
        if (line == "}") { block = false; continue; }
        if (block) continue;
        const auto equals = line.find('=');
        if (equals == std::string::npos) continue;
        const auto key = line.substr(0, equals), value = line.substr(equals + 1);
        if (allowed.find("|" + key + "|") == std::string::npos || value.empty()) continue;
        if (value.find_first_not_of(key == "country" ? "ABCDEFGHIJKLMNOPQRSTUVWXYZ" : "0123456789") != std::string::npos) continue;
        out += line + "\n";
    }
    return out;
}
static bool AtomicWrite(const std::string& directory, const std::string& data, uid_t owner) {
    int dir = open(directory.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (dir < 0) return false;
    const std::string temp = ".wifi-new-" + std::to_string(getpid());
    int fd = openat(dir, temp.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) { close(dir); return false; }
    bool ok = fchmod(fd, 0600) == 0 && fchown(fd, owner, owner) == 0;
    size_t offset = 0;
    while (ok && offset < data.size()) {
        ssize_t n = write(fd, data.data() + offset, data.size() - offset);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { ok = false; break; }
        offset += static_cast<size_t>(n);
    }
    ok = ok && fsync(fd) == 0;
    if (close(fd)) ok = false;
    if (ok) ok = renameat(dir, temp.c_str(), dir, "wpa_supplicant.conf") == 0;
    if (ok) ok = fsync(dir) == 0;
    unlinkat(dir, temp.c_str(), 0);
    close(dir);
    return ok;
}
static std::string Request(const Paths& p, const std::string& command) {
    static unsigned serial = 0;
    const std::string local = p.runtime + "/ctrl-" + std::to_string(getpid()) + "-" + std::to_string(++serial);
    sockaddr_un from{}, to{};
    if (local.size() >= sizeof(from.sun_path) || p.socket.size() >= sizeof(to.sun_path)) return "";
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (fd < 0) return "";
    from.sun_family = to.sun_family = AF_UNIX;
    memcpy(from.sun_path, local.c_str(), local.size() + 1);
    memcpy(to.sun_path, p.socket.c_str(), p.socket.size() + 1);
    std::string reply;
    if (bind(fd, reinterpret_cast<sockaddr*>(&from), sizeof(from)) == 0 &&
        chown(local.c_str(), p.supplicant, p.supplicant) == 0 &&
        chmod(local.c_str(), 0600) == 0 &&
        connect(fd, reinterpret_cast<sockaddr*>(&to), sizeof(to)) == 0 &&
        send(fd, command.data(), command.size(), MSG_NOSIGNAL | MSG_DONTWAIT) == static_cast<ssize_t>(command.size())) {
        pollfd wait{fd, POLLIN, 0};
        if (poll(&wait, 1, 2000) > 0 && (wait.revents & POLLIN)) {
            char buf[65536];
            ssize_t size = recv(fd, buf, sizeof(buf), MSG_TRUNC | MSG_DONTWAIT);
            if (size > 0 && size < static_cast<ssize_t>(sizeof(buf))) reply.assign(buf, size);
        }
    }
    close(fd); unlink(local.c_str());
    return Trim(reply);
}
static std::string Field(const std::string& status, const std::string& key) {
    std::istringstream input(status);
    std::string line;
    while (std::getline(input, line)) if (line.compare(0, key.size() + 1, key + "=") == 0) return line.substr(key.size() + 1);
    return "";
}
static bool Prepare(const Paths& p) {
    if (!SecureDirectory(p.runtime, p.supplicant)) return false;
    std::string config;
    const bool saved = StoreReady(p, false) && ReadPrivate(p.saved + "/wpa_supplicant.conf", p.root, config) && ProfileCount(config) >= 0;
    if (!saved && (!ReadPrivate(p.runtime + "/wpa_supplicant.conf", p.supplicant, config) || ProfileCount(config) < 0)) config = BaseConfig(p);
    bool ok = AtomicWrite(p.runtime, EnabledProfiles(config), p.supplicant);
    Property("twrp.wifi.profiles", saved ? "loaded" : "ram-only");
    return ok;
}
static bool Save(const Paths& p) {
    if (!StoreReady(p)) { Property("twrp.wifi.profiles", "waiting-data"); return false; }
    if (Field(Request(p, "STATUS"), "wpa_state") != "COMPLETED") return false;
    if (Request(p, "SAVE_CONFIG") != "OK") return false;
    std::string config;
    const auto runtime = p.runtime + "/wpa_supplicant.conf";
    if (!ReadPrivate(runtime, p.supplicant, config) || ProfileCount(config) <= 0) return false;
    if (chmod(runtime.c_str(), 0600)) return false;
    config = EnabledProfiles(config);
    std::string previous;
    if (ReadPrivate(p.saved + "/wpa_supplicant.conf", p.root, previous) && previous == config) {
        Property("twrp.wifi.profiles", "saved");
        return true;
    }
    bool ok = AtomicWrite(p.saved, config, p.root);
    Property("twrp.wifi.profiles", ok ? "saved" : "save-failed");
    return ok;
}
static std::string IPv4() {
    ifaddrs* list = nullptr;
    std::string address;
    if (getifaddrs(&list)) return "";
    for (auto* item = list; item; item = item->ifa_next) {
        if (!item->ifa_addr || item->ifa_addr->sa_family != AF_INET || strcmp(item->ifa_name, "wlan0")) continue;
        auto* in = reinterpret_cast<sockaddr_in*>(item->ifa_addr);
        const uint32_t host = ntohl(in->sin_addr.s_addr);
        if (!host || (host >> 24) == 127 || (host >> 16) == 0xa9fe) continue;
        char buf[INET_ADDRSTRLEN];
        if (inet_ntop(AF_INET, &in->sin_addr, buf, sizeof(buf))) address = buf;
    }
    freeifaddrs(list); return address;
}
static bool DefaultRoute() {
    std::ifstream input("/proc/net/route");
    std::string line, iface, destination, gateway;
    unsigned flags;
    std::getline(input, line);
    while (std::getline(input, line)) {
        std::istringstream row(line);
        if (row >> iface >> destination >> gateway >> std::hex >> flags)
            if (iface == "wlan0" && destination == "00000000" && (flags & 3) == 3) return true;
    }
    return false;
}
static bool Run(const char* program, const char* arg, int seconds) {
    pid_t child = fork();
    if (child < 0) return false;
    if (!child) {
        int null = open("/dev/null", O_RDWR);
        if (null >= 0) { dup2(null, 0); dup2(null, 1); dup2(null, 2); if (null > 2) close(null); }
        execl(program, program, arg, nullptr); _exit(127);
    }
    for (int i = 0; i < seconds * 10; ++i) {
        int status;
        if (waitpid(child, &status, WNOHANG) == child) return WIFEXITED(status) && WEXITSTATUS(status) == 0;
        usleep(100000);
    }
    kill(child, SIGKILL); waitpid(child, nullptr, 0); return false;
}
static void Disconnected() {
    Property("twrp.wifi.connected", "0");
    Property("twrp.wifi.ip", "");
    Property("twrp.wifi.ssid", "");
}
static bool NeedsReassociate(const std::string& state, const std::string& networks, unsigned cycle) {
    // This Android supplicant can load enabled profiles yet remain DISCONNECTED
    // until REASSOCIATE. A scan alone is not enough on the tested OP15.
    return cycle % 15 == 0 && networks.find('\n') != std::string::npos &&
        (state == "DISCONNECTED" || state == "INACTIVE" || state == "SCANNING");
}
static int Monitor(const Paths& p, bool once) {
    if (!SecureDirectory(p.runtime, p.supplicant)) return 1;
    int lock = open((p.runtime + "/manager.lock").c_str(), O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (lock < 0 || flock(lock, LOCK_EX | LOCK_NB)) { if (lock >= 0) close(lock); return 1; }
    signal(SIGTERM, StopSignal); signal(SIGINT, StopSignal);
    std::string association;
    std::string published_ip;
    bool saved = false, loaded = GetProperty("twrp.wifi.profiles") == "loaded";
    unsigned cycle = 0;
    while (!stopping) {
        if (GetProperty("twrp.wifi.manual") == "1") { association.clear(); saved = false; }
        else {
            const auto status = Request(p, "STATUS");
            if (Field(status, "wpa_state") == "COMPLETED") {
                const auto current = Field(status, "bssid") + ":" + Field(status, "id");
                const bool changed = current != association;
                if (changed) { association = current; saved = false; published_ip.clear(); }
                if ((changed || cycle % 5 == 0) && (IPv4().empty() || !DefaultRoute()))
                    Run("/system/bin/dhcpcd", "wlan0", 15);
                const auto ip = IPv4();
                if (!ip.empty() && DefaultRoute()) {
                    if (published_ip != ip || GetProperty("twrp.wifi.dns.ready") != "1")
                        Run("/system/bin/twrp-dns-publish", "wlan0", 5);
                    if (GetProperty("twrp.wifi.dns.ready") == "1") {
                        published_ip = ip;
                        Property("twrp.wifi.ssid", Field(status, "ssid"));
                        Property("twrp.wifi.ip", ip);
                        Property("twrp.wifi.connected", "1");
                    } else Disconnected();
                } else Disconnected();
                if (!saved && GetProperty("twrp.wifi.manual") != "1") saved = Save(p);
            } else {
                Disconnected(); association.clear(); saved = false;
                // Do not overwrite an in-progress manual network configuration.
                const auto networks = Request(p, "LIST_NETWORKS");
                if (!loaded && DataMounted(p) && networks.find('\n') == std::string::npos &&
                    !networks.empty() && Prepare(p)) {
                    loaded = Request(p, "RECONFIGURE") == "OK";
                }
                if (cycle % 15 == 0) Request(p, "SCAN");
                if (NeedsReassociate(Field(status, "wpa_state"), networks, cycle))
                    Request(p, "REASSOCIATE");
            }
        }
        if (once) break;
        ++cycle;
        sleep(2);
    }
    if (!once) Disconnected();
    close(lock); return 0;
}
} // namespace wifi

#ifndef WIFI_MANAGER_HOST_TEST
int main(int argc, char** argv) {
    umask(0077);
    if (argc != 2 || geteuid() != 0) return 64;
    wifi::Paths paths;
    const std::string command = argv[1];
    if (command == "prepare") return wifi::Prepare(paths) ? 0 : 1;
    if (command == "save") return wifi::Save(paths) ? 0 : 1;
    if (command == "daemon" || command == "once") return wifi::Monitor(paths, command == "once");
    if (command == "status") {
        std::string config;
        bool ready = wifi::StoreReady(paths, false);
        int count = ready && wifi::ReadPrivate(paths.saved + "/wpa_supplicant.conf", 0, config) ? wifi::ProfileCount(config) : 0;
        printf("data_available=%d\nuser_key_independent=%d\nsaved_profiles=%d\n", wifi::DataMounted(paths), ready, count);
        printf("data_root_key_independent=%d\n", wifi::IndependentOfUserKey(paths.data));
        return ready ? 0 : 1;
    }
    return 64;
}
#endif
