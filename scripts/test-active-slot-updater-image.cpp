// SPDX-License-Identifier: Apache-2.0
// Host-only use of the exact recovery-side AVB validator. No block access.
#define main op15_recovery_entrypoint_not_called_by_host
#include "../updater/main.cpp"
#undef main

#include <cassert>

std::string android::base::GetProperty(const std::string&, const std::string& fallback) {
    return fallback;
}

int main(int argc,char** argv) {
    assert(argc == 6);
    assert(SlotToken("androidboot.slot_suffix = \"_a\"\n",true) == "_a");
    assert(SlotToken("unrelated=yes androidboot.slot_suffix=_b",false) == "_b");
    try {
        SlotToken("androidboot.slot_suffix=_a androidboot.slot_suffix=_b",false);
        assert(!"Ambiguous kernel slot accepted");
    } catch (const std::runtime_error&) {}
    auto source = Open(argv[1]);
    assert(source >= 0);
    const auto v = RecoveryImage(source);
    assert(!v.key.empty());
    const auto manifest = Manifest(File(argv[3],32768),File(argv[4],64),Unhex(argv[5]));
    assert(manifest.sha == Hash(source,ImageSize));
    auto broken = Fd(open(argv[2],O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC,0600));
    assert(broken >= 0);
    assert(Stream(source,broken,ImageSize,[](uint64_t,uint64_t){}) == manifest.sha);
    auto reject = [&] {
        try { RecoveryImage(broken); } catch (const std::runtime_error&) { return; }
        assert(!"Malformed AVB recovery image accepted");
    };
    unsigned char original;
    ReadAt(broken,&original,1,4097);
    unsigned char bad = original ^ 0x80;
    assert(pwrite(broken,&bad,1,4097) == 1);
    reject();
    assert(pwrite(broken,&original,1,4097) == 1);
    assert(RecoveryImage(broken) == v);
    assert(pwrite(broken,"BAD!",4,ImageSize-64) == 4);
    reject();
    std::cout << "PASS: native AVB accepted packed recovery and rejected corrupt payload/footer; signed image hash matched\n";
}
