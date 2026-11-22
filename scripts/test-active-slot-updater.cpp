// SPDX-License-Identifier: Apache-2.0
#include "../updater/core.hpp"
#include <cassert>
#include <fcntl.h>
#include <iostream>
#include <map>

using namespace op15_update;
using namespace std::string_literals;
namespace {
template <class Fn> void Reject(Fn f) {
    try { f(); } catch (const std::runtime_error&) { return; }
    assert(!"Unsafe operation unexpectedly accepted");
}
struct File {
    int fd;
    explicit File(const std::string& path) : fd(open(path.c_str(),O_CREAT | O_EXCL | O_RDWR,0600)) { assert(fd >= 0); }
    ~File() { close(fd); }
};
Json::Value IdentityJson(uint64_t n, const char* channel) {
    Json::Value v(Json::objectValue);
    v["schema"]=1u; v["device"]=Device; v["twrp"]=Version; v["partition_bytes"]=Json::UInt64(ImageSize);
    v["compatibility"]="op15-dedicated-ab-recovery-v1"; v["build"]=Json::UInt64(n); v["timestamp"]=1u;
    v["commit"]=std::string(40,'c'); v["channel"]=channel;
    return v;
}
Json::Value ProfileJson(const Profile& p) {
    Json::Value v;
    v["project"]=p.project; v["slot"]=p.slot; v["boot"]=p.boot; v["init_boot"]=p.init_boot;
    v["vendor_boot"]=p.vendor_boot; v["dtbo"]=p.dtbo;
    v["vbmeta"]=p.vbmeta; v["from_recovery"]=p.from_recovery;
    return v;
}
struct Signer {
    Key key{nullptr,EVP_PKEY_free};
    Digest pub{};
    explicit Signer(unsigned char seed) {
        Digest secret{};
        secret.fill(seed);
        key.reset(EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519,nullptr,secret.data(),secret.size()));
        auto size = pub.size();
        assert(key && EVP_PKEY_get_raw_public_key(key.get(),pub.data(),&size) == 1 && size == pub.size());
    }
    std::string Sign(const std::string& data) const {
        std::string sig(64,0);
        size_t n=sig.size();
        Md ctx(EVP_MD_CTX_new(),EVP_MD_CTX_free);
        assert(EVP_DigestSignInit(ctx.get(),nullptr,nullptr,nullptr,key.get()) == 1 &&
               EVP_DigestSign(ctx.get(),reinterpret_cast<unsigned char*>(sig.data()),&n,
                   reinterpret_cast<const unsigned char*>(data.data()),data.size()) == 1 && n == sig.size());
        return sig;
    }
};
void Releases() {
    Signer good(3), wrong(7);
    Profile p{"24863","_a",std::string(64,'a'),std::string(64,'a'),std::string(64,'b'),
              std::string(64,'b'),std::string(64,'c'),std::string(64,'d')};
    const auto running=Identity(IdentityJson(10,"stable"));
    Json::Value releases(Json::arrayValue);
    std::map<std::string,std::string> network;
    auto fixture = [&](unsigned build,const std::string& tag,bool preview=false,bool draft=false,
                       bool wrong_key=false,const std::string& device=Device,bool omit_image=false,
                       bool off_host=false,bool wrong_slot=false) {
        auto manifest=IdentityJson(build,preview?"prerelease":"stable");
        manifest["device"]=device;
        manifest["tag"]=tag; manifest["notes"]="A test build"; manifest["asset"]=ImageAsset;
        manifest["sha256"]=std::string(64,'e'); manifest["profiles"].append(ProfileJson(p));
        if (wrong_slot) manifest["profiles"][0]["slot"]="_b";
        auto raw=manifest.toStyledString();
        network[AssetURL(tag,ManifestAsset)]=raw;
        network[AssetURL(tag,SignatureAsset)]=(wrong_key?wrong:good).Sign(raw);
        Json::Value release;
        release["draft"]=draft; release["prerelease"]=preview; release["tag_name"]=tag;
        auto asset=[&](const char* name,uint64_t n) {
            Json::Value a;
            a["name"]=name; a["state"]="uploaded"; a["size"]=Json::UInt64(n);
            a["browser_download_url"]=off_host?"https://evil.example/recovery.img":AssetURL(tag,name);
            release["assets"].append(a);
        };
        if (!omit_image) asset(ImageAsset,ImageSize);
        asset(ManifestAsset,raw.size()); asset(SignatureAsset,64);
        releases.append(release);
    };
    fixture(100,"wrong-key",false,false,true);
    fixture(99,"draft",false,true);
    fixture(98,"another-device",false,false,false,"other");
    fixture(97,"missing-image",false,false,false,Device,true);
    fixture(96,"wrong-asset-host",false,false,false,Device,false,true);
    fixture(95,"different-slot",false,false,false,Device,false,false,true);
    fixture(18,"stable-last");
    fixture(21,"preview",true);
    fixture(19,"stable-newest");
    fixture(10,"already-installed");
    fixture(9,"downgrade");
    auto fetch=[&](const std::string& url,uint64_t cap) {
        assert(network.count(url) && network.at(url).size() <= cap);
        return network.at(url);
    };
    assert(Select(releases,running,good.pub,p,false,fetch)->build.id == 19);
    assert(Select(releases,running,good.pub,p,true,fetch)->build.id == 21);
    assert(!Select(Json::Value(Json::arrayValue),running,good.pub,p,false,fetch));
    Json::Value old(Json::arrayValue); old.append(releases[9]); old.append(releases[10]);
    assert(!Select(old,running,good.pub,p,false,fetch));
    const auto raw=network[AssetURL("stable-newest",ManifestAsset)];
    const auto sig=network[AssetURL("stable-newest",SignatureAsset)];
    Reject([&]{ Manifest(raw+" ",sig,good.pub); });
    Reject([&]{ Manifest(raw,sig.substr(1),good.pub); });
    Reject([&]{ Manifest(raw,sig,wrong.pub); });
    Reject([&]{ Parse("{\"duplicate\":1,\"duplicate\":2}"); });
    auto selected=Manifest(raw,sig,good.pub);
    assert(selected.Token()=="19:"+std::string(64,'e'));
    p.from_recovery.replace(0,1,"0");
    assert(!Eligible(selected,running,p,false));
    assert(!Tag("../escape") && !Tag("one?redirect") && Tag("date-123-1"));
}
void Partitions(const std::string& root) {
    assert(Target("_a","_a","")=="recovery_a");
    assert(Target("_b","","_b")=="recovery_b");
    for (auto property : {"","a","_c","_a/../boot"})
        Reject([&]{ Target(property,"_a","_a"); });
    Reject([]{ Target("_a","_b",""); });
    Reject([]{ Target("_b","_b","_a"); });
    Reject([]{ Target("_a","",""); });
    assert(CleanOtaState("") && CleanOtaState("none") && CleanOtaState("\x08\x00"s));
    assert(!CleanOtaState("merging") && !CleanOtaState("unverified") && !CleanOtaState("\x08\x02"s));
    File source(root+"/payload"), a(root+"/recovery_a"), b(root+"/recovery_b");
    constexpr uint64_t size=5*1024*1024+129;
    for (auto fd : {source.fd,a.fd,b.fd}) assert(ftruncate(fd,size)==0);
    assert(pwrite(source.fd,"image",5,0)==5 && pwrite(source.fd,"end",3,size-3)==3);
    const auto digest=Hash(source.fd,size), untouched=Hash(a.fd,size);
    bool readback=false, wrote=false;
    const auto stage=[&](bool verifying){ wrote |= !verifying; readback=verifying; };
    const auto progress=[](uint64_t n,uint64_t all){ assert(n<=all && all==size); };
    const auto flush=[](int fd){ return fsync(fd)==0; };
    // Disposable partitions use the same write, flush and complete-readback
    // function that recovery uses. Both directions leave the inactive fixture intact.
    auto target=[&](const char* slot)->int { return Target(slot,slot,"")=="recovery_a"?a.fd:b.fd; };
    WriteAndVerify(source.fd,target("_b"),size,digest,stage,progress,flush);
    assert(wrote && readback && Hash(b.fd,size)==digest && Hash(a.fd,size)==untouched);
    assert(pwrite(source.fd,"new image",9,0)==9);
    const auto second=Hash(source.fd,size);
    WriteAndVerify(source.fd,target("_a"),size,second,stage,progress,flush);
    assert(Hash(a.fd,size)==second && Hash(b.fd,size)==digest);
    Reject([&]{ Hash(source.fd,size+1); });
    int full=open("/dev/full",O_WRONLY);
    assert(full>=0);
    readback=false;
    Reject([&]{ WriteAndVerify(source.fd,full,size,second,stage,progress,flush); });
    assert(!readback);
    close(full);
    Reject([&]{ WriteAndVerify(source.fd,a.fd,size,second,stage,progress,[](int){ return false; }); });
    assert(!readback);
    Reject([&]{ WriteAndVerify(source.fd,a.fd,size,second,[&](bool r) {
        if (r) assert(pwrite(a.fd,"corrupt",7,size-7)==7);
    },progress,flush); });
    Json::Value journal;
    journal["stage"]="writing"; journal["commit"]=std::string(40,'a'); journal["slot"]="_a";
    journal["build"]=2u; journal["sha256"]=Hex(second);
    assert(!RebootVerified(2,std::string(40,'a'),"_a",second,journal));
    journal["stage"]="verified";
    assert(RebootVerified(2,std::string(40,'a'),"_a",second,journal));
    assert(!RebootVerified(1,std::string(40,'a'),"_a",second,journal));
    assert(!RebootVerified(2,std::string(40,'e'),"_a",second,journal));
    assert(!RebootVerified(2,std::string(40,'a'),"_b",second,journal));
    assert(!RebootVerified(2,std::string(40,'a'),"_a",Hash(a.fd,size),journal));
}
void Downloads() {
    const auto download=[](const std::string& chunk,uint64_t length,bool exact) {
        int pair[2];
        assert(pipe(pair)==0);
        assert(write(pair[1],chunk.data(),chunk.size())==static_cast<ssize_t>(chunk.size()));
        close(pair[1]);
        std::string result;
        try {
            Receive(pair[0],length,exact,[&](const char* buf,size_t count,uint64_t done) {
                result.append(buf,count);
                assert(result.size()==done);
            });
            close(pair[0]);
            return result;
        } catch (...) { close(pair[0]); throw; }
    };
    assert(download("signed!",7,true)=="signed!");
    assert(download("manifest",128,false)=="manifest");
    Reject([&]{ download("incomplete",100,true); });
    Reject([&]{ download("oversize",4,true); });
}
}
int main(int argc,char** argv) {
    assert(argc==2);
    Releases();
    Downloads();
    Partitions(argv[1]);
    std::cout << "PASS: signed releases, downgrade/slot/OTA guards, write/readback and reboot gate fixtures\n";
}
