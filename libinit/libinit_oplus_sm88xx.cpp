/*
 * Copyright (C) 2022-2025 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

#include <android-base/logging.h>
#include <android-base/parseint.h>
#include <android-base/properties.h>
#define _REALLY_INCLUDE_SYS__SYSTEM_PROPERTIES_H_
#include <sys/_system_properties.h>

#include <fs_mgr.h>
#include <unordered_map>

using android::base::GetProperty;
using android::fs_mgr::GetKernelCmdline;

const std::unordered_map<int, std::string> kRegionSuffixMap = {
    {27,    "IN"},
    {55,    "RU"},
    {68,    "EEA"},
    {151,   ""},    // CN
    {161,   "NA"},
    {0,     ""},    // Default
};

struct ModelInfo {
    const char* brand;              // ro.product.brand
    const char* device;             // ro.product.device
    const char* manufacturer;       // ro.product.manufacturer
    const char* model;              // ro.product.model
    const char* base_name;          // ro.product.name  w/o region suffix
    const char* supportSpr;         // vendor.display.enable_spr
};

const std::unordered_map<int, ModelInfo> kModelInfoMap = {
    {24831, {"OnePlus", "OP60FFL1", "OnePlus", "PLK110",  "PLK110",  "1"}}, // infiniti CN
    {0,     {"OPLUS",   "SM87XX",   "OPLUS",   "SM88XX",  "SM88XX",  "0"}}, // Default
};

/*
 * SetProperty does not allow updating read only properties and as a result
 * does not work for our use case. Write "OverrideProperty" to do practically
 * the same thing as "SetProperty" without this restriction.
 */
void OverrideProperty(const char* name, const char* value) {
    size_t valuelen = strlen(value);

    prop_info* pi = (prop_info*)__system_property_find(name);
    if (pi != nullptr) {
        __system_property_update(pi, value, valuelen);
    } else {
        __system_property_add(name, strlen(name), value, valuelen);
    }
}

void SetupModelProperties(const ModelInfo& info, const std::string& region) {
    std::string name = info.base_name + region;
    struct PropPair {
        const char* key;
        const char* value;
    } props[] = {
        {"ro.product.brand",            info.brand},
        {"ro.product.device",           info.device},
        {"ro.product.manufacturer",     info.manufacturer},
        {"ro.product.model",            info.model},
        {"ro.product.name",             name.c_str()},
        {"vendor.display.enable_spr",   info.supportSpr},
        {"ro.build.date.utc",           "0"},
    };
    for (const auto& p : props) {
        OverrideProperty(p.key, p.value);
    }
}

void vendor_load_properties() {
    std::string buf = "0";
    GetKernelCmdline("oplus_region", &buf);

    auto region = std::stoi(buf);
    auto region_suffix_iter = kRegionSuffixMap.find(region);

    auto prjname = std::stoi(GetProperty("ro.boot.prjname", "0"));
    auto model_info = kModelInfoMap.find(prjname);

    SetupModelProperties(model_info->second, region_suffix_iter->second);
}
