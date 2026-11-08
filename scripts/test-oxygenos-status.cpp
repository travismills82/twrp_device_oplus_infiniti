// SPDX-License-Identifier: GPL-3.0-or-later
// Host-only fixtures. Never reads the phone or its block devices.
#include "oxygenos_dashboard.hpp"
#include <cassert>
#include <fstream>
#include <iostream>
#include <string>

using namespace op15_dashboard;
int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string root = argv[1];
    Inputs s;
    assert(Crypto(s) == "Unknown" && !Unlocked(s));
    s.ready = true;
    assert(Crypto(s) == "Unavailable");
    s.mounted = true;
    assert(Crypto(s) == "Unknown");
    s.encrypted = 1; s.decrypted = 1; s.fbe = 1;
    assert(Crypto(s) == "Encrypted");  // DE unlocked does not unlock user-0 CE.
    assert(Storage(s) == "Internal storage locked");
    s.user0 = true;
    assert(Crypto(s) == "Decrypted" && Unlocked(s));
    assert(Storage(s) == "Internal storage mounted");
    s.mounted = false;
    assert(Crypto(s) == "Unavailable" && !Unlocked(s));
    s.mounted = true; s.ready = false;
    assert(Crypto(s) == "Unknown" && !Unlocked(s));
    s.ready = true; s.fbe = 0; s.decrypted = 0;
    assert(Crypto(s) == "Encrypted" && !Unlocked(s));
    s.decrypted = 1;
    assert(Crypto(s) == "Decrypted");
    s.encrypted = 0; s.decrypted = 0;
    assert(Crypto(s) == "Unencrypted" && Unlocked(s));
    // Every missing/unmounted/busy combination must fail closed.
    for (int encrypted : {-1,0,1}) for (int fbe : {-1,0,1}) for (int decrypted : {-1,0,1}) {
        s.encrypted=encrypted;s.fbe=fbe;s.decrypted=decrypted;
        s.ready=false;s.mounted=true;assert(!Unlocked(s));
        s.ready=true;s.mounted=false;assert(!Unlocked(s));
        assert(Crypto(s)!="Decrypted");
    }
    assert(Slot("A")=="Slot A" && Slot("B")=="Slot B");
    assert(Slot("_a")=="Slot A" && Slot("_b")=="Slot B");
    for (auto x : {"", "C", "unknown", "a", "_c"}) assert(Slot(x)=="Unknown");
    assert(Battery("0%")=="0%" && Battery("100%+")=="100%");
    assert(Battery("42% ")=="42%" && BatteryPercent("42%+")==42);
    for (auto x : {"", "0", "101%", "-1%", "NaN%", "10%bad", "9999999999999999999999999%"})
        assert(Battery(x)=="Unavailable" && BatteryPercent(x)==-1);
    assert(Cpu("45")=="45 °C");
    assert(Progress("56.9")=="56%" && Progress("100")=="100%" && Progress("0")=="0%");
    for (auto x : {"","nan","inf","-1","101","50 garbage"}) assert(Progress(x).empty());
    for (auto x : {"", "0", "-1", "150", "45000", "NaN", "45 bad"}) assert(Cpu(x)=="Unavailable");
    for (auto x : {"Charging","Charging\n","Charging\r\n"}) assert(Charging(x));
    for (auto x : {"","Unknown","Full","Not charging","Discharging","charging","Charging extra"}) assert(!Charging(x));
    const std::string charge_fixture=root+"/battery-status";
    { std::ofstream out(charge_fixture);out<<"Charging\n"; }
    assert(ReadCharging(charge_fixture.c_str()));
    { std::ofstream out(charge_fixture);out<<"Not charging\n"; }
    assert(!ReadCharging(charge_fixture.c_str()));
    { std::ofstream out(charge_fixture);out<<std::string(64,'x'); }
    assert(!ReadCharging(charge_fixture.c_str()));
    assert(!ReadCharging((root+"/missing-status").c_str()));
    const std::string f2fs="51 1 253:2 / /data rw,seclabel - f2fs /dev/block/dm-2 rw\n";
    const std::string ext4="51 1 253:2 / /data ro - ext4 /dev/block/mapper/userdata ro\n";
    assert(HasDataMount(f2fs) && HasDataMount(ext4));
    for (auto x : {"", "garbage", "51 1 0:2 / /data rw - tmpfs tmpfs rw\n",
                   "51 1 253:2 / /data_mirror rw - f2fs /dev/block/dm-2 rw\n",
                   "51 1 253:2 / /data rw ext4 /dev/block/dm-2 rw\n",
                   "51 1 253:2 / /data rw - ext4 /tmp/image rw\n"}) assert(!HasDataMount(x));
    const std::string fixture=root+"/mountinfo";
    { std::ofstream out(fixture);out<<f2fs; }
    assert(ReadDataMount(fixture.c_str()));
    { std::ofstream out(fixture);out<<std::string(262145,'x'); }
    assert(!ReadDataMount(fixture.c_str()));
    assert(!ReadDataMount((root+"/absent").c_str()));
    std::cout << "OxygenOS status policy PASS: truthful crypto, mount, slot, battery and CPU fixtures\n";
}
