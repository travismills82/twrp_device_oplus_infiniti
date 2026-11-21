// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "op15_smb_storage.hpp"
#include "op15_smb_archive.hpp"
#include "op15_smb_profiles.hpp"
#include "data.hpp"
#include "gui/pages.hpp"
#include "partitions.hpp"

#include <chrono>
#include <dirent.h>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <array>
#include <cstring>
#include <vector>

namespace op15_smb {
constexpr size_t Rows = 24;
inline std::vector<std::string> Items;
inline std::vector<Location> SavedLocations;
inline std::string BrowseDir, BrowseMount, BrowseLabel, RestoreRoot, ServerResults;
inline size_t Offset = 0;

inline void Status(const std::string& message) { Queue("tw_smb_status", message); }
inline std::string Get(const std::string& key) { return DataManager::GetStrValue("tw_smb_" + key); }
inline void Set(const std::string& key, const std::string& value) { Queue("tw_smb_" + key, value); }
inline void ApplyUpdates() {
    std::vector<std::pair<std::string, std::string>> values;
    {
        std::lock_guard lock(UIQueueLock);
        values.swap(UIQueue);
    }
    for (const auto& entry : values) {
        if (entry.first == "tw_smb_leave_browser") {
            if (PageManager::GetCurrentPage() == "smb_browser") gui_changePage("advanced");
            continue;
        }
        if (entry.first == "tw_smb_prompt_login") {
            // A completed worker must not pull the user back from another page.
            if (PageManager::GetCurrentPage() == "smb_browser") gui_changePage("smb_server");
            continue;
        }
        if (entry.first == "tw_restore" && DataManager::GetIntValue("tw_smb_busy")) {
            Queue(entry.first, entry.second);
            continue;
        }
        if (entry.first == "tw_storage_path") {
            std::unique_lock guard(Session, std::try_to_lock);
            if (!guard) { Queue(entry.first, entry.second); continue; }
            DataManager::SetValue(entry.first, entry.second);
        } else DataManager::SetValue(entry.first, entry.second);
    }
}

inline int Process(const char* executable, std::vector<const char*> argv,
                   const std::string& input, std::string* result) {
    int fds[2];
    if (socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, fds)) return 4;
    const pid_t pid = fork();
    if (pid < 0) { close(fds[0]); close(fds[1]); return 4; }
    if (!pid) {
        close(fds[0]);
        if (dup2(fds[1], STDIN_FILENO) < 0 || dup2(fds[1], STDOUT_FILENO) < 0) _exit(4);
        close(fds[1]);
        int fd = open("/dev/null", O_WRONLY);
        if (fd >= 0) { dup2(fd, STDERR_FILENO); close(fd); }
        execv(executable, const_cast<char* const*>(argv.data()));
        _exit(4);
    }
    close(fds[1]);
    size_t sent = 0;
    while (sent < input.size()) {
        const auto n = send(fds[0], input.data() + sent, input.size() - sent, MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        sent += n;
    }
    shutdown(fds[0], SHUT_WR);
    const auto end = std::chrono::steady_clock::now() + std::chrono::seconds(20);
    bool done = false;
    result->clear();
    while (std::chrono::steady_clock::now() < end && result->size() < 65536) {
        pollfd p{fds[0], POLLIN, 0};
        if (poll(&p, 1, 150) <= 0) continue;
        char buf[2048];
        const auto n = read(fds[0], buf, sizeof(buf));
        if (n == 0) { done = true; break; }
        if (n < 0) break;
        result->append(buf, n);
    }
    close(fds[0]);
    int status = 0;
    if (!done) kill(pid, SIGKILL);
    pid_t waited;
    do { waited = waitpid(pid, &status, 0); } while (waited < 0 && errno == EINTR);
    return done && waited == pid && WIFEXITED(status) ? WEXITSTATUS(status) : 2;
}
inline int Client(const char* command, const std::string& data, std::string* out) {
    const char* exe = "/system/bin/twrp-smb-client";
    return Process(exe, {exe, command, nullptr}, data, out);
}

inline bool RefreshWifi() {
    const char* exe = "/system/bin/wpa_cli";
    std::string details, ip, ssid;
    Process(exe, {exe, "-iwlan0", "-p/tmp/recovery/sockets", "status", nullptr}, "", &details);
    std::istringstream lines(details);
    std::string line;
    bool associated = false;
    while (getline(lines, line)) {
        if (line == "wpa_state=COMPLETED") associated = true;
        if (line.rfind("ssid=", 0) == 0) ssid = line.substr(5);
    }
    const bool connected = associated && Client("status", "", &ip) == 0;
    if (!ip.empty() && ip.back() == '\n') ip.pop_back();
    Set("wifi", connected ? "Connected" : "Disconnected");
    Set("ssid", connected ? ssid : "–");
    Set("ip", connected ? ip : "–");
    return connected;
}

inline void ShowRows() {
    for (size_t i = 0; i < Rows; ++i)
        Set("row_" + std::to_string(i), Offset + i < Items.size() ? Items[Offset+i] : "");
    Set("more", Offset + Rows < Items.size() ? "1" : "0");
    Set("prev", Offset ? "1" : "0");
}
inline void Content(const char* view, const std::string& text = "") {
    Items.clear();
    Offset = 0;
    std::string name;
    std::istringstream in(text);
    while (getline(in, name) && Items.size() < 256) {
        if (Component(name)) Items.push_back(name);
    }
    std::sort(Items.begin(), Items.end());
    Items.erase(std::unique(Items.begin(), Items.end()), Items.end());
    Set("view", view);
    ShowRows();
}

inline void ShowServerOverview() {
    Set("share", "");
    Set("folder", "");
    Content("servers", ServerResults);
    Status(Items.empty() ? "Scan the network or add a server manually." :
                           "Tap a server or enter a hostname manually.");
}

inline bool ListFolders() {
    if (!Directory(BrowseDir, BrowseMount)) return false;
    DIR* directory = opendir(BrowseDir.c_str());
    if (!directory) return false;
    std::string entries;
    size_t count = 0;
    int result = 0;
    while (count < 256) {
        errno = 0;
        auto* item = readdir(directory);
        if (!item) { result = errno; break; }
        if (!Component(item->d_name)) continue;
        if (item->d_type != DT_DIR && item->d_type != DT_UNKNOWN) continue;
        const std::string path = BrowseDir + "/" + item->d_name;
        struct stat file {};
        if (lstat(path.c_str(), &file) != 0 || !S_ISDIR(file.st_mode)) continue;
        entries += std::string(item->d_name) + "\n";
        ++count;
    }
    closedir(directory);
    if (result || MountId() != BrowseMount) return false;
    Set("folder", BrowseLabel + BrowseDir.substr(std::string(Root).size()));
    Content("folders", entries);
    return true;
}

inline bool ListBackups() {
    const std::string root = DataManager::GetStrValue("tw_backups_folder");
    const auto id = MountId();
    RestoreRoot.clear();
    Content("restores");
    if (!Directory(root, id)) return false;
    DIR* directory = opendir(root.c_str());
    if (!directory) return false;
    const auto end = std::chrono::steady_clock::now() + std::chrono::seconds(25);
    std::string names;
    while (std::chrono::steady_clock::now() < end && names.size() < 60000) {
        auto* entry = readdir(directory);
        if (!entry) break;
        if (!Component(entry->d_name)) continue;
        if (entry->d_type != DT_DIR && entry->d_type != DT_UNKNOWN) continue;
        const auto path = root + "/" + entry->d_name;
        if (Directory(path, id) && CompleteBackupAt(path))
            names += std::string(entry->d_name) + "\n";
    }
    closedir(directory);
    if (MountId() != id) return false;
    RestoreRoot = root;
    Content("restores", names);
    return true;
}

inline bool TargetFree() {
    std::ifstream mounts("/proc/self/mountinfo");
    std::string line;
    if (!mounts) return false;
    while (getline(mounts, line)) {
        std::istringstream fields(line);
        std::string id, parent, dev, root, target;
        if (!(fields >> id >> parent >> dev >> root >> target) || target == Root) return false;
    }
    for (const char* path : {"/mnt/smb", Root}) {
        if (mkdir(path, 0700) && errno != EEXIST) return false;
        struct stat v {};
        if (lstat(path, &v) != 0 || !S_ISDIR(v.st_mode) || v.st_uid != 0) return false;
    }
    return true;
}

inline int PromptLogin(const std::string& command, const char* message) {
    Set("auth_operation", command);
    Set("auth_hint", message);
    Set("password", "");
    Queue("tw_smb_prompt_login", "");
    Status(message);
    return 0;
}

inline bool ReadSaved(Profiles* list) {
    const int dir = OpenProfileDirectory(false);
    if (dir < 0) return false;
    const bool ok = ReadProfiles(dir, list);
    close(dir);
    return ok;
}

inline bool FillSaved(Login* login) {
    if (!ValidLogin(*login)) return false;
    Profiles list;
    if (!ReadSaved(&list)) return false;
    const auto key = ProfileLocation(*login);
    for (const auto& row : list.records) {
        if (ProfileLocation(row) != key || row[3].empty()) continue;
        for (size_t i = 3; i < login->size(); ++i) (*login)[i] = row[i];
        return true;
    }
    return false;
}

inline bool Remember(const Login& login) {
    const int dir = OpenProfileDirectory(true);
    if (dir < 0) return false;
    const bool ok = UpdateProfile(dir, login);
    close(dir);
    return ok;
}

inline int SendLogin(const std::string& command, const Login& values, std::string* out) {
    std::string input;
    for (const auto& value : values) { input += value; input.push_back(0); }
    const int rc = Client(command.c_str(), input, out);
    Wipe(input);
    return rc;
}

inline int Connect(const std::string& command, Login values, bool prompt_on_refusal,
                   bool try_saved = false, bool prefer_saved = false) {
    auto fail = [](const char* message) { Status(message); return -1; };
    struct ClearSecret {
        std::string& password;
        ~ClearSecret() { Wipe(password); }
    } clear{values[4]};
    Set("password", "");
    if (command == "shares") values[2].clear(); // Enumeration verified only the server, not a share.
    if (!ValidLogin(values)) return fail("Check the hostname, port, share name, or login fields.");
    if (!RefreshWifi()) return fail("Connect to Wi-Fi first.");
    if (command == "mount" && !TargetFree()) return fail("Disconnect the current SMB share first.");
    if (prefer_saved) FillSaved(&values);
    std::string out;
    int rc = SendLogin(command, values, &out);
    if (rc == LoginRefused && try_saved && values[3].empty() && FillSaved(&values))
        rc = SendLogin(command, values, &out);
    const bool guest = values[3].empty();
    if (rc == 1) return fail("Check the hostname, port, or share name.");
    if (rc == LoginRefused) {
        if (prompt_on_refusal) {
            if (!guest) { Set("user", values[3]); Set("domain", values[5]); }
            return PromptLogin(command, guest ? "Guest access denied. Sign in to continue." :
                "Sign-in denied. Check your username and password.");
        }
        return fail("Login or share listing refused. Check credentials or enter the share directly.");
    }
    if (rc == 5) return fail("Server did not negotiate SMB 2.1 or newer.");
    if (rc == 4) return fail("SMB connection could not be mounted. FUSE support or permission is missing.");
    if (rc) return fail("SMB server unavailable, not on this Wi-Fi subnet, or a share is already mounted.");
    Set("auth_operation", "");
    Set("auth_hint", "");
    if (command == "shares") {
        const bool remembered = Remember(values);
        Content("shares", out);
        Status(Items.empty() ? "No visible shares. Enter a share manually." :
            (remembered ? "Tap a share to open it." : "Tap a share to open it. Server was not saved."));
        return 0;
    }
    BrowseDir = Root;
    BrowseMount = MountId();
    BrowseLabel = values[0] + "/" + values[2];
    if (out != "mounted\n" || !ListFolders()) {
        PartitionManager.Disconnect_Op15_Smb();
        BrowseDir.clear(); BrowseMount.clear(); BrowseLabel.clear();
        return fail("The SMB mount did not pass a live directory check.");
    }
    Status(Remember(values) ? "Connected. Browse to the folder you want to use." :
        "Connected. SMB location could not be saved to /data.");
    return 0;
}

inline int Run(const std::string& op) {
    std::unique_lock guard(Session, std::try_to_lock);
    if (!guard) {
        Set("password", "");
        Status("SMB is busy with a backup or restore.");
        return -1;
    }
    auto fail = [](const char* message) { Status(message); return -1; };
    if (op == "back") {
        for (const char* key : {"password", "auth_operation", "auth_hint"}) Set(key, "");
        switch (BrowserBack(Get("view"), !BrowseMount.empty())) {
        case BackDestination::Leave:
            Queue("tw_smb_leave_browser", "");
            break;
        case BackDestination::Servers:
            ShowServerOverview();
            break;
        case BackDestination::Connected:
            // Keep both the mount and TWRP's selected network storage in use.
            Content("connected");
            Status("The share is still mounted. Tap Resume Share to browse it.");
            break;
        }
        return 0;
    }
    Status("Working…");
    if (op == "resume") {
        if (!ListFolders()) return fail("The SMB share is unavailable. Disconnect and reconnect it.");
        Status("Connected. Browse to the folder you want to use.");
        return 0;
    }
    if (op == "disconnect") {
        if (!PartitionManager.Disconnect_Op15_Smb()) return fail("Cannot disconnect a share in use.");
        BrowseDir.clear(); BrowseMount.clear(); BrowseLabel.clear();
        for (const char* key : {"password", "user", "domain", "folder"}) Set(key, "");
        ShowServerOverview();
        Status("Disconnected from share.");
        return 0;
    }
    if (op == "next" || op == "previous") {
        if (op == "next" && Offset + Rows < Items.size()) Offset += Rows;
        if (op == "previous" && Offset) Offset -= Rows;
        ShowRows();
        Status("");
        return 0;
    }
    if (op == "saved") {
        Profiles list;
        SavedLocations.clear();
        Content("saved");
        if (!ReadSaved(&list)) return fail("No readable saved SMB locations on /data.");
        for (const auto& row : list.records) {
            const auto location = ProfileLocation(row);
            std::string label = location[0];
            if (location[1] != "445") label += ":" + location[1];
            if (!location[2].empty()) label += " / " + location[2];
            Items.push_back(label);
            SavedLocations.push_back(location);
        }
        ShowRows();
        Status(Items.empty() ? "No saved SMB locations yet." : "Tap a saved server or share.");
        return 0;
    }
    if (op == "restore-list") {
        if (!ListBackups()) return fail("No readable network backup folder. Check the selected share.");
        Status(Items.empty() ? "No complete network backups found." : "Select a network backup.");
        return 0;
    }
    if (op.rfind("row:", 0) == 0) {
        const auto key = op.substr(4);
        const int pos = Port(key) - 1; // buttons use one-based indices
        if (key.empty() || pos < 0 || pos >= static_cast<int>(Rows) ||
            Offset + pos >= Items.size()) return fail("List changed. Refresh and try again.");
        const std::string item = Items[Offset + pos];
        if (Get("view") == "saved") {
            if (Offset + pos >= SavedLocations.size()) return fail("Saved list changed. Reopen it.");
            const auto location = SavedLocations[Offset + pos];
            Set("server", location[0]); Set("port", location[1]); Set("share", location[2]);
            for (const char* key : {"user", "password", "domain", "auth_operation", "auth_hint"}) Set(key, "");
            return Connect(location[2].empty() ? "shares" : "mount",
                           {location[0], location[1], location[2], "", "", ""}, true, false, true);
        }
        if (Get("view") == "restores") {
            const auto path = RestoreRoot + "/" + item;
            if (RestoreRoot.empty() || RestoreRoot != DataManager::GetStrValue("tw_backups_folder") ||
                !Directory(path, MountId()) || !CompleteBackupAt(path))
                return fail("Backup unavailable or incomplete. Refresh the list.");
            Queue("tw_restore_name", item);
            Queue("tw_restore", path);
            Status("");
            return 0;
        }
        if (Get("view") == "servers") {
            Set("server", item); Set("port", ""); Set("share", "");
            for (const char* key : {"user", "password", "domain", "auth_operation", "auth_hint"}) Set(key, "");
            // Do not read queued variables or carry credentials between servers.
            return Connect("shares", {item, "", "", "", "", ""}, true, true);
        }
        if (Get("view") == "shares") {
            Set("share", item);
            return Connect("mount", {Get("server"), Get("port"), item, "", "", ""}, true, true);
        }
        const auto old = BrowseDir;
        BrowseDir += "/" + item;
        if (!ListFolders()) { BrowseDir = old; return fail("Cannot open that SMB folder."); }
        Status("");
        return 0;
    }
    if (op == "parent" || op == "mkdir" || op == "backup" || op == "restore" ||
        (op == "refresh" && !BrowseMount.empty())) {
        if (op == "refresh" && !RefreshWifi()) return fail("Wi-Fi is disconnected.");
        if (!Directory(BrowseDir, BrowseMount)) return fail("SMB mount or Wi-Fi is unavailable.");
        if (op == "parent" && BrowseDir != Root) BrowseDir.resize(BrowseDir.rfind('/'));
        if (op == "mkdir") {
            const auto folder = Get("newfolder");
            Set("newfolder", "");
            if (!Component(folder) || mkdir((BrowseDir + "/" + folder).c_str(), 0700))
                return fail("Cannot create folder. Check its name and share permissions.");
        }
        if (op == "backup" || op == "restore") {
            if (op == "backup" && !Writable(BrowseDir)) return fail("The SMB folder is not writable.");
            if (!PartitionManager.Set_Op15_Smb_Storage(BrowseDir, Get("folder")))
                return fail("Cannot register the SMB folder as TWRP storage.");
            Status(op == "backup" ? "SMB storage selected. Open the native Backup screen." :
                "SMB storage selected. Open the native Restore screen.");
            return 0;
        }
        if (!ListFolders()) return fail("Cannot read that SMB directory.");
        Status("");
        return 0;
    }
    if (op == "scan" || op == "refresh") {
        if (!RefreshWifi()) return fail("Connect to Wi-Fi first.");
        std::string out;
        if (Client("scan", "", &out)) return fail("Could not scan the Wi-Fi subnet.");
        ServerResults = std::move(out);
        ShowServerOverview();
        return 0;
    }
    const bool signin = op == "signin";
    const auto command = signin ? Get("auth_operation") : op;
    if (command != "shares" && command != "mount") return fail("Unknown SMB operation.");
    if (signin && Get("user").empty()) return PromptLogin(command, "Enter a username to sign in.");
    return Connect(command, {Get("server"), Get("port"), Get("share"),
                             Get("user"), Get("password"), Get("domain")}, signin);
}
}
