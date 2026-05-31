//
// Copyright (C) 2026 The Android Open Source Project
//
// SPDX-License-Identifier: Apache-2.0
//

// Minimal vendor init hook for recovery.
//
// BoardConfig.mk references this module through:
//   TARGET_INIT_VENDOR_LIB := //$(DEVICE_PATH):libinit_oplus_infiniti
//
// TWRP/system init links this static library and calls vendor_load_properties()
// when vendor-specific property overrides are supported by the manifest.
// Keep this intentionally minimal until device-specific runtime property
// overrides are required for OnePlus 15 / SM8850.

void vendor_load_properties() {
    // No device-specific property overrides are currently required.
}
