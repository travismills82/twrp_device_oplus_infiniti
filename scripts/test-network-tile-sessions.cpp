// SPDX-License-Identifier: Apache-2.0
#include "op15_network_sessions.hpp"

#include <arpa/inet.h>
#include <cassert>
#include <filesystem>
#include <iostream>
#include <sys/socket.h>

int main(int argc, char** argv) {
    using namespace op15_network_sessions;
    namespace fs = std::filesystem;
    assert(argc == 2);
    const fs::path fixture(argv[1]);
    const fs::path ftp = fixture / "ftp", smb = fixture / "smb", proc = fixture / "proc";
    fs::create_directory(ftp);
    fs::create_directory(smb);
    fs::create_directories(proc / "42/fd");
    // The command's actual name is irrelevant, and may contain whitespace and ')'.
    {
        std::ofstream stat(proc / "42/stat");
        stat << "42 (name ) with spaces) S";
        for (int i = 4; i < 22; ++i) stat << " 0";
        stat << " 12345 0\n";
    }
    fs::create_symlink("socket:[985]", proc / "42/fd/3");
    fs::create_symlink("/dev/null", proc / "42/fd/4");
    std::ofstream(ftp / "42.12345").close();
    std::ofstream(ftp / "42.11111").close();
    std::ofstream(ftp / "777.12345").close();
    fs::create_directories(proc / "43");
    fs::copy_file(proc / "42/stat", proc / "43/stat");
    std::ofstream(smb / "43.12345.986").close();
    assert(StartTime((proc / "42").string()) == "12345");
    assert(SessionSockets(ftp, proc) == Sockets{"985"});
    assert(SessionSockets(smb, proc).empty());
    assert(SessionSockets(smb, proc, true) == Sockets{"986"});
    assert(!fs::exists(ftp / "42.11111") && !fs::exists(ftp / "777.12345"));
    std::istringstream other("0: 0100007F:0001 0100007F:0002 01 0:0 0:0 0 0 0 114\n");
    std::istringstream listening("0: 0100007F:0001 00000000:0000 0A 0:0 0:0 0 0 0 985\n");
    std::istringstream closing("0: 0100007F:0001 0100007F:0002 08 0:0 0:0 0 0 0 985\n");
    std::istringstream live("0: 0100007F:0001 0100007F:0002 01 0:0 0:0 0 0 0 985\n");
    assert(!Established(other, {"985"}) && !Established(listening, {"985"}));
    assert(!Established(closing, {"985"}) && Established(live, {"985"}));

    const auto process = std::to_string(getpid());
    const auto start = StartTime("/proc/" + process);
    assert(!start.empty());
    std::ofstream(smb / (process + "." + start)).close();
    const auto connected = [&] {
        const auto sockets = SessionSockets(smb, "/proc");
        std::ifstream tcp("/proc/net/tcp");
        assert(tcp.good());
        return Established(tcp, sockets);
    };
    const int server = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    assert(server >= 0);
    sockaddr_in local{};
    local.sin_family = AF_INET;
    local.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    assert(bind(server, reinterpret_cast<const sockaddr*>(&local), sizeof(local)) == 0);
    assert(listen(server, 1) == 0 && !connected());
    socklen_t length = sizeof(local);
    assert(getsockname(server, reinterpret_cast<sockaddr*>(&local), &length) == 0);
    const int client = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    assert(client >= 0 && connect(client, reinterpret_cast<const sockaddr*>(&local), length) == 0);
    const int peer = accept(server, nullptr, nullptr);
    assert(peer >= 0 && connected());
    assert(close(client) == 0 && close(peer) == 0 && !connected() && close(server) == 0);
    std::cout << "Network tile session fixtures PASS: ownership, real TCP transition, stale PID and closed states\n";
}
