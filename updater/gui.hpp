// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <fcntl.h>
#include <signal.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <algorithm>
#include <cerrno>
#include <string>

#include "data.hpp"

namespace op15_updater_gui {
// All methods run on the GUI thread. HTTPS, hashes and partition access are
// handled exclusively by the child, whose pipe is drained without blocking.
class Controller {
    pid_t pid_ = -1;
    int pipe_ = -1;
    std::string mode_, buffer_, offer_, pending_offer_, pending_state_, error_;
    bool verified_ = false, previous_wifi_ = false, info_started_ = false, confirmation_started_ = false;
    time_t auto_after_ = 0, manual_after_ = 0;

    static std::string Name(const std::string& key) { return "tw_op15_update_" + key; }
    static void Set(const std::string& key,const std::string& value) {
        if (DataManager::GetStrValue(Name(key)) != value) DataManager::SetValue(Name(key),value);
    }
    static bool Wifi() { return DataManager::GetIntValue("tw_wifi_connected") == 1; }
    static time_t Now() {
        timespec ts{};
        clock_gettime(CLOCK_MONOTONIC,&ts);
        return ts.tv_sec;
    }
    static bool Digits(const std::string& s) {
        return !s.empty() && s.size() <= 20 && s.find_first_not_of("0123456789") == std::string::npos;
    }
    static bool Token(const std::string& s) {
        const auto p = s.find(':');
        return p != std::string::npos && p <= 20 && s.size() == p + 65 &&
            Digits(s.substr(0,p)) && s.find_first_not_of("0123456789abcdef",p+1) == std::string::npos;
    }
    bool Start(const std::string& mode,const std::string& offered = {}) {
        if (pid_ != -1 || DataManager::GetIntValue("tw_busy")) return false;
        int fd[2];
        if (pipe2(fd,O_CLOEXEC) != 0) return false;
        if (fcntl(fd[0],F_SETFL,O_NONBLOCK) != 0) {
            close(fd[0]); close(fd[1]); return false;
        }
        const bool preview = DataManager::GetIntValue(Name("preview")) == 1;
        pid_ = fork();
        if (pid_ == 0) {
            if (dup2(fd[1],STDOUT_FILENO) < 0) _exit(127);
            close(fd[0]); close(fd[1]);
            constexpr auto bin = "/system/bin/op15-twrp-updater";
            const char* channel = preview ? "preview" : "stable";
            if (mode == "install") execl(bin,bin,mode.c_str(),channel,offered.c_str(),nullptr);
            else if (mode == "check") execl(bin,bin,mode.c_str(),channel,nullptr);
            else execl(bin,bin,mode.c_str(),nullptr);
            _exit(127);
        }
        close(fd[1]);
        if (pid_ < 0) { close(fd[0]); return false; }
        pipe_ = fd[0];
        mode_ = mode;
        buffer_.clear(); pending_offer_.clear(); pending_state_.clear(); error_.clear();
        verified_ = false;
        if (mode == "install") {
            DataManager::SetValue("tw_busy",1);
            Set("state","installing"); Set("progress","0"); Set("speed","");
            Set("status","Rechecking the signed release");
        } else if (mode == "check") {
            offer_.clear();
            Set("state","checking"); Set("status","Checking GitHub Releases");
            Set("available","—"); Set("notes","No signed release notes");
            manual_after_ = Now() + 15;
            auto_after_ = Now() + 900;
        }
        return true;
    }
    void Line(const std::string& line) {
        const auto tab = line.find('\t');
        if (tab == std::string::npos || line.size() > 4096) return;
        auto key = line.substr(0,tab), value = line.substr(tab+1);
        if (key == "installed" || key == "target" || key == "slot" || key == "success" ||
            key == "available" || key == "notes" || key == "status" || key == "speed" ||
            (key == "progress" && value.size() <= 3 && Digits(value))) {
            Set(key,value);
        } else if (key == "offer" && Token(value)) pending_offer_ = value;
        else if (key == "state" && (value == "available" || value == "current")) pending_state_ = value;
        else if (key == "error") error_ = value;
        else if (key == "verified" && value == "1") verified_ = true;
    }
    void Finish(bool ok) {
        const auto mode = mode_;
        if (pipe_ >= 0) close(pipe_);
        pipe_ = -1; pid_ = -1; mode_.clear(); buffer_.clear();
        if (mode == "info") return;
        if (mode == "confirm") {
            if (!ok && !error_.empty()) Set("warning",error_);
            return;
        }
        if (mode == "install") {
            Set("speed","");
            if (ok && verified_ && error_.empty()) {
                Set("state","verified");
                // Equivalent to GUIAction::reboot("recovery"): let TWRP
                // leave the UI loop and perform its native shutdown.
                DataManager::SetValue("tw_reboot_arg","recovery");
                DataManager::SetValue("tw_gui_done",1);
            } else {
                Set("state","failed");
                Set("status",error_.empty() ? "Update interrupted. Check recovery before rebooting." : error_);
            }
            DataManager::SetValue("tw_busy",0);
            return;
        }
        if (!Wifi()) { Offline(); return; }
        if (ok && pending_state_ == "available" && !pending_offer_.empty()) {
            offer_ = pending_offer_;
            Set("state","available");
        } else if (ok && pending_state_ == "current") {
            Set("state","current");
        } else {
            Set("state","failed");
            Set("status",error_.empty() ? "Update check did not complete" : error_);
        }
    }
    void Offline() {
        offer_.clear();
        Set("state","offline");
        Set("status","Offline — connect to Wi-Fi");
    }
public:
    void Apply() {
        const bool wifi = Wifi();
        const auto now = Now();
        // On reconnect check immediately, but never issue a request storm.
        if (wifi && !previous_wifi_) auto_after_ = std::min(auto_after_,std::max(now,manual_after_));
        previous_wifi_ = wifi;
        if (pid_ >= 0) {
            char buf[2048];
            // Bound each frame's work even if progress arrives in a burst.
            bool eof = false;
            for (unsigned i=0;i<16;++i) {
                const auto n = read(pipe_,buf,sizeof(buf));
                if (n == 0) { eof = true; break; }
                if (n < 0) break;
                buffer_.append(buf,n);
                size_t next;
                while ((next = buffer_.find('\n')) != std::string::npos) {
                    Line(buffer_.substr(0,next));
                    buffer_.erase(0,next+1);
                }
                if (buffer_.size() > 4096) buffer_.clear();
            }
            if (eof) {
                int status = 0;
                const auto ret = waitpid(pid_,&status,WNOHANG);
                if (ret == pid_) Finish(WIFEXITED(status) && WEXITSTATUS(status) == 0);
                else if (ret < 0 && errno == ECHILD) Finish(false);
            }
            return;
        }
        if (DataManager::GetIntValue("tw_busy")) return;
        if (!info_started_) {
            info_started_ = true;
            if (Start("info")) return;
        }
        if (!confirmation_started_ && (!DataManager::GetIntValue("tw_is_encrypted") ||
                                      DataManager::GetIntValue("tw_is_decrypted"))) {
            confirmation_started_ = Start("confirm");
            if (confirmation_started_) return;
        }
        if (!wifi) { Offline(); return; }
        if (now >= auto_after_ && !Start("check")) auto_after_ = now + 30;
    }
    int User(const std::string& action) {
        if (pid_ >= 0 || DataManager::GetIntValue("tw_busy")) return 0;
        if (action == "preview") {
            DataManager::SetValue(Name("preview"),1-DataManager::GetIntValue(Name("preview")));
            offer_.clear();
            Set("state","current");
            Set("available","—");
            Set("notes","No signed release notes");
            auto_after_ = std::max(Now(),manual_after_);
            Set("status","Update channel changed; checking again");
            if (!Wifi()) Offline();
            return 0;
        }
        if (!Wifi()) { Offline(); return 0; }
        if ((action == "tile" || action == "install") && !offer_.empty()) {
            if (!Start("install",offer_)) return -1;
            offer_.clear();
            return 0;
        }
        if (action == "install") return -1;
        if (Now() < manual_after_) {
            Set("status","Please wait before checking again");
            return 0;
        }
        return Start("check") ? 0 : -1;
    }
};
inline Controller& Instance() { static Controller controller; return controller; }
}
