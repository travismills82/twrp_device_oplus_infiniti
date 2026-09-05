// SPDX-License-Identifier: Apache-2.0
#include <android/binder_ibinder.h>
#include <android/binder_manager.h>

// Accept a public service name only; never receives credentials or key material.
int main(int argc, char** argv) {
    if (argc != 2 || argv[1][0] == '\0') return 2;
    AIBinder* binder = AServiceManager_checkService(argv[1]);
    if (binder == nullptr) return 1;
    AIBinder_decStrong(binder);
    return 0;
}
