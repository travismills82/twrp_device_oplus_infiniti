/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include "backup_safety.hpp"

int main(int argc, char** argv) {
    assert(argc == 2); // A disposable test directory, never /sys or /dev.
    const std::filesystem::path root(argv[1]);
    assert(root.string().find("/tmp/") == 0);
    using namespace twrp_backup_safety;
    constexpr uint64_t MiB = 1024 * 1024;
    assert(!HasCapacity(0, 1));
    assert(!HasCapacity(31 * MiB, 1));
    assert(HasCapacity(33 * MiB, MiB));
    assert(!HasCapacity(33 * MiB, MiB + 1));
    assert(!ImageLengthValid(0, 100));
    assert(!ImageLengthValid(99, 100));
    assert(!ImageLengthValid(101, 100));
    assert(ImageLengthValid(100, 100));
    assert(ImageLengthValid(500ULL * 1024 * MiB, 500ULL * 1024 * MiB));
    unsigned char bytes[8] {};
    int calls = 0;
    size_t transferred = 0;
    assert(ExactIo(bytes, sizeof(bytes), [&](void* cursor, size_t remaining) -> ssize_t {
        if (++calls == 1) { errno = EINTR; return -1; }
        assert(cursor == bytes + transferred);
        const size_t partial = std::min<size_t>(2, remaining);
        transferred += partial;
        return partial;
    }));
    assert(transferred == 8 && calls == 5);
    assert(!ExactIo(bytes, 8, [](void*, size_t) -> ssize_t { return 0; }));
    assert(errno == EIO);
    assert(!ExactIo(bytes, 8, [](void*, size_t) -> ssize_t { errno = ENOSPC; return -1; }));
    assert(errno == ENOSPC);

    const auto sys = root / "sys";
    const auto mounts = root / "mountinfo";
    std::filesystem::create_directories(sys / "dev/block/8:1/holders");
    std::filesystem::create_directories(sys / "dev/block/253:0/holders");
    auto mount = [&](const std::string& text) { std::ofstream file(mounts); file << text; };
    const std::string root_mount = "1 0 0:1 / / ro - rootfs rootfs ro\n";
    auto safe = [&](bool restore) {
        std::string error;
        return BlockIsSafe("8:1", restore, &error, sys.string(), mounts.string());
    };
    mount(root_mount);
    assert(safe(false) && safe(true));
    mount(root_mount + "2 1 8:1 / /vendor ro,relatime - erofs /dev/block/test ro\n");
    assert(safe(false) && !safe(true));
    mount(root_mount + "2 1 8:1 / /data rw,relatime - f2fs /dev/block/test rw\n");
    assert(!safe(false) && !safe(true));
    std::filesystem::create_directories(sys / "dev/block/8:1/holders/dm-0");
    { std::ofstream file(sys / "dev/block/8:1/holders/dm-0/dev"); file << "253:0\n"; }
    mount(root_mount);
    assert(safe(false) && !safe(true));
    mount(root_mount + "2 1 253:0 / /data rw,relatime - f2fs /dev/block/dm-0 rw\n");
    assert(!safe(false) && !safe(true));
    mount("");
    assert(!safe(false) && !safe(true));
    mount("corrupt mount record\n");
    assert(!safe(false) && !safe(true));
    std::filesystem::remove(sys / "dev/block/8:1/holders/dm-0/dev");
    mount(root_mount);
    assert(!safe(false));

    // Bind aliases must not hide recursion, but same-filesystem sibling
    // directories (for example .android_secure and TWRP) remain usable.
    std::filesystem::create_directories(root / "data/media/0/TWRP");
    std::filesystem::create_directories(root / "data/app/backups");
    std::filesystem::create_directories(root / "media_alias");
    struct stat storage {};
    assert(stat((root / "data").c_str(), &storage) == 0);
    const auto device = DeviceId(storage.st_dev);
    mount("1 0 " + device + " / " + (root / "data").string() + " rw - f2fs test rw\n" +
          "2 1 " + device + " /media/0 " + (root / "media_alias").string() + " rw - f2fs test rw\n");
    std::string error;
    assert(!SafeFileBackup((root / "media_alias").string(), (root / "data/media/0/TWRP").string(), &error, mounts.string()));
    assert(!SafeFileBackup((root / "data/app").string(), (root / "data/app/backups").string(), &error, mounts.string()));
    assert(SafeFileBackup((root / "data/app").string(), (root / "data/media/0/TWRP").string(), &error, mounts.string()));
    assert(ContainsPath("/media/0", "/media/0/TWRP"));
    assert(!ContainsPath("/media/0", "/media/01/TWRP"));
    assert(MountUnescape("/USB\\040Disk") == "/USB Disk");
    std::cout << "Native backup length, capacity, short I/O, mount and mapper guards passed\n";
}
