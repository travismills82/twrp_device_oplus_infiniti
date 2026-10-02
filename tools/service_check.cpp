// SPDX-License-Identifier: Apache-2.0
#include <aidl/android/hardware/weaver/IWeaver.h>
#include <aidl/android/hardware/weaver/WeaverConfig.h>
#include <android/binder_auto_utils.h>
#include <android/binder_ibinder.h>
#include <android/binder_manager.h>

#include <cstring>

namespace {

constexpr char kWeaverService[] = "android.hardware.weaver.IWeaver/default";

// This is intentionally read-only: it validates the eSE-backed Weaver
// transport without receiving a credential, a Weaver key, or any key material.
int CheckWeaverConfig() {
    ::ndk::SpAIBinder binder(AServiceManager_checkService(kWeaverService));
    if (binder.get() == nullptr) return 1;

    const auto weaver = ::aidl::android::hardware::weaver::IWeaver::fromBinder(binder);
    if (weaver == nullptr) return 1;

    ::aidl::android::hardware::weaver::WeaverConfig config;
    if (!weaver->getConfig(&config).isOk()) return 1;

    return config.slots > 0 && config.keySize > 0 && config.valueSize > 0 ? 0 : 1;
}

}  // namespace

// Accept a public service name only; never receives credentials or key material.
int main(int argc, char** argv) {
    if (argc != 2 || argv[1][0] == '\0') return 2;
    if (std::strcmp(argv[1], "--weaver-config") == 0) return CheckWeaverConfig();

    AIBinder* binder = AServiceManager_checkService(argv[1]);
    if (binder == nullptr) return 1;
    AIBinder_decStrong(binder);
    return 0;
}
