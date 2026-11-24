// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <string>
#include <string_view>

namespace op15_update_notes {
// Preserve line breaks inside the helper's newline-delimited status protocol.
inline constexpr char Break = '\x1e';
inline std::string Encode(std::string_view notes) {
    std::string out;
    out.reserve(notes.size());
    for (char c : notes) {
        if (c == '\n') out += Break;
        else if (c != '\r') out += static_cast<unsigned char>(c) < 32 || c == 127 ? ' ' : c;
    }
    return out;
}

inline std::string Bullets(std::string_view record) {
    std::string out;
    while (!record.empty()) {
        auto end = record.find(Break);
        auto line = record.substr(0,end);
        record = end == std::string_view::npos ? std::string_view{} : record.substr(end + 1);
        auto start = line.find_first_not_of(' ');
        if (start == std::string_view::npos) continue;
        line = line.substr(start,line.find_last_not_of(' ') - start + 1);
        // Accept ordinary GitHub Markdown bullets and already-bulleted text.
        if (line.substr(0,2) == "- " || line.substr(0,2) == "* " || line.substr(0,2) == "+ ")
            line.remove_prefix(2);
        else if (line.substr(0,4) == "• ")
            line.remove_prefix(4);
        start = line.find_first_not_of(' ');
        if (start == std::string_view::npos) continue;
        if (!out.empty()) out += '\n';
        out += "• ";
        out.append(line.substr(start));
    }
    return out;
}
}
