// SPDX-License-Identifier: Apache-2.0
#include "core.hpp"

#include <android-base/properties.h>
#include <libavb/libavb.h>
#include <dirent.h>
#include <fcntl.h>
#include <linux/fs.h>
#include <signal.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/sysmacros.h>
#include <sys/wait.h>
#include <cstdio>
#include <chrono>
#include <ctime>
#include <cstring>
#include <iostream>
#include <sstream>
#include <utility>

namespace {
using namespace op15_update;
using android::base::GetProperty;
constexpr int Flags = O_CLOEXEC | O_NOFOLLOW;
constexpr char IdentityFile[] = "/system/etc/op15-updater-identity.json";
// All names passed to OpenAt below are constants or validated boot slot suffixes.
struct Fd {
    int n;
    explicit Fd(int fd) : n(fd) {}
    ~Fd() { if (n >= 0) close(n); }
    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
    Fd(Fd&& o) : n(std::exchange(o.n,-1)) {}
    operator int() const { return n; }
};
Fd Open(const std::string& path, int flags = O_RDONLY) {
    return Fd(open(path.c_str(),flags | Flags));
}
Fd At(int dir, const char* name, int flags = O_RDONLY) {
    return Fd(openat(dir,name,flags | Flags,0600));
}
std::string Read(int fd, size_t limit) {
    Require(fd >= 0, "Cannot open required file");
    std::string s;
    char buf[4096];
    ssize_t n;
    while ((n = TEMP_FAILURE_RETRY(read(fd,buf,sizeof(buf)))) > 0) {
        Require(static_cast<size_t>(n) <= limit - s.size(), "Input exceeds limit");
        s.append(buf,n);
    }
    Require(n == 0, "Cannot read required file");
    return s;
}
std::string File(const std::string& path, size_t limit = 64 * 1024) {
    return Read(Open(path),limit);
}
std::string Maybe(const std::string& path) {
    auto fd = Open(path);
    if (fd < 0 && errno == ENOENT) return {};
    return Read(fd,16 * 1024);
}
std::string MaybeAt(int dir, const char* name, size_t limit = 4096) {
    auto fd = At(dir,name);
    if (fd < 0 && errno == ENOENT) return {};
    struct stat sb{};
    Require(fd >= 0 && fstat(fd,&sb) == 0 && S_ISREG(sb.st_mode), "Invalid state file");
    return Read(fd,limit);
}
bool Exists(int dir, const char* name) {
    struct stat s{};
    if (fstatat(dir,name,&s,AT_SYMLINK_NOFOLLOW) == 0) return true;
    Require(errno == ENOENT,"Cannot inspect transaction or OTA state");
    return false;
}
void Out(const char* key, std::string value) {
    for (char& c : value) if (static_cast<unsigned char>(c) < 32 || c == 127) c = ' ';
    std::cout << key << '\t' << value << std::endl;
}
void Write(int fd, const char* p, size_t length) {
    while (length) {
        auto n = TEMP_FAILURE_RETRY(write(fd,p,length));
        Require(n > 0 && static_cast<size_t>(n) <= length,"Cannot write update storage");
        p += n;
        length -= n;
    }
}
std::string SlotToken(std::string input, bool config) {
    if (config) {
        std::istringstream lines(input);
        std::string line, result;
        while (std::getline(lines,line)) {
            auto eq = line.find('=');
            if (eq == std::string::npos) continue;
            auto key = line.substr(0,eq);
            const auto last = key.find_last_not_of(" \t");
            if (last == std::string::npos || key.substr(0,last+1) != "androidboot.slot_suffix") continue;
            auto value = line.substr(eq+1);
            const auto a = value.find_first_not_of(" \t");
            Require(a != std::string::npos,"Invalid bootconfig slot");
            value = value.substr(a,value.find_last_not_of(" \t")-a+1);
            if (value.size() >= 2 && value.front() == '"' && value.back() == '"')
                value = value.substr(1,value.size()-2);
            Require(result.empty() && Slot(value),"Invalid or duplicate bootconfig slot");
            result = value;
        }
        return result;
    }
    std::istringstream tokens(input);
    std::string t, result;
    constexpr std::string_view prefix = "androidboot.slot_suffix=";
    while (tokens >> t) if (t.compare(0,prefix.size(),prefix) == 0) {
        t.erase(0,prefix.size());
        Require(result.empty() && Slot(t),"Invalid or duplicate kernel slot");
        result = t;
    }
    return result;
}
std::string ActiveTarget() {
    auto project = GetProperty("ro.boot.prjname","");
    Require(geteuid() == 0 && GetProperty("ro.twrp.version","").compare(0,8,"3.7.1_16") == 0 &&
            (project == "24831" || project == "24863"),"Not a supported OnePlus 15 TWRP environment");
    Require(GetProperty("ro.boot.vbmeta.device_state","") == "unlocked" &&
            GetProperty("ro.boot.verifiedbootstate","") == "orange",
            "Bootloader verification state is not a supported unlocked configuration");
    const auto prop = GetProperty("ro.boot.slot_suffix","");
    const auto bootconfig = SlotToken(Maybe("/proc/bootconfig"),true);
    return Target(prop,bootconfig,SlotToken(File("/proc/cmdline"),false));
}
struct Mount {
    std::string id, path, opts, fs;
};
std::vector<Mount> Mounts() {
    std::vector<Mount> mounts;
    std::istringstream lines(File("/proc/self/mountinfo",1024 * 1024));
    std::string line;
    while (std::getline(lines,line)) {
        std::istringstream l(line);
        Mount m;
        std::string ignore;
        Require(bool(l >> ignore >> ignore >> m.id >> ignore >> m.path >> m.opts),
                "Invalid mount inventory");
        while (l >> ignore && ignore != "-") {}
        Require(ignore == "-" && bool(l >> m.fs),"Incomplete mount inventory");
        mounts.push_back(m);
    }
    return mounts;
}
std::string MajorMinor(dev_t dev) {
    return std::to_string(major(dev)) + ":" + std::to_string(minor(dev));
}
Fd RealMount(const char* path, bool write) {
    auto fd = Open(path,O_RDONLY | O_DIRECTORY);
    struct stat st{};
    Require(fd >= 0 && fstat(fd,&st) == 0,"Cannot access required mounted storage");
    for (const auto& m : Mounts()) if (m.path == path && m.id == MajorMinor(st.st_dev) &&
        (m.fs == "ext4" || m.fs == "f2fs") && (!write || m.opts == "rw" || m.opts.compare(0,3,"rw,") == 0))
        return fd;
    throw std::runtime_error("Mount Data and Metadata before updating");
}
void EmptyHolders(dev_t dev) {
    std::string path = "/sys/dev/block/" + MajorMinor(dev) + "/holders";
    std::unique_ptr<DIR,decltype(&closedir)> d(opendir(path.c_str()),closedir);
    Require(bool(d),"Cannot inspect recovery partition holders");
    for (;;) {
        errno = 0;
        auto* entry = readdir(d.get());
        if (!entry) { Require(errno == 0,"Cannot inspect recovery partition holders"); return; }
        Require(!std::strcmp(entry->d_name,".") || !std::strcmp(entry->d_name,".."),
                "Recovery is in use by a block mapping");
    }
}
struct Block {
    Fd fd;
    uint64_t bytes;
    dev_t dev;
};
Block Partition(const std::string& name, bool write = false) {
    // The kernel-reported GPT partition name must agree with the by-name link.
    const auto boot_path = "/dev/block/bootdevice/by-name/" + name;
    const auto alias_path = "/dev/block/by-name/" + name;
    struct stat s{}, by_boot{}, by_block{};
    const bool boot = stat(boot_path.c_str(),&by_boot) == 0;
    Require(boot || errno == ENOENT,"Cannot inspect bootdevice partition link");
    const bool alias = stat(alias_path.c_str(),&by_block) == 0;
    Require(alias || errno == ENOENT,"Cannot inspect block partition link");
    Require((boot || alias) && (!boot || S_ISBLK(by_boot.st_mode)) &&
            (!alias || S_ISBLK(by_block.st_mode)) &&
            (!(boot && alias) || by_boot.st_rdev == by_block.st_rdev),"Conflicting or missing partition links");
    const auto& path = boot ? boot_path : alias_path;
    auto fd = Fd(open(path.c_str(),(write ? O_RDWR | O_EXCL : O_RDONLY) | O_CLOEXEC));
    uint64_t n = 0;
    Require(fd >= 0 && fstat(fd,&s) == 0 && S_ISBLK(s.st_mode) &&
            s.st_rdev == (boot ? by_boot.st_rdev : by_block.st_rdev) &&
            ioctl(fd,BLKGETSIZE64,&n) == 0 && n > 0 && n <= 512ULL * 1024 * 1024,
            "Required block partition is missing, busy or has an invalid size");
    const auto id = MajorMinor(s.st_rdev);
    std::istringstream attrs(File("/sys/dev/block/" + id + "/uevent",4096));
    std::string line, partname;
    while (std::getline(attrs,line))
        if (line.compare(0,9,"PARTNAME=") == 0) partname = line.substr(9);
    Require(partname == name,"Block device and GPT partition name do not agree");
    if (name == "recovery_a" || name == "recovery_b") {
        int ro = 1;
        Require(n == ImageSize && ioctl(fd,BLKROGET,&ro) == 0 && ro == 0,
                "Recovery partition has the wrong size or is read-only");
        for (const auto& m : Mounts()) Require(m.id != id,"Recovery partition is mounted");
        EmptyHolders(s.st_rdev);
    }
    return {std::move(fd),n,s.st_rdev};
}
Profile Probe(const std::string& target, const Block& recovery) {
    Profile p{GetProperty("ro.boot.prjname",""),target.substr(8),{},{},{},{},{},{}};
    const auto hash = [&](const std::string& base) {
        auto block = Partition(base + p.slot);
        Require(block.dev != recovery.dev,"Boot and recovery partition links alias");
        return Hex(Hash(block.fd,block.bytes));
    };
    p.boot = hash("boot");
    p.init_boot = hash("init_boot");
    p.vendor_boot = hash("vendor_boot");
    p.dtbo = hash("dtbo");
    p.vbmeta = hash("vbmeta");
    p.from_recovery = Hex(Hash(recovery.fd,recovery.bytes));
    return p;
}
void ReadAt(int fd, void* buffer, size_t size, uint64_t offset) {
    auto* p = static_cast<char*>(buffer);
    while (size) {
        auto n = TEMP_FAILURE_RETRY(pread(fd,p,size,offset));
        Require(n > 0 && static_cast<size_t>(n) <= size,"Incomplete partition or image read");
        p += n;
        size -= n;
        offset += n;
    }
}
uint32_t LE(const unsigned char* p) {
    return uint32_t(p[0]) | (uint32_t(p[1])<<8) | (uint32_t(p[2])<<16) | (uint32_t(p[3])<<24);
}
struct AvbPolicy {
    std::string key;
    uint64_t rollback;
    uint32_t location, algorithm;
    bool operator==(const AvbPolicy& other) const {
        return key == other.key && rollback == other.rollback && location == other.location &&
            algorithm == other.algorithm;
    }
};
struct HashDescriptor {
    const uint8_t* start;
    const uint8_t* end;
    const AvbHashDescriptor* found = nullptr;
    unsigned count = 0;
};
bool VisitDescriptor(const AvbDescriptor* descriptor, void* data) {
    auto& d = *static_cast<HashDescriptor*>(data);
    AvbDescriptor h{};
    if (!avb_descriptor_validate_and_byteswap(descriptor,&h)) return false;
    const auto* raw = reinterpret_cast<const uint8_t*>(descriptor);
    if (raw < d.start || raw > d.end ||
        static_cast<uint64_t>(d.end-raw) < sizeof(h) ||
        h.num_bytes_following > static_cast<uint64_t>(d.end-raw)-sizeof(h)) return false;
    if (h.tag == AVB_DESCRIPTOR_TAG_HASH) {
        if (h.num_bytes_following < sizeof(AvbHashDescriptor)-sizeof(h)) return false;
        d.found = reinterpret_cast<const AvbHashDescriptor*>(descriptor);
        ++d.count;
    } else if (h.tag != AVB_DESCRIPTOR_TAG_PROPERTY) {
        return false;
    }
    return true;
}
AvbPolicy RecoveryImage(int fd) {
    unsigned char header[44]{};
    ReadAt(fd,header,sizeof(header),0);
    Require(!std::memcmp(header,"ANDROID!",8) && LE(header+8) == 0 && LE(header+12) > 0 &&
            LE(header+20) == 1584 && LE(header+40) == 4,"Not an OP15 v4 ramdisk-only recovery image");
    AvbFooter raw{}, footer{};
    ReadAt(fd,&raw,sizeof(raw),ImageSize-sizeof(raw));
    Require(avb_footer_validate_and_byteswap(&raw,&footer) && footer.vbmeta_size >= sizeof(AvbVBMetaImageHeader) &&
            footer.vbmeta_size <= 64 * 1024 && footer.original_image_size >= 4096ULL + LE(header+12) &&
            footer.original_image_size <= footer.vbmeta_offset &&
            footer.vbmeta_offset <= ImageSize-sizeof(raw)-footer.vbmeta_size,"Invalid recovery AVB footer");
    std::vector<uint8_t> bytes(footer.vbmeta_size);
    ReadAt(fd,bytes.data(),bytes.size(),footer.vbmeta_offset);
    const uint8_t* public_key = nullptr;
    size_t key_length = 0;
    Require(avb_vbmeta_image_verify(bytes.data(),bytes.size(),&public_key,&key_length) == AVB_VBMETA_VERIFY_RESULT_OK &&
            public_key && key_length > 0,"Invalid recovery AVB signature");
    AvbVBMetaImageHeader vbmeta{};
    avb_vbmeta_image_header_to_host_byte_order(
        reinterpret_cast<const AvbVBMetaImageHeader*>(bytes.data()),&vbmeta);
    Require(vbmeta.flags == 0 && vbmeta.algorithm_type == AVB_ALGORITHM_TYPE_SHA256_RSA2048,
            "Unexpected recovery AVB algorithm or verification flags");
    HashDescriptor desc{bytes.data(),bytes.data()+bytes.size()};
    Require(avb_descriptor_foreach(bytes.data(),bytes.size(),VisitDescriptor,&desc) &&
            desc.count == 1,"Invalid recovery AVB descriptors");
    AvbHashDescriptor h{};
    Require(avb_hash_descriptor_validate_and_byteswap(desc.found,&h) &&
            !std::memcmp(h.hash_algorithm,"sha256",7) && h.partition_name_len == 8 &&
            h.digest_len == 32 && h.salt_len <= 64 && h.flags == 0 &&
            h.image_size == footer.original_image_size,"Invalid recovery AVB hash descriptor");
    Require(h.parent_descriptor.num_bytes_following >=
            sizeof(h)-sizeof(AvbDescriptor)+h.partition_name_len+h.salt_len+h.digest_len,
            "Truncated recovery AVB hash descriptor");
    const auto* part = reinterpret_cast<const uint8_t*>(desc.found)+sizeof(h);
    const auto* salt = part+h.partition_name_len;
    const auto* digest = salt+h.salt_len;
    Require(!std::memcmp(part,"recovery",8),"Unexpected AVB partition");
    const auto computed = Hash(fd,h.image_size,std::string(reinterpret_cast<const char*>(salt),h.salt_len));
    Require(!std::memcmp(digest,computed.data(),computed.size()),"Recovery AVB payload hash mismatch");
    return {std::string(reinterpret_cast<const char*>(public_key),key_length),
            vbmeta.rollback_index,vbmeta.rollback_index_location,vbmeta.algorithm_type};
}
void Power() {
    auto battery = File("/sys/class/power_supply/battery/capacity",16);
    if (!battery.empty() && battery.back() == '\n') battery.pop_back();
    Require(!battery.empty() && battery.size() <= 3 &&
            battery.find_first_not_of("0123456789") == std::string::npos &&
            std::stoi(battery) >= 50 && std::stoi(battery) <= 100,"At least 50% battery is required");
}
Fd CleanOta() {
    auto metadata = RealMount("/metadata",false);
    const auto misc = Partition("misc");
    unsigned char message[64]{};
    ReadAt(misc.fd,message,sizeof(message),32 * 1024);
    Require(message[0] == 2 && LE(message+1) == 0x56740AB0 && message[5] == 0,
            "Bootloader OTA merge state is active or cannot be verified");
    auto ota = At(metadata,"ota",O_RDONLY | O_DIRECTORY);
    // Without the same metadata lock used by libsnapshot there is no safe write.
    Require(ota >= 0 && flock(ota,LOCK_SH | LOCK_NB) == 0,"Cannot lock or verify OTA metadata");
    const auto state = MaybeAt(ota,"state");
    Require(CleanOtaState(state),"Virtual A/B snapshot state is not clean");
    for (const auto* name : {"snapshot-boot","snapshot-boot-without-slot-switch",
                             "rollback-indicator","merge_state"})
        Require(!Exists(ota,name),"OTA snapshot artifacts remain; update refused");
    if (Exists(ota,"snapshots")) {
        auto snaps = At(ota,"snapshots",O_RDONLY | O_DIRECTORY);
        Require(snaps >= 0,"Cannot inspect snapshot records");
        std::unique_ptr<DIR,decltype(&closedir)> d(fdopendir(dup(snaps)),closedir);
        Require(bool(d),"Cannot inspect snapshot records");
        for (;;) {
            errno = 0;
            auto* e = readdir(d.get());
            if (!e) { Require(errno == 0,"Cannot read snapshot records"); break; }
            Require(!std::strcmp(e->d_name,".") || !std::strcmp(e->d_name,".."),
                    "OTA snapshot records remain; update refused");
        }
    }
    std::unique_ptr<DIR,decltype(&closedir)> blocks(opendir("/sys/class/block"),closedir);
    Require(bool(blocks),"Cannot inspect active block mappings");
    for (;;) {
        errno = 0;
        auto* e = readdir(blocks.get());
        if (!e) { Require(errno == 0,"Cannot read active block mappings"); break; }
        if (std::strncmp(e->d_name,"dm-",3) != 0) continue;
        const auto name = File(std::string("/sys/class/block/")+e->d_name+"/dm/name",256);
        Require(name.find("-cow") == std::string::npos && name.find("-snapshot") == std::string::npos &&
                name.find("-base") == std::string::npos,"Active OTA snapshot block mappings remain");
    }
    return ota;
}
Fd Storage() {
    auto data = RealMount("/data",true);
    // /data/twrp is shared with ordinary recovery settings. Only its private
    // updater child stores writable updater state; neither may be a symlink.
    if (mkdirat(data,"twrp",0700) && errno != EEXIST) throw std::runtime_error("Cannot create TWRP state directory");
    auto parent = At(data,"twrp",O_RDONLY | O_DIRECTORY);
    struct stat ds{}, ps{}, s{};
    Require(parent >= 0 && !fstat(data,&ds) && !fstat(parent,&ps) && ps.st_uid == 0 &&
            ps.st_dev == ds.st_dev && !(ps.st_mode & 0022),"Unsafe updater state parent");
    if (mkdirat(parent,"updater",0700) && errno != EEXIST) throw std::runtime_error("Cannot create updater state");
    auto dir = At(parent,"updater",O_RDONLY | O_DIRECTORY);
    Require(dir >= 0 && !fstat(dir,&s) && s.st_dev == ds.st_dev && s.st_uid == 0 &&
            (s.st_mode & 0777) == 0700,"Unsafe updater state directory");
    Require(flock(dir,LOCK_EX | LOCK_NB) == 0,"Another recovery update transaction is active");
    return dir;
}
void Receipt(int dir, Json::Value journal, const char* stage) {
    journal["stage"] = stage;
    const auto s = journal.toStyledString();
    auto temp = At(dir,"receipt.tmp",O_CREAT | O_EXCL | O_WRONLY);
    Require(temp >= 0,"Cannot create transaction receipt");
    try {
        Write(temp,s.data(),s.size());
        Require(fsync(temp) == 0 && renameat(dir,"receipt.tmp",dir,"receipt.json") == 0 &&
                fsync(dir) == 0,"Cannot flush transaction receipt");
    } catch (...) { unlinkat(dir,"receipt.tmp",0); throw; }
}
std::string Fetch(const std::string& url, uint64_t limit, int fd = -1, bool api = false) {
    int p[2];
    Require(pipe2(p,O_CLOEXEC) == 0,"Cannot create HTTPS stream");
    Fd read_end(p[0]), write_end(p[1]);
    const auto pid = fork();
    Require(pid >= 0,"Cannot start HTTPS client");
    if (pid == 0) {
        if (dup2(write_end,STDOUT_FILENO) < 0) _exit(127);
        const auto null = Open("/dev/null",O_WRONLY);
        if (null < 0 || dup2(null,STDERR_FILENO) < 0) _exit(127);
        // Ignore ~/.curlrc, process proxy overrides, non-TLS redirects and optional trust overrides.
        const char* argv[] = {"/system/bin/curl","-q","--silent","--fail","--location",
            "--proto","=https","--proto-redir","=https","--tlsv1.2","--max-redirs","4",
            "--cacert","/system/etc/security/cacerts/cacert.pem","--noproxy","*","--interface","wlan0",
            "--connect-timeout","8","--max-time",fd >= 0 ? "600" : "18",
            "--speed-time","20","--speed-limit","128","--user-agent","OP15-TWRP-Update/1",
            "-H",api ? "Accept: application/vnd.github+json" : "Accept: application/octet-stream",
            url.c_str(),nullptr};
        const char* env[] = {"PATH=/system/bin","HOME=/","LANG=C",nullptr};
        execve(argv[0],const_cast<char* const*>(argv),const_cast<char* const*>(env));
        _exit(127);
    }
    close(std::exchange(write_end.n,-1));
    std::string result;
    auto done = uint64_t{0};
    const auto start = time(nullptr);
    int last = -1;
    int status = 0;
    try {
        char buffer[64*1024];
        ssize_t n;
        while ((n = TEMP_FAILURE_RETRY(read(read_end,buffer,sizeof(buffer)))) > 0) {
            Require(static_cast<uint64_t>(n) <= limit-done,"HTTPS response exceeds expected size");
            done += n;
            if (fd < 0) result.append(buffer,n);
            else {
                Write(fd,buffer,n);
                const int pct = static_cast<int>(done*100/limit);
                if (pct != last) {
                    last = pct;
                    Out("progress",std::to_string(pct));
                    Out("speed",std::to_string(done/1024/std::max<time_t>(1,time(nullptr)-start))+" KiB/s");
                }
            }
        }
        Require(n == 0 && TEMP_FAILURE_RETRY(waitpid(pid,&status,0)) == pid,"HTTPS stream failed");
    } catch (...) { kill(pid,SIGKILL); TEMP_FAILURE_RETRY(waitpid(pid,&status,0)); throw; }
    Require(WIFEXITED(status),"HTTPS client interrupted");
    switch (WEXITSTATUS(status)) {
        case 0: break;
        case 6: throw std::runtime_error("GitHub DNS lookup failed");
        case 7: throw std::runtime_error("Cannot reach GitHub; check Wi-Fi and Internet");
        case 22: throw std::runtime_error("GitHub HTTP error or API rate limit");
        case 28: throw std::runtime_error("GitHub HTTPS request timed out");
        case 35: case 60: case 77: throw std::runtime_error("GitHub TLS verification failed");
        default: throw std::runtime_error("HTTPS download failed or was interrupted");
    }
    Require(fd < 0 || done == limit,"Download length differs from signed manifest");
    return result;
}
std::unique_ptr<Offer> Check(const Build& installed, const Digest& pub, Profile profile, bool preview) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(60);
    auto releases = Parse(Fetch(std::string("https://api.github.com/repos/")+Repo+
        "/releases?per_page=20",2 * 1024 * 1024,-1,true));
    auto best = Select(releases,installed,pub,profile,preview,[&](const std::string& url,uint64_t size) {
        Require(std::chrono::steady_clock::now() < deadline,"Timed out checking signed releases");
        return Fetch(url,size);
    });
    Require(std::chrono::steady_clock::now() < deadline,"Timed out checking signed releases");
    return best;
}
struct TempImage {
    int dir;
    const char* name;
    Fd fd;
    TempImage(int d,const char* n) : dir(d),name(n),fd(At(d,n,O_CREAT | O_RDWR | O_EXCL)) {
        Require(fd >= 0,"Cannot create update temporary file (check for interrupted update)");
    }
    ~TempImage() { unlinkat(dir,name,0); }
};
void Install(const Build& running, const Offer& o, const std::string& target,
             const Profile& profile, const Block& original) {
    Power();
    { const auto lock = CleanOta(); }
    const auto policy = RecoveryImage(original.fd);
    auto dir = Storage();
    Require(!Exists(dir,"receipt.json") && !Exists(dir,"receipt.tmp"),
            "An earlier update needs inspection or boot confirmation");
    // With no receipt, the earlier attempt did not open the write phase. Only
    // known temporary names in the private, locked directory are cleaned up.
    for (const auto* name : {"download.part","rollback.part"})
        if (Exists(dir,name)) Require(unlinkat(dir,name,0) == 0,"Cannot clean interrupted download");
    struct statvfs fs{};
    Require(fstatvfs(dir,&fs) == 0 && fs.f_frsize > 0 &&
            fs.f_bavail >= (2*ImageSize + 16*1024*1024)/fs.f_frsize + 1,
            "Not enough mounted Data space for download and rollback");
    TempImage img(dir,"download.part");
    Out("status","Downloading TWRP update");
    try { Fetch(o.url,ImageSize,img.fd); }
    catch (const std::exception&) {
        // A retry starts from an empty file. Curl's automatic stream retries
        // cannot safely rewind a pipe that has already delivered data.
        Require(GetProperty("twrp.wifi.connected","0") == "1","Wi-Fi disconnected during download");
        Require(ftruncate(img.fd,0) == 0 && lseek(img.fd,0,SEEK_SET) == 0,"Cannot reset interrupted download");
        Out("status","Retrying interrupted download once");
        Out("progress","0");
        Fetch(o.url,ImageSize,img.fd);
    }
    Out("status","Verifying signed recovery image");
    Require(fsync(img.fd) == 0 && Hash(img.fd,ImageSize) == o.sha,"Downloaded recovery SHA-256 mismatch");
    Require(RecoveryImage(img.fd) == policy,"Recovery AVB policy differs from the installed recovery");
    const auto lock = CleanOta();
    Power();
    Require(ActiveTarget() == target && Probe(target,original) == profile,
            "Boot slot or firmware changed during download");
    const auto rollback_name = target+"-build-"+std::to_string(running.id)+".img";
    if (!Exists(dir,rollback_name.c_str())) {
        TempImage pending(dir,"rollback.part");
        Out("status","Saving verified recovery rollback");
        Require(Stream(original.fd,pending.fd,ImageSize,[](uint64_t,uint64_t){}) == Unhex(profile.from_recovery) &&
                fsync(pending.fd) == 0 && Hash(pending.fd,ImageSize) == Unhex(profile.from_recovery) &&
                linkat(dir,pending.name,dir,rollback_name.c_str(),0) == 0 && fsync(dir) == 0,
                "Failed to save a verified rollback image");
    }
    const auto rollback = At(dir,rollback_name.c_str());
    struct stat rs{};
    Require(rollback >= 0 && fstat(rollback,&rs) == 0 && S_ISREG(rs.st_mode) &&
            rs.st_size == static_cast<off_t>(ImageSize) &&
            Hash(rollback,ImageSize) == Unhex(profile.from_recovery),"Rollback file is not intact");
    Power();
    const auto final_ota_lock = CleanOta();
    Require(ActiveTarget() == target,"Active slot changed before installation");
    const auto dest = Partition(target,true);
    Require(dest.dev == original.dev && Hash(dest.fd,ImageSize) == Unhex(profile.from_recovery),
            "Active recovery partition changed before installation");
    Json::Value journal(Json::objectValue);
    journal["build"] = Json::UInt64(o.build.id);
    journal["commit"] = o.build.commit;
    journal["slot"] = profile.slot;
    journal["boot_id"] = File("/proc/sys/kernel/random/boot_id",80);
    journal["sha256"] = Hex(o.sha);
    journal["rollback"] = rollback_name;
    journal["rollback_sha256"] = profile.from_recovery;
    Receipt(dir,journal,"writing");
    int last = -1;
    auto progress = [&](uint64_t a,uint64_t b) {
        int pct = a*100/b;
        if (pct != last) { last = pct; Out("progress",std::to_string(pct)); }
    };
    WriteAndVerify(img.fd,dest.fd,ImageSize,o.sha,[&](bool readback) {
        Out("status",readback ? "Reading back the entire recovery partition" : "Installing " + target);
        Out("progress","0");
        last = -1;
    },progress,[](int fd) { return fsync(fd) == 0 && ioctl(fd,BLKFLSBUF,0) == 0; });
    Receipt(dir,journal,"verified");
    Out("status","Installation verified; restarting recovery");
    Out("verified","1");
}
void Confirm(const Build& running) {
    // The state directory may not be available before FBE and mount setup.
    auto dir = Storage();
    if (!Exists(dir,"receipt.json")) return;
    auto receipt = Parse(MaybeAt(dir,"receipt.json"));
    Require(String(receipt,"stage",32) == "verified",
            "Interrupted installation: keep recovery running and inspect the rollback");
    // Never consume a verified receipt during the same boot that wrote it.
    if (String(receipt,"boot_id",80) == File("/proc/sys/kernel/random/boot_id",80)) return;
    Require(Number(receipt,"build") == running.id,
            "The expected updated recovery did not boot; leave the rollback intact");
    const auto target = ActiveTarget();
    const auto p = Partition(target);
    Require(RebootVerified(running.id,running.commit,target.substr(8),Hash(p.fd,p.bytes),receipt),
            "Running recovery does not match verified update receipt");
    Require(renameat(dir,"receipt.json",dir,"last-success.json") == 0 && fsync(dir) == 0,
            "Unable to consume verified update receipt");
    Out("success","Recovery updated successfully");
}
}

int main(int argc, char** argv) {
    try {
        const auto identity = Parse(File(IdentityFile,4096));
        const auto running = Identity(identity);
        Out("installed",std::string(Version)+" / build "+std::to_string(running.id)+" ("+
            running.commit.substr(0,12)+")");
        Require(argc >= 2,"Missing updater operation");
        const std::string mode = argv[1];
        if (mode == "info" && argc == 2) {
            const auto target = ActiveTarget();
            Out("target",target);
            Out("slot",target.back() == 'a' ? "A" : "B");
            return 0;
        }
        if (mode == "confirm" && argc == 2) {
            if (running.id > 0 && identity["public_key"].isString() &&
                IsHex(identity["public_key"].asString(),64)) Confirm(running);
            return 0;
        }
        Require((mode == "check" && argc == 3) || (mode == "install" && argc == 4),
                "Unknown updater operation");
        const auto target = ActiveTarget();
        Out("target",target);
        Out("slot",target.substr(9) == "a" ? "A" : "B");
        Require(running.id > 0 && identity["public_key"].isString() &&
                IsHex(identity["public_key"].asString(),64),"This build has no trusted updater key");
        Require(GetProperty("twrp.wifi.connected","0") == "1","Offline — connect to Wi-Fi");
        const auto recovery = Partition(target);
        const auto profile = Probe(target,recovery);
        const bool preview = !std::strcmp(argv[2],"preview");
        Out("status","Checking GitHub Releases");
        auto offer = Check(running,Unhex(identity["public_key"].asString()),profile,preview);
        if (!offer) {
            Require(mode == "check","Previously selected update is no longer eligible");
            Out("state","current");
            Out("status","No newer signed compatible recovery");
            return 0;
        }
        const auto id = std::to_string(offer->build.id);
        Out("available",offer->tag+" / build "+id);
        Out("notes",offer->notes);
        if (mode == "install") {
            Require(offer->Token() == argv[3],"Release changed; check again before installing");
            Install(running,*offer,target,profile,recovery);
        } else {
            // Do not turn green if even the running recovery fails AVB preflight.
            RecoveryImage(recovery.fd);
            Out("offer",offer->Token());
            Out("status","A signed compatible recovery update is available");
            Out("state","available");
        }
        return 0;
    } catch (const std::exception& e) {
        Out("error",e.what());
        return 1;
    }
}
