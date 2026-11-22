// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <json/json.h>
#include <openssl/evp.h>
#include <unistd.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <sys/types.h>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace op15_update {
constexpr uint64_t ImageSize = 100 * 1024 * 1024;
constexpr char Repo[] = "travismills82/twrp_device_oplus_infiniti";
constexpr char Device[] = "infiniti";
constexpr char Version[] = "3.7.1-16";
constexpr char ImageAsset[] = "recovery.img";
constexpr char ManifestAsset[] = "twrp-update.json";
constexpr char SignatureAsset[] = "twrp-update.json.sig";
using Digest = std::array<unsigned char, 32>;
using Md = std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)>;
using Key = std::unique_ptr<EVP_PKEY, decltype(&EVP_PKEY_free)>;

inline void Require(bool ok, const char* reason) {
    if (!ok) throw std::runtime_error(reason);
}
inline bool IsHex(std::string_view s, size_t n) {
    return s.size() == n && s.find_first_not_of("0123456789abcdef") == std::string_view::npos;
}
inline unsigned Nibble(char c) { return c <= '9' ? c - '0' : c - 'a' + 10; }
inline Digest Unhex(std::string_view s) {
    Require(IsHex(s, 64), "Invalid SHA-256 or public key");
    Digest out{};
    for (size_t i = 0; i < out.size(); ++i) out[i] = (Nibble(s[i*2]) << 4) | Nibble(s[i*2+1]);
    return out;
}
inline std::string Hex(const Digest& v) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string result;
    for (auto b : v) { result += digits[b >> 4]; result += digits[b & 15]; }
    return result;
}
inline Json::Value Parse(const std::string& s) {
    Json::CharReaderBuilder b;
    Json::CharReaderBuilder::strictMode(&b.settings_);
    b["stackLimit"] = 16;
    b["rejectDupKeys"] = true;
    b["failIfExtra"] = true;
    b["allowComments"] = false;
    b["collectComments"] = false;
    Json::Value result;
    const std::unique_ptr<Json::CharReader> reader(b.newCharReader());
    Require(!s.empty() && reader->parse(s.data(), s.data()+s.size(), &result, nullptr),
            "Invalid JSON");
    return result;
}
inline std::string String(const Json::Value& v, const char* key, size_t max) {
    Require(v.isObject() && v[key].isString(), "Missing string field");
    auto s = v[key].asString();
    Require(!s.empty() && s.size() <= max, "Invalid string field");
    return s;
}
inline uint64_t Number(const Json::Value& v, const char* key) {
    Require(v.isObject() && v[key].isUInt64(), "Missing integer field");
    return v[key].asUInt64();
}
inline bool Tag(std::string_view tag) {
    return !tag.empty() && tag.size() <= 96 && tag != "." && tag != ".." &&
        tag.find_first_not_of("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_.") ==
            std::string_view::npos;
}
inline bool Slot(std::string_view slot) { return slot == "_a" || slot == "_b"; }
inline std::string Target(std::string_view property, std::string_view bootconfig,
                          std::string_view cmdline) {
    Require(Slot(property) && (!bootconfig.empty() || !cmdline.empty()) &&
            (bootconfig.empty() || bootconfig == property) &&
            (cmdline.empty() || cmdline == property), "Bootloader slot is missing or inconsistent");
    return "recovery" + std::string(property);
}
struct Build {
    uint64_t id, timestamp;
    std::string commit, channel;
};
inline Build Identity(const Json::Value& v) {
    Require(Number(v, "schema") == 1 && String(v, "device", 32) == Device &&
            String(v, "twrp", 32) == Version && Number(v, "partition_bytes") == ImageSize &&
            String(v, "compatibility", 40) == "op15-dedicated-ab-recovery-v1",
            "Wrong device, image format or updater protocol");
    Build b{Number(v, "build"), Number(v, "timestamp"),
            String(v, "commit", 40), String(v, "channel", 16)};
    Require(IsHex(b.commit, 40) && (b.channel == "stable" || b.channel == "prerelease" ||
            b.channel == "development"), "Invalid build identity");
    return b;
}
struct Profile {
    std::string project, slot, boot, init_boot, vendor_boot, dtbo, vbmeta, from_recovery;
    bool operator==(const Profile& o) const {
        return project == o.project && slot == o.slot && boot == o.boot && init_boot == o.init_boot &&
            vendor_boot == o.vendor_boot && dtbo == o.dtbo && vbmeta == o.vbmeta &&
            from_recovery == o.from_recovery;
    }
};
inline Profile Compatibility(const Json::Value& v) {
    Profile p{String(v,"project",8),String(v,"slot",2),String(v,"boot",64),
        String(v,"init_boot",64),String(v,"vendor_boot",64),String(v,"dtbo",64),
        String(v,"vbmeta",64),String(v,"from_recovery",64)};
    Require((p.project == "24831" || p.project == "24863") && Slot(p.slot) &&
            IsHex(p.boot,64) && IsHex(p.init_boot,64) && IsHex(p.vendor_boot,64) &&
            IsHex(p.dtbo,64) && IsHex(p.vbmeta,64) &&
            IsHex(p.from_recovery,64), "Invalid compatibility profile");
    return p;
}
struct Offer {
    Build build;
    std::string tag, url, notes;
    Digest sha;
    std::vector<Profile> profiles;
    std::string Token() const { return std::to_string(build.id) + ":" + Hex(sha); }
};
inline void Verify(const std::string& raw, const std::string& signature, const Digest& pub) {
    Require(raw.size() <= 32768 && signature.size() == 64, "Invalid signed manifest size");
    Key k(EVP_PKEY_new_raw_public_key(EVP_PKEY_ED25519, nullptr, pub.data(), pub.size()),
          EVP_PKEY_free);
    Md ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free);
    Require(k && ctx && EVP_DigestVerifyInit(ctx.get(), nullptr, nullptr, nullptr, k.get()) == 1 &&
            EVP_DigestVerify(ctx.get(), reinterpret_cast<const unsigned char*>(signature.data()), 64,
                reinterpret_cast<const unsigned char*>(raw.data()), raw.size()) == 1,
            "Manifest signature verification failed");
}
inline Offer Manifest(const std::string& raw, const std::string& signature, const Digest& key) {
    Verify(raw, signature, key);
    auto v = Parse(raw);
    Offer o{Identity(v),String(v,"tag",96),{},String(v,"notes",3072),Unhex(String(v,"sha256",64)),{}};
    Require(Tag(o.tag) && o.build.id > 0 && o.build.timestamp > 0 &&
            o.build.channel != "development" && String(v,"asset",32) == ImageAsset,
            "Invalid release identity or image asset");
    Require(v["profiles"].isArray() && v["profiles"].size() >= 1 && v["profiles"].size() <= 24,
            "Release has no bounded compatibility list");
    for (const auto& p : v["profiles"]) o.profiles.push_back(Compatibility(p));
    return o;
}
inline bool Eligible(const Offer& o, const Build& current, const Profile& p, bool preview) {
    return current.id > 0 && o.build.id > current.id &&
        (o.build.channel == "stable" || (preview && o.build.channel == "prerelease")) &&
        std::find(o.profiles.begin(), o.profiles.end(), p) != o.profiles.end();
}
inline std::string AssetURL(const std::string& tag, const char* asset) {
    return std::string("https://github.com/") + Repo + "/releases/download/" + tag + "/" + asset;
}
template <class Fetch>
std::unique_ptr<Offer> Select(const Json::Value& releases, const Build& installed,
                              const Digest& pub, const Profile& profile, bool preview, Fetch fetch) {
    Require(releases.isArray() && releases.size() <= 20,"Invalid GitHub release list");
    std::unique_ptr<Offer> best;
    std::string last_error;
    for (const auto& release : releases) {
        if (!release.isObject() || !release["draft"].isBool() || release["draft"].asBool() ||
            !release["prerelease"].isBool() || (!preview && release["prerelease"].asBool()) ||
            !release["tag_name"].isString() || !release["assets"].isArray()) continue;
        const auto tag = release["tag_name"].asString();
        if (!Tag(tag)) continue;
        unsigned image=0, manifest=0, sig=0;
        for (const auto& a : release["assets"]) {
            if (!a.isObject() || !a["name"].isString() || !a["state"].isString() ||
                a["state"].asString() != "uploaded" || !a["browser_download_url"].isString() ||
                !a["size"].isUInt64()) continue;
            const auto name = a["name"].asString();
            if (name != ImageAsset && name != ManifestAsset && name != SignatureAsset) continue;
            if (a["browser_download_url"].asString() != AssetURL(tag,name.c_str())) continue;
            auto len = a["size"].asUInt64();
            if (name == ImageAsset && len == ImageSize) ++image;
            if (name == ManifestAsset && len > 0 && len <= 32768) ++manifest;
            if (name == SignatureAsset && len == 64) ++sig;
        }
        if (image != 1 || manifest != 1 || sig != 1) continue;
        try {
            auto raw = fetch(AssetURL(tag,ManifestAsset),32768);
            auto sig_bytes = fetch(AssetURL(tag,SignatureAsset),64);
            auto o = Manifest(raw,sig_bytes,pub);
            Require(o.tag == tag && ((o.build.channel == "prerelease") == release["prerelease"].asBool()),
                    "Signed manifest does not match its GitHub release");
            if (Eligible(o,installed,profile,preview) && (!best || o.build.id > best->build.id)) {
                o.url = AssetURL(tag,ImageAsset);
                best = std::make_unique<Offer>(std::move(o));
            }
        } catch (const std::exception& e) { last_error = e.what(); }
    }
    Require(best || last_error.empty(),last_error.c_str());
    return best;
}
inline bool CleanOtaState(const std::string& state) {
    return state.empty() || state == "none" || state == std::string("\x08\x00",2);
}
template <class Sink>
uint64_t Receive(int source,uint64_t bound,bool exact,Sink consume) {
    char buffer[64 * 1024];
    uint64_t done = 0;
    for (;;) {
        ssize_t n;
        do { n = read(source,buffer,sizeof(buffer)); } while (n < 0 && errno == EINTR);
        Require(n >= 0,"HTTPS stream failed");
        if (!n) break;
        Require(static_cast<uint64_t>(n) <= bound-done,"HTTPS response exceeds expected size");
        done += n;
        consume(buffer,static_cast<size_t>(n),done);
    }
    Require(!exact || done == bound,"Download length differs from signed manifest");
    return done;
}
inline bool RebootVerified(uint64_t running, std::string_view commit, std::string_view slot,
                           const Digest& readback, const Json::Value& receipt) {
    return String(receipt,"stage",32) == "verified" && Number(receipt,"build") == running &&
        String(receipt,"commit",40) == commit && String(receipt,"slot",2) == slot &&
        Unhex(String(receipt,"sha256",64)) == readback;
}
template <class Progress>
Digest Stream(int input, int output, uint64_t size, Progress callback,
              const std::string& salt = {}) {
    Md ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free);
    Require(ctx && EVP_DigestInit_ex(ctx.get(), EVP_sha256(), nullptr) == 1, "Cannot initialize SHA-256");
    if (!salt.empty()) Require(EVP_DigestUpdate(ctx.get(), salt.data(), salt.size()) == 1, "SHA-256 failed");
    std::vector<unsigned char> buffer(256 * 1024);
    uint64_t done = 0;
    while (done < size) {
        const auto chunk = static_cast<size_t>(std::min<uint64_t>(size-done, buffer.size()));
        ssize_t n;
        do { n = pread(input, buffer.data(), chunk, done); } while (n < 0 && errno == EINTR);
        Require(n > 0 && static_cast<size_t>(n) <= chunk, "Short read or read error");
        Require(EVP_DigestUpdate(ctx.get(),buffer.data(),n) == 1,"SHA-256 failed");
        if (output >= 0) {
            ssize_t written = 0;
            while (written < n) {
                ssize_t w = pwrite(output,buffer.data()+written,n-written,done+written);
                if (w < 0 && errno == EINTR) continue;
                Require(w > 0 && w <= n-written, "Short write or write error");
                written += w;
            }
        }
        done += n;
        callback(done,size);
    }
    Digest digest{};
    unsigned length = 0;
    Require(EVP_DigestFinal_ex(ctx.get(),digest.data(),&length) == 1 && length == digest.size(),
            "SHA-256 finalization failed");
    return digest;
}
inline Digest Hash(int fd, uint64_t size, const std::string& salt = {}) {
    return Stream(fd,-1,size,[](uint64_t,uint64_t){},salt);
}
template <class Stage, class Progress, class Flush>
void WriteAndVerify(int input, int target, uint64_t bytes, const Digest& digest,
                    Stage stage, Progress progress, Flush flush) {
    stage(false);
    Require(Stream(input,target,bytes,progress) == digest && flush(target),
            "Write or block-cache flush failed; do not reboot");
    stage(true);
    Require(Stream(target,-1,bytes,progress) == digest,
            "Full recovery partition readback mismatch; do not reboot");
}
}
