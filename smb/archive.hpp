// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "op15_smb_protocol.hpp"
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
#include <dirent.h>
#include <string>
#include <sys/stat.h>
#include <vector>

namespace op15_smb {
inline bool CompleteBackupAt(const std::string& directory) {
    struct stat st {};
    if (lstat((directory + "/.twrp-incomplete").c_str(), &st) == 0 || errno != ENOENT) return false;
    DIR* files = opendir(directory.c_str());
    if (!files) return false;
    bool found = false;
    for (int count = 0; count < 1024; ++count) {
        auto* entry = readdir(files);
        if (!entry) break;
        const std::string_view name(entry->d_name);
        if (!Component(name)) continue;
        const auto win = name.rfind(".win");
        if (win == std::string_view::npos || name.find('.') == win ||
            (name.substr(win) != ".win" && name.substr(win) != ".win000")) continue;
        const std::string base = directory + "/" + std::string(name);
        if (lstat(base.c_str(), &st) != 0 || !S_ISREG(st.st_mode) || st.st_size <= 0) continue;
        for (const char* suffix : {".sha2", ".sha256", ".md5", ".md5sum"}) {
            if (lstat((base + suffix).c_str(), &st) == 0 && S_ISREG(st.st_mode) &&
                st.st_size > 0 && st.st_size <= 4096) { found = true; break; }
        }
        if (found) break;
    }
    closedir(files);
    return found;
}

inline bool BackupDigestFiles(const std::string& file, std::vector<std::string>* outputs) {
	struct stat one {};
	if (lstat(file.c_str(), &one) == 0) {
		if (!S_ISREG(one.st_mode) || one.st_size <= 0) return false;
		outputs->push_back(file);
		return true;
	}
	if (errno != ENOENT) return false;
	const auto slash = file.rfind('/');
	if (slash == std::string::npos) return false;
	const auto base = file.substr(slash + 1);
	DIR* directory = opendir(file.substr(0, slash).c_str());
	if (!directory) return false;
	std::array<bool, 1000> present{};
	int last = -1;
	errno = 0;
	while (auto* item = readdir(directory)) {
		const std::string name = item->d_name;
		if (name.size() != base.size() + 3 || name.compare(0, base.size(), base)) continue;
		int index = 0;
		for (char digit : name.substr(base.size())) {
			if (digit < '0' || digit > '9') { index = -1; break; }
			index = index * 10 + digit - '0';
		}
		if (index < 0) continue;
		present[index] = true;
		last = std::max(last, index);
	}
	const int io_error = errno;
	closedir(directory);
	if (last < 0 || io_error) return false;
	for (int i = 0; i <= last; ++i) {
		if (!present[i]) return false;
		const char suffix[] = {static_cast<char>('0' + i / 100),
			static_cast<char>('0' + (i / 10) % 10), static_cast<char>('0' + i % 10), '\0'};
		const auto part = file + suffix;
		if (lstat(part.c_str(), &one) != 0 || !S_ISREG(one.st_mode) || one.st_size <= 0) return false;
		outputs->push_back(part);
	}
	return true;
}
}
