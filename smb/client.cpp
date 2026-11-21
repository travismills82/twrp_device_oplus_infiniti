// SPDX-License-Identifier: Apache-2.0
#ifndef FUSE_USE_VERSION
#define FUSE_USE_VERSION 31
#endif
#include <fuse.h>
#include <smb2/smb2.h>
#include <smb2/libsmb2.h>
#include <smb2/libsmb2-raw.h>
#include <smb2/smb2-errors.h>
#include "network_sessions.hpp"
#include "protocol.hpp"
#include "stream_digest.hpp"

#include <arpa/inet.h>
#include <fcntl.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <netdb.h>
#include <poll.h>
#include <signal.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/statvfs.h>
#include <sys/wait.h>
#include <unistd.h>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <vector>

namespace {
using namespace op15_smb;
const char* const Iface = "wlan0";
const char* Target() {
#ifndef __ANDROID__
    if (auto p = getenv("TWRP_SMB_TEST_TARGET")) return p;
#endif
    return Root;
}

Lan Network() {
    ifaddrs* list = nullptr;
    if (getifaddrs(&list)) return {};
    Lan out;
    for (auto* p = list; p; p = p->ifa_next) {
        if (strcmp(p->ifa_name, Iface) || !p->ifa_addr || !p->ifa_netmask ||
            p->ifa_addr->sa_family != AF_INET || !(p->ifa_flags & IFF_UP) ||
            !(p->ifa_flags & IFF_RUNNING)) continue;
        out = {ntohl(reinterpret_cast<sockaddr_in*>(p->ifa_addr)->sin_addr.s_addr),
               ntohl(reinterpret_cast<sockaddr_in*>(p->ifa_netmask)->sin_addr.s_addr)};
        break;
    }
    freeifaddrs(list);
    return out;
}
std::string Address(uint32_t ip) {
    in_addr addr{htonl(ip)};
    char out[INET_ADDRSTRLEN]{};
    return inet_ntop(AF_INET, &addr, out, sizeof(out)) ? out : "";
}
bool OnLan(uint32_t ip, const Lan& lan) {
#ifndef __ANDROID__
    // Only host fixtures can use the loopback server.
    if (ip == 0x7f000001 && getenv("TWRP_SMB_TEST_TARGET")) return true;
#endif
    return lan.Contains(ip);
}

bool AuthDenied(uint32_t status) {
    switch (status) {
    case SMB2_STATUS_ACCESS_DENIED:
    case SMB2_STATUS_NETWORK_ACCESS_DENIED:
    case SMB2_STATUS_LOGON_FAILURE:
    case SMB2_STATUS_NO_SUCH_USER:
    case SMB2_STATUS_WRONG_PASSWORD:
    case SMB2_STATUS_ACCOUNT_DISABLED:
    case SMB2_STATUS_ACCOUNT_RESTRICTION:
    case SMB2_STATUS_LOGON_TYPE_NOT_GRANTED:
    case SMB2_STATUS_PASSWORD_EXPIRED:
    case SMB2_STATUS_PASSWORD_MUST_CHANGE:
    case SMB2_STATUS_ACCOUNT_LOCKED_OUT:
        return true;
    default:
        return false;
    }
}

struct ShareQuery {
    bool done = false;
    int result = 2;
};

void ShareResult(smb2_context* ctx, int status, void* data, void* opaque) {
    auto& query = *static_cast<ShareQuery*>(opaque);
    auto* reply = static_cast<smb2_share_enum_reply*>(data);
    // SRVSVC returns Windows ERROR_ACCESS_DENIED (5), SMB transport can
    // return -EACCES. Do not confuse other RPC or connection errors with auth.
    if (status == 5 || status == -EACCES || status == -EPERM) {
        query.result = LoginRefused;
    } else if (status == 0 && reply) {
        query.result = 0;
        for (uint32_t i = 0; i < reply->entries_read && i < 256; ++i) {
            const auto& item = reply->share_info.info_1[i];
            if ((item.type & 0xff) == SMB2_SHARE_TYPE_DISKTREE &&
                !(item.type & SMB2_SHARE_TYPE_HIDDEN) && item.netname && Component(item.netname))
                puts(item.netname);
        }
    }
    if (reply) smb2_free_data(ctx, reply);
    query.done = true;
}

int ListShares(smb2_context* ctx, ShareQuery* query) {
    if (smb2_share_enum_async(ctx, SMB2_SHARE_INFO_1, ShareResult, query) < 0) return 2;
    while (!query->done) {
        pollfd p{smb2_get_fd(ctx), static_cast<short>(smb2_which_events(ctx)), 0};
        if (p.fd < 0) break;
        const int n = poll(&p, 1, 250);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0 || smb2_service(ctx, p.revents) < 0) break;
    }
    return query->done ? query->result : 2;
}
std::string Resolve(const std::string& host) {
    const Lan lan = Network();
    addrinfo hints{}, *reply = nullptr;
    hints.ai_family = AF_INET; hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host.c_str(), nullptr, &hints, &reply)) return {};
    std::string result;
    for (auto* row = reply; row; row = row->ai_next) {
        const auto ip = ntohl(reinterpret_cast<sockaddr_in*>(row->ai_addr)->sin_addr.s_addr);
        if (OnLan(ip, lan)) { result = Address(ip); break; }
    }
    freeaddrinfo(reply);
    return result;
}

int Scan(const Lan& lan) {
    if (!lan.ip || !lan.mask) return 2;
    std::vector<pollfd> sockets;
    std::vector<uint32_t> peers;
    for (uint64_t ip = lan.Start(); ip <= lan.End(); ++ip) {
        if (!lan.Contains(ip)) continue;
        const int fd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
        if (fd < 0) continue;
        if (setsockopt(fd, SOL_SOCKET, SO_BINDTODEVICE, Iface, strlen(Iface) + 1)) {
            close(fd); continue;
        }
        sockaddr_in dest{};
        dest.sin_family = AF_INET; dest.sin_port = htons(445); dest.sin_addr.s_addr = htonl(ip);
        if (!connect(fd, reinterpret_cast<sockaddr*>(&dest), sizeof(dest))) {
            puts(Address(ip).c_str()); close(fd);
        } else if (errno == EINPROGRESS) {
            sockets.push_back({fd, POLLOUT, 0}); peers.push_back(ip);
        } else close(fd);
    }
    // One bounded window for at most one /24; no rescan or background probes.
    for (int tick = 0; tick < 10; ++tick) {
        if (poll(sockets.data(), sockets.size(), 135) <= 0) continue;
        for (size_t i = 0; i < sockets.size(); ++i) {
            if (!sockets[i].revents || sockets[i].fd < 0) continue;
            int error = 0; socklen_t len = sizeof(error);
            if (!getsockopt(sockets[i].fd, SOL_SOCKET, SO_ERROR, &error, &len) && !error)
                puts(Address(peers[i]).c_str());
            close(sockets[i].fd); sockets[i].fd = -1;
        }
    }
    for (auto& p : sockets) if (p.fd >= 0) close(p.fd);
    return 0;
}

bool Receive(std::array<std::string, 6>& fields) {
    // NUL-delimited framed stdin, never argv, env, properties or files.
    for (auto& field : fields) {
        int c;
        while ((c = getchar()) != EOF && c != 0) {
            if (c < 32 || c == 127 || field.size() >= 511) return false;
            field.push_back(c);
        }
        if (c != 0) return false;
    }
    return true;
}
using Context = std::unique_ptr<smb2_context, decltype(&smb2_destroy_context)>;
smb2_context* S() { return static_cast<smb2_context*>(fuse_get_context()->private_data); }
bool Plain(const smb2_stat_64& v) {
    return !(v.smb2_attributes & SMB2_FILE_ATTRIBUTE_REPARSE_POINT) &&
        (v.smb2_type == SMB2_TYPE_FILE || v.smb2_type == SMB2_TYPE_DIRECTORY);
}
int PtrError() {
    const int result = nterror_to_errno(smb2_get_nterror(S()));
    return result > 0 ? -result : -EIO;
}
int Attributes(const char* path, struct stat* out, fuse_file_info*) {
    if (!Path(path)) return -EINVAL;
    smb2_stat_64 data{};
    const int rc = smb2_stat(S(), path + 1, &data);
    if (rc < 0) return rc;
    if (!Plain(data)) return -EOPNOTSUPP;
    memset(out, 0, sizeof(*out));
    out->st_mode = (data.smb2_type == SMB2_TYPE_DIRECTORY ? S_IFDIR | 0700 : S_IFREG | 0600);
    out->st_size = data.smb2_size;
    out->st_nlink = std::max(1U, data.smb2_nlink);
    out->st_mtim = {static_cast<time_t>(data.smb2_mtime), static_cast<long>(data.smb2_mtime_nsec)};
    return 0;
}
int ReadDir(const char* path, void* buf, fuse_fill_dir_t add, off_t, fuse_file_info*, fuse_readdir_flags) {
    if (!Path(path)) return -EINVAL;
    auto* dir = smb2_opendir(S(), path + 1);
    if (!dir) return PtrError();
    add(buf, ".", nullptr, 0, static_cast<fuse_fill_dir_flags>(0));
    add(buf, "..", nullptr, 0, static_cast<fuse_fill_dir_flags>(0));
    while (auto* item = smb2_readdir(S(), dir)) {
        if (Plain(item->st) && Component(item->name) &&
            add(buf, item->name, nullptr, 0, static_cast<fuse_fill_dir_flags>(0))) break;
    }
    smb2_closedir(S(), dir);
    return 0;
}
struct ArchiveRecord {
    Sha256Stream digest;
    WriteReceipt receipt{};
    bool ready = false;
    bool open = true;
    void Invalidate() { digest.Invalidate(); ready = false; }
};
struct FileHandle {
    smb2fh* remote = nullptr;
    bool writable = false;
    std::shared_ptr<ArchiveRecord> write;
};

// Owned by the daemon's single FUSE loop, never supplied by the SMB server.
std::map<std::string, std::shared_ptr<ArchiveRecord>> ArchiveRecords;
void ForgetArchives(const char* path) {
    for (auto it = ArchiveRecords.lower_bound(path); it != ArchiveRecords.end();) {
        if (!Below(path, it->first)) {
            if (it->first.compare(0, strlen(path), path) != 0) break;
            ++it;
            continue;
        }
        it->second->Invalidate();
        it = ArchiveRecords.erase(it);
    }
}
std::shared_ptr<ArchiveRecord> TrackArchive(const char* path, bool creates_file) {
    auto previous = ArchiveRecords.find(path);
    const bool concurrent = previous != ArchiveRecords.end() && previous->second->open;
    ForgetArchives(path);
    if (ArchiveRecords.size() >= 4096) {
        const auto closed = std::find_if(ArchiveRecords.begin(), ArchiveRecords.end(),
            [](const auto& row) { return !row.second->open; });
        if (closed == ArchiveRecords.end()) return {};
        ArchiveRecords.erase(closed);
    }
    auto record = std::make_shared<ArchiveRecord>();
    if (!creates_file || concurrent) record->Invalidate();
    return ArchiveRecords.emplace(path, record).first->second;
}

int DigestAttribute(const char* path, const char* name, char* value, size_t size) {
    if (!Path(path) || strcmp(name, WrittenDigestAttr)) return -ENODATA;
    const auto it = ArchiveRecords.find(path);
    if (it == ArchiveRecords.end() || !it->second->ready) return -ENODATA;
    const auto& receipt = it->second->receipt;
    if (!size) return receipt.size();
    if (size < receipt.size()) return -ERANGE;
    memcpy(value, receipt.data(), receipt.size());
    return receipt.size();
}

int Open(const char* path, fuse_file_info* info) {
    if (!Path(path)) return -EINVAL;
    auto* handle = smb2_open(S(), path + 1, info->flags & (O_ACCMODE | O_CREAT | O_EXCL | O_TRUNC | O_APPEND));
    if (!handle) return PtrError();
    auto file = std::make_unique<FileHandle>();
    file->remote = handle;
    file->writable = (info->flags & O_ACCMODE) != O_RDONLY;
    if (file->writable && DigestArchivePath(path))
        file->write = TrackArchive(path, (info->flags & (O_CREAT | O_TRUNC)) != 0);
    info->fh = reinterpret_cast<uintptr_t>(file.release());
    info->direct_io = 1;
    return 0;
}
FileHandle* File(fuse_file_info* info) { return reinterpret_cast<FileHandle*>(info->fh); }
smb2fh* Handle(fuse_file_info* info) { return File(info)->remote; }
int Space(const char* path, struct statvfs* out) {
    if (!Path(path)) return -EINVAL;
    struct smb2_statvfs v{};
    const int rc = smb2_statvfs(S(), path + 1, &v);
    if (rc < 0) return rc;
    out->f_bsize = v.f_bsize; out->f_frsize = v.f_frsize; out->f_blocks = v.f_blocks;
    out->f_bfree = v.f_bfree; out->f_bavail = v.f_bavail;
    out->f_files = v.f_files; out->f_ffree = v.f_ffree; out->f_favail = v.f_favail;
    out->f_namemax = v.f_namemax;
    return 0;
}

int Serve(smb2_context* ctx) {
    int ready[2];
    if (pipe2(ready, O_CLOEXEC)) return 4;
    pid_t child = fork();
    if (child < 0) { close(ready[0]); close(ready[1]); return 4; }
    if (child) {
        close(ready[1]);
        pollfd p{ready[0], POLLIN, 0};
        char ok = 0;
        if (poll(&p, 1, 6500) > 0 && read(ready[0], &ok, 1) != 1) ok = 0;
        close(ready[0]);
        if (!ok) { kill(child, SIGTERM); waitpid(child, nullptr, 0); return 4; }
        puts("mounted");
        return 0;
    }
    close(ready[0]);
    setsid();
    int null = open("/dev/null", O_RDWR | O_CLOEXEC);
    if (null < 0) _exit(4);
    for (int fd = 0; fd <= 2; ++fd) dup2(null, fd);
    if (null > 2) close(null);
    fuse_operations ops{};
    ops.getattr = Attributes; ops.readdir = ReadDir; ops.open = Open; ops.statfs = Space;
    ops.getxattr = DigestAttribute;
    ops.create = [](const char* p, mode_t, fuse_file_info* f) { f->flags |= O_CREAT; return Open(p, f); };
    ops.read = [](const char*, char* b, size_t n, off_t offset, fuse_file_info* f) {
        return offset < 0 ? -EINVAL : smb2_pread(S(), Handle(f), reinterpret_cast<uint8_t*>(b),
            std::min<size_t>(n, smb2_get_max_read_size(S())), offset);
    };
    ops.write = [](const char*, const char* b, size_t n, off_t offset, fuse_file_info* f) {
        auto& record = File(f)->write;
        if (record) record->ready = false;
        const auto request = std::min<size_t>(n, smb2_get_max_write_size(S()));
        const int count = offset < 0 ? -EINVAL : smb2_pwrite(S(), Handle(f),
            reinterpret_cast<const uint8_t*>(b), request, offset);
        if (record) {
            if (count <= 0 || static_cast<size_t>(count) > request) record->Invalidate();
            else record->digest.Append(offset, b, count);
        }
        return count > 0 && static_cast<size_t>(count) > request ? -EIO : count;
    };
    ops.flush = [](const char*, fuse_file_info* f) {
        // FUSE flush can pass only the handle, without the original open flags.
        if (!File(f)->writable) return 0;
        const int rc = smb2_fsync(S(), Handle(f));
        if (auto& record = File(f)->write) {
            if (rc != 0) record->Invalidate();
            else record->ready = record->digest.Finish(&record->receipt);
        }
        return rc;
    };
    ops.fsync = [](const char*, int, fuse_file_info* f) {
        const int rc = smb2_fsync(S(), Handle(f));
        if (rc != 0 && File(f)->write) File(f)->write->Invalidate();
        return rc;
    };
    ops.release = [](const char*, fuse_file_info* f) {
        std::unique_ptr<FileHandle> file(File(f));
        const int rc = smb2_close(S(), file->remote);
        if (auto& record = file->write) {
            record->open = false;
            if (rc != 0) record->Invalidate();
        }
        return rc;
    };
    ops.mkdir = [](const char* p, mode_t) { return Path(p) ? smb2_mkdir(S(), p + 1) : -EINVAL; };
    ops.rmdir = [](const char* p) {
        if (!Path(p)) return -EINVAL;
        ForgetArchives(p);
        return smb2_rmdir(S(), p + 1);
    };
    ops.unlink = [](const char* p) {
        if (!Path(p)) return -EINVAL;
        ForgetArchives(p);
        return smb2_unlink(S(), p + 1);
    };
    ops.rename = [](const char* p, const char* q, unsigned flags) {
        if (flags || !Path(p) || !Path(q)) return -EINVAL;
        ForgetArchives(p);
        ForgetArchives(q);
        return smb2_rename(S(), p + 1, q + 1);
    };
    ops.truncate = [](const char* p, off_t size, fuse_file_info* f) {
        if (size < 0 || !Path(p)) return -EINVAL;
        ForgetArchives(p);
        if (f && File(f)->write) File(f)->write->Invalidate();
        return f ? smb2_ftruncate(S(), Handle(f), size) : smb2_truncate(S(), p + 1, size);
    };
    // A single FUSE event loop serializes access to the SMB context.
    fuse_args args = FUSE_ARGS_INIT(0, nullptr);
    fuse_opt_add_arg(&args, "twrp-smb-client");
    fuse_opt_add_arg(&args, "-o");
    fuse_opt_add_arg(&args, "subtype=twrp-smb,fsname=twrp-smb,nodev,nosuid,noexec,entry_timeout=0,attr_timeout=0,negative_timeout=0");
    auto* fs = fuse_new(&args, &ops, sizeof(ops), ctx);
    fuse_opt_free_args(&args);
    if (!fs || fuse_mount(fs, Target())) _exit(4);
#ifdef __ANDROID__
    op15_network_sessions::RegisterSmb(smb2_get_fd(ctx));
#endif
    const char ok = 1;
    if (write(ready[1], &ok, 1) != 1) { fuse_unmount(fs); _exit(4); }
    close(ready[1]);
    fuse_loop(fs);
    fuse_unmount(fs);
    fuse_destroy(fs);
    smb2_destroy_context(ctx);
    _exit(0);
}
}

int main(int argc, char** argv) {
#ifndef __ANDROID__
    if (argc == 3 && std::string_view(argv[1]) == "fixture-verify-archive")
        return op15_smb::ReadbackAndSaveDigest(argv[2]) ? 0 : 6;
#endif
    if (argc != 2) return 1;
    prctl(PR_SET_DUMPABLE, 0, 0, 0, 0);
    signal(SIGPIPE, SIG_IGN);
    const rlimit core{0, 0};
    setrlimit(RLIMIT_CORE, &core);
    setvbuf(stdin, nullptr, _IONBF, 0);
    const std::string cmd = argv[1];
    if (cmd == "scan") return Scan(Network());
    if (cmd == "status") {
        const Lan lan = Network();
        if (!lan.ip) return 2;
        puts(Address(lan.ip).c_str()); return 0;
    }
    bool probe = false;
#ifndef __ANDROID__
    probe = cmd == "fixture-probe";
#endif
    if (cmd != "shares" && cmd != "mount" && !probe) return 1;
    // The library has per-command timeouts; this additionally caps the
    // complete DNS/negotiation/login operation, even if a peer goes silent.
    signal(SIGALRM, [](int) { _exit(2); });
    alarm(12);
    std::array<std::string, 6> fields;
    if (!Receive(fields)) return 1;
    auto& [server, port, share, user, password, domain] = fields;
    if (!Host(server) || !Port(port) || (cmd != "shares" && !Component(share))) return 1;
    const std::string addr = Resolve(server);
    if (addr.empty()) return 2;
    const std::string endpoint = addr + ":" + std::to_string(Port(port));
    // The query must outlive context destruction, which can drain pending callbacks.
    ShareQuery query;
    Context ctx(smb2_init_context(), smb2_destroy_context);
    if (!ctx) return 4;
    // A mounted USB HDD can stall briefly during writeback. The separate
    // login alarm above still bounds negotiation and share discovery.
    smb2_set_timeout(ctx.get(), 60);
    smb2_set_version(ctx.get(), SMB2_VERSION_ANY);
    smb2_set_authentication(ctx.get(), SMB2_SEC_NTLMSSP);
    smb2_set_sign(ctx.get(), !user.empty());
    smb2_set_user(ctx.get(), user.empty() ? "guest" : user.c_str());
    smb2_set_domain(ctx.get(), domain.c_str());
    smb2_set_password(ctx.get(), user.empty() ? nullptr : password.c_str());
    Wipe(password);
    int rc = smb2_connect_share(ctx.get(), endpoint.c_str(),
                              cmd == "shares" ? "IPC$" : share.c_str(), nullptr);
    if (rc < 0) return AuthDenied(smb2_get_nterror(ctx.get())) ? LoginRefused : 2;
    smb2_set_password(ctx.get(), nullptr);
    if (smb2_get_dialect(ctx.get()) < 0x0210) return 5;
    if (probe) {
        printf("%04x\n", smb2_get_dialect(ctx.get()));
        return 0;
    }
    if (cmd == "mount") {
        smb2_stat_64 root{};
        rc = smb2_stat(ctx.get(), "", &root);
        if (rc < 0) return AuthDenied(smb2_get_nterror(ctx.get())) ? LoginRefused : 2;
        if (!Plain(root)) return 2;
        alarm(0);
        return Serve(ctx.get());
    }
    return ListShares(ctx.get(), &query);
}
