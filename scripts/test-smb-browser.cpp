#include <cassert>
#include <sstream>
#include <fstream>
#include "op15_smb_storage.hpp"
#include "op15_smb_archive.hpp"
#include "op15_smb_profiles.hpp"

int main() {
    using namespace op15_smb;
    assert(BrowserBack("", false) == BackDestination::Leave);
    assert(BrowserBack("servers", false) == BackDestination::Leave);
    assert(BrowserBack("saved", false) == BackDestination::Servers);
    assert(BrowserBack("shares", false) == BackDestination::Servers);
    assert(BrowserBack("folders", true) == BackDestination::Connected);
    assert(BrowserBack("connected", true) == BackDestination::Leave);
    assert(Host("HOME-NAS.local") && Host("192.168.1.2"));
    assert(!Host("user@host") && !Host("//nas") && !Host("nas:445"));
    assert(Port("") == 445 && Port("1445") == 1445 && !Port("0") && !Port("65536"));
    assert(Component("2026-11-21--08-48") && Component("My Photos"));
    assert(!Component("..") && !Component("bad\tname") && !Component("bad'name"));
    assert(!Component("win:stream") && !Component("bad\\name"));
    assert(Path("/") && Path("/backup/one") && !Path("/backup/../one") && !Path("/backup//one"));
    assert(NetworkPath("/mnt/smb/share/TWRP") && !NetworkPath("/mnt/smb/share-other"));
    assert(!Below("", "/data"));
    Lan lan{0xc0a80110, 0xffff0000};
    assert(lan.Start() == 0xc0a80100 && lan.End() == 0xc0a801ff);
    assert(lan.Contains(0xc0a80113) && !lan.Contains(0xc0a80110) && !lan.Contains(0xc0a90013));
    Lan small{0xc0a80110, 0xfffffff0};
    assert(small.Start() == 0xc0a80110 && small.End() == 0xc0a8011f);
    std::istringstream legitimate("19 18 0:17 / /mnt/smb/share rw - fuse.twrp-smb twrp-smb rw\n");
    std::istringstream other("19 18 0:17 / /mnt/smb/share rw - tmpfs tmpfs rw\n");
    std::istringstream duplicate(
        "19 18 0:17 / /mnt/smb/share rw - fuse.twrp-smb twrp-smb rw\n"
        "20 19 0:18 / /mnt/smb/share rw - fuse.twrp-smb twrp-smb rw\n");
    assert(MountId(legitimate) == "19" && MountId(other).empty() && MountId(duplicate).empty());
    char folder[] = "/tmp/twrp-archive-parts.XXXXXX";
    assert(mkdtemp(folder));
    const int profile_dir = open(folder, O_DIRECTORY | O_RDONLY | O_CLOEXEC);
    assert(profile_dir >= 0);
    Login first{"NAS.Example", "", "Backups", "fixture", "comma, space!\t", "TEST"};
    Login guest{"nas.example", "445", "Backups", "", "", ""};
    Login alternate{"nas.example", "8445", "Backups", "fixture2", "different", "TEST"};
    assert(ProfileLocation(first) == ProfileLocation(guest));
    assert(ProfileLocation(first) != ProfileLocation(alternate));
    assert(UpdateProfile(profile_dir, first) && UpdateProfile(profile_dir, guest));
    assert(UpdateProfile(profile_dir, alternate));
    Profiles stored;
    assert(ReadProfiles(profile_dir, &stored) && stored.records.size() == 2);
    assert(stored.records[0] == first && stored.records[1] == alternate);
    assert(fchmodat(profile_dir, ProfileFile, 0644, 0) == 0);
    Profiles invalid;
    assert(!ReadProfiles(profile_dir, &invalid) && !UpdateProfile(profile_dir, guest));
    assert(fchmodat(profile_dir, ProfileFile, 0600, 0) == 0);
    assert(linkat(profile_dir, ProfileFile, profile_dir, "extra", 0) == 0);
    assert(!ReadProfiles(profile_dir, &invalid));
    assert(unlinkat(profile_dir, "extra", 0) == 0 && unlinkat(profile_dir, ProfileFile, 0) == 0);
    assert(symlinkat("/dev/null", profile_dir, ProfileFile) == 0);
    assert(!ReadProfiles(profile_dir, &invalid) && !UpdateProfile(profile_dir, first));
    assert(unlinkat(profile_dir, ProfileFile, 0) == 0);
    assert(!DecodeProfiles("TWRP-SMB1\ntruncated", &invalid));
    std::istringstream data_mount("18 17 253:18 / /data rw - f2fs /dev/block/dm-18 rw\n");
    std::istringstream tmp_mount("18 17 0:25 / /data rw - tmpfs tmpfs rw\n");
    assert(DataVolumeMounted(data_mount) && !DataVolumeMounted(tmp_mount));
    assert(close(profile_dir) == 0);
    auto archive = std::string(folder) + "/data.f2fs.win";
    std::vector<std::string> files;
    assert(!BackupDigestFiles(archive, &files)); // Missing is never a success.
    std::ofstream(archive + "000") << "part 0";
    std::ofstream(archive + "002") << "part 2";
    assert(!BackupDigestFiles(archive, &files)); // A hole is never a success.
    files.clear();
    std::ofstream(archive + "001") << "part 1";
    assert(BackupDigestFiles(archive, &files) && files.size() == 3);
    for (const auto& part : files) assert(unlink(part.c_str()) == 0);
    files.clear();
    { std::ofstream empty(archive); }
    assert(!BackupDigestFiles(archive, &files));
    assert(!CompleteBackupAt(folder));
    std::ofstream(archive) << "backup";
    assert(!CompleteBackupAt(folder));
    std::ofstream(archive + ".sha2") << "synthetic checksum";
    assert(CompleteBackupAt(folder));
    const auto marker = std::string(folder) + "/.twrp-incomplete";
    { std::ofstream incomplete(marker); }
    assert(!CompleteBackupAt(folder));
    assert(unlink(marker.c_str()) == 0 && unlink((archive + ".sha2").c_str()) == 0);
    assert(unlink(archive.c_str()) == 0 && rmdir(folder) == 0);
}
