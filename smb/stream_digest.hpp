// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <openssl/evp.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <fcntl.h>
#include <memory>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <sys/xattr.h>
#include <unistd.h>
#include <vector>

namespace op15_smb {
constexpr char WrittenDigestAttr[] = "user.twrp.written-sha256";
constexpr size_t DigestReadBytes = 256 * 1024;
using WriteReceipt = std::array<unsigned char, 40>; // little-endian length + binary SHA-256

inline bool DigestArchivePath(std::string_view path) {
    const auto name = path.substr(path.rfind('/') + 1);
    const auto marker = name.rfind(".win");
    if (marker == std::string_view::npos || marker == 0) return false;
    const auto suffix = name.substr(marker + 4);
    return suffix.empty() || (suffix.size() == 3 && std::all_of(suffix.begin(), suffix.end(),
        [](char c) { return c >= '0' && c <= '9'; }));
}

class Sha256Stream {
public:
    Sha256Stream() : context(EVP_MD_CTX_new(), EVP_MD_CTX_free) {
        valid = context && EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr) == 1;
    }
    void Append(uint64_t offset, const void* data, size_t count) {
        if (!valid || offset != bytes || count > UINT64_MAX - bytes ||
            EVP_DigestUpdate(context.get(), data, count) != 1) {
            valid = false;
            return;
        }
        bytes += count;
    }
    void Invalidate() { valid = false; }
    bool Finish(WriteReceipt* receipt) const {
        if (!valid || bytes == 0) return false;
        std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> snapshot(EVP_MD_CTX_new(), EVP_MD_CTX_free);
        unsigned length = 0;
        if (!snapshot || EVP_MD_CTX_copy_ex(snapshot.get(), context.get()) != 1 ||
            EVP_DigestFinal_ex(snapshot.get(), receipt->data() + 8, &length) != 1 || length != 32) return false;
        for (size_t i = 0; i < 8; ++i) (*receipt)[i] = static_cast<unsigned char>(bytes >> (8 * i));
        return true;
    }

private:
    std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> context;
    bool valid = false;
    uint64_t bytes = 0;
};

inline uint64_t ReceiptLength(const WriteReceipt& receipt) {
    uint64_t bytes = 0;
    for (size_t i = 0; i < 8; ++i) bytes |= static_cast<uint64_t>(receipt[i]) << (8 * i);
    return bytes;
}

inline std::string DigestHex(const WriteReceipt& receipt) {
    constexpr char hex[] = "0123456789abcdef";
    std::string result;
    result.reserve(64);
    for (auto it = receipt.begin() + 8; it != receipt.end(); ++it) {
        result.push_back(hex[*it >> 4]);
        result.push_back(hex[*it & 15]);
    }
    return result;
}

inline bool MatchReadback(int fd, const WriteReceipt& expected) {
    const uint64_t size = ReceiptLength(expected);
    if (size == 0) return false;
    Sha256Stream stream;
    std::vector<unsigned char> buffer(DigestReadBytes);
    uint64_t bytes = 0;
    for (;;) {
        const ssize_t count = read(fd, buffer.data(), buffer.size());
        if (count < 0 && errno == EINTR) continue;
        if (count < 0 || static_cast<uint64_t>(count) > size - bytes) return false;
        if (!count) break;
        stream.Append(bytes, buffer.data(), count);
        bytes += count;
    }
    WriteReceipt observed{};
    return bytes == size && stream.Finish(&observed) && observed == expected;
}

inline bool ReadbackAndSaveDigest(const std::string& archive) {
    const int fd = open(archive.c_str(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return false;
    struct stat file {};
    WriteReceipt expected{};
    bool ok = fstat(fd, &file) == 0 && S_ISREG(file.st_mode) && file.st_size > 0 &&
        fgetxattr(fd, WrittenDigestAttr, expected.data(), expected.size()) == static_cast<ssize_t>(expected.size()) &&
        ReceiptLength(expected) == static_cast<uint64_t>(file.st_size) && MatchReadback(fd, expected);
    ok = close(fd) == 0 && ok;
    if (!ok) return false;
    const std::string contents = DigestHex(expected) + "  " + archive.substr(archive.rfind('/') + 1) + "\n";
    const std::string path = archive + ".sha2";
    const int checksum = open(path.c_str(), O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (checksum < 0) return false;
    size_t done = 0;
    while (done < contents.size()) {
        const auto count = write(checksum, contents.data() + done, contents.size() - done);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) break;
        done += count;
    }
    ok = done == contents.size() && fsync(checksum) == 0;
    // Check only the small sidecar too; the archive is never read twice.
    std::vector<char> sidecar(contents.size() + 1);
    size_t received = 0;
    while (ok && received < sidecar.size()) {
        const auto count = pread(checksum, sidecar.data() + received, sidecar.size() - received, received);
        if (count < 0 && errno == EINTR) continue;
        if (count < 0) ok = false;
        if (count <= 0) break;
        received += count;
    }
    if (ok) {
        ok = received == contents.size() &&
            std::equal(contents.begin(), contents.end(), sidecar.begin());
    }
    ok = close(checksum) == 0 && ok;
    if (!ok) unlink(path.c_str());
    return ok;
}
}
