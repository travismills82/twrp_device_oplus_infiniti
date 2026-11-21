# OnePlus 15 — native SMB browser validation

The native SMB work started from `0fa0019` and is included in `twrp-16.0`.
The existing backup destination safety patch and fstab are retained.
The recovery source remains pinned at `6bd8134ec8ff`.

## Backend and usage

Connect through the existing WLAN page. Open **Network & Tools → CIFS / SMB Browser**
or **Advanced → CIFS / SMB Browser**, which replaces the placeholder Extension
button. The browser includes the existing
status bar, WLAN status/SSID/IPv4, a scrollable server/share/folder list,
manual login with a masked password, parent navigation, folder creation and
separate buttons to select the current directory for Backup or Restore.

Discovery checks TCP 445 on the intersection of the active WLAN subnet and
the local /24, at most 254 simultaneous nonblocking connection attempts
with a bounded polling window. Results are candidate IP addresses; the
actual SMB session and share enumeration validate the protocol and server.
Manual IPv4 and DNS hostnames work with an optional custom port. IPv6,
NetBIOS browsing, and WS-Discovery are not implemented; `.local` names
depend on the recovery resolver. Some servers prohibit IPC share enumeration;
enter the known share manually if authenticated enumeration is unavailable.
Tapping a discovered server attempts guest share enumeration. If access is
explicitly refused, recovery opens the login page, and **Sign In** retries
that operation. A server can expose share names to guests but protect the
directories: tapping a listed share then attempts a guest mount and prompts
if that share denies access. Connection failures and timeouts are not treated
as authentication refusals. The login page uses TWRP's shared bottom navigation
and has no extra Back button.

Back from a share list, saved list, or folder view returns to the SMB browser
overview. If a share is mounted, **Resume Share** returns to the same folder;
Back does not unmount the share or change Backup/Restore storage. To unmount
it, use **Disconnect**. Back from the overview exits to Advanced.

The attached phone was running Android kernel
`6.12.118-android16-6-o-g76b73bd515be-4k`; its live configuration reported
`CONFIG_CIFS` **not set**, `CONFIG_FUSE_FS=y`, and exposed `/dev/fuse`. No
matching CIFS module was present in the checked module locations. The
dedicated recovery image is built **without a kernel**, so it cannot enable
CIFS on its own. No custom kernel or module is shipped. The actual filesystem
type is `fuse.twrp-smb`, not kernel `cifs`. It uses
[libsmb2](https://github.com/sahlberg/libsmb2/tree/c7996bb97601a7f04d3e5c371317425da9b82ba4)
and the existing AOSP libfuse. `scripts/prepare-smb-deps.sh` pulls that exact
source revision, enables the libfuse recovery variant, and adds FUSE write
permissions only to the recovery SELinux domain. It does not relax Android
enforcement. No Samba server is bundled.

SMB1 is not implemented. SMB 2.1, 3.0 and 3.1.1 are accepted where mutually
supported; authenticated logins require signing. Guest access depends on
server policy. Host fixtures forced SMB 2.1 and 3.1.1; 3.0 was not forced in
the fixtures. Credentials travel to the client through a private in-memory
socket, not arguments, shell commands, properties, backup logs or metadata.
After a successful connection, recovery saves the location and successful
credentials in root-only `/data/twrp/smb/profiles.v1` (mode `0600`), separate
from Wi-Fi profiles. This is not an encrypted password vault: a privileged
process with access to the mounted Data filesystem can read the file. The
directory is outside user-0 CE storage and the normal TWRP Data archive. Saved
locations are listed under **Saved SMB Locations**; credentials are reused
only after the user selects the same server, port and share. The server is
not pinned by IP ownership; use saved credentials on trusted networks only.
If the filesystem is unavailable or read-only, an otherwise successful SMB
session still works but the login may not be saved. The
legacy helper now only reports status; in particular, it no longer passes
passwords in CIFS mount options to an external command.

## Native backup/restore path and safety

- A verified session creates one noexec/nosuid/nodev mount at `/mnt/smb/share`.
  The browser verifies the mount ID, filesystem and source identity, checks
  real directory access, and refuses path escape and duplicate mounts.
- TWRP registers a session-only storage object, not a block device or fstab
  entry, and presents it in its ordinary storage selector. File IO is direct
  against `<selected folder>/TWRP/BACKUPS/<device-id>/<backup-name>`, with
  the normal archive and compression paths. There is no `/data` staging.
- A network backup always checks remote write permission and capacity, never
  reopens an existing backup folder, and verifies the generated checksums.
  The SMB transport computes SHA-256 over the actual outgoing archive bytes.
  After the server flushes them, recovery reads each archive or split chunk
  back once in up-to-256 KiB reads and checks both length and SHA-256 against
  the local write digest. Only after that does it create the normal `.sha2`
  sidecar. Missing write digests and readback failures leave the existing
  incomplete-backup protection in place. Restore still verifies the saved
  digest before writing to any target.
  A started backup is marked incomplete until success. Network errors leave
  unfinished output incomplete, with no automatic resume. Backup logs stay
  on the phone.
- The native Restore page lists network backup sets on a worker; it hides
  incomplete sets and requires a plausible archive and checksum to show an
  entry. The restore preflight checks compatible native partition entries
  and requires checksums even if native settings allow skipping them. The
  checksum loop now rejects unreadable files and missing split chunks.
  Existing target safety and exact raw-size gates remain in place.
- Discovery and browser operations run on the action worker; SMB browser
  variable updates are drained on the UI thread. The mount session is
  guarded throughout native backup/restore and cannot be disconnected while
  in use. FUSE is serialized and requests have a protocol timeout; there is
  no automatic destructive restore retry.

Only restore backup files from a trusted server that is not modifying them
during restore. Checksums detect corruption, not malicious replacement of
an archive and its checksum. A lost connection can still interrupt a
restore after a target has been modified. Do not rely on a network share
as the only copy of a critical recovery backup.

## Validation

| Check | Result |
| --- | --- |
| Device patch syntax, native theme XML, retained-menu and runtime source checks | Passed on the host |
| Existing recovery regression suite and native SMB path/selector fixtures | Passed `scripts/validate-oxygenos-ui.sh` |
| Generated Android/arm64 compiler syntax checks for every changed C++ translation unit | Passed |
| SMB 3.1.1 and 2.1 against disposable loopback Samba | Signed and guest login, special-character password, share enumeration and wrong-password rejection passed |
| Authentication prompt classification | Disposable Samba with guest-visible IPC and authentication-only IPC both passed; private-share guest denial, signed login and timeout behavior were checked separately. Prompt navigation and the uniform seven-button Network & Tools grid are covered by host GUI tests; fresh handset validation is pending. |
| Real host FUSE reads/writes | Folder creation, statvfs, fsync, checksum/readback, read-only and corruption detection, and offsets beyond 4 GiB passed |
| Independent Android/arm64 SDK transport link | Client, libsmb2 and libfuse all linked and stripped; not the packed recovery output |
| Server interruption and silent peer | FUSE read failed and the incomplete marker remained; login to a silent peer timed out |
| Real handset recovery boot, Wi-Fi, discovery and SMB transport | `9482410` booted in slot A with SELinux enforcing and GLES active. Wi-Fi obtained an IPv4 address; the handset discovered a local server and the shipped SMB client enumerated its shares over WLAN. |
| Readback and rollback | Both flashed `recovery_a` images matched their host files exactly. Independent 100 MiB copies of both prior recovery slots were checked against on-device SHA-256 before flashing. `recovery_b`, `boot_a` and slot selection stayed unchanged. |
| Native list and login GUI | The first handset test exposed an inverted empty-row test. `e5e3d04` corrects both listboxes and moves the title beside the logo. `644974a` separates the login fields and adds an artwork-based row clearance test. `3e12968` uses only the shared navigation bar on the browser page. The handset build at `62eb0bc` opened the browser from the new Network & Tools button, displayed a discovered server with no empty rows, opened the spaced login form and showed four labeled shares through List Shares. |
| Initial physical SMB backup and restore | Not tested in the initial discovery run. Recovery could not reach the disposable test server's alternate TCP port. |
| Full recoveryimage build and size | Initial and corrected builds passed all host regression, AVB, packed XML/SMB and GPU checks. The corrected image is 104,857,600 bytes including padding, with 7,970,816 bytes available before the AVB payload ceiling. Its SHA-256 is `b127fad642ef61953b7d77901c9a86731bd97a2a2f278e2ab08e9532cc77a107`. |

The next candidate also has **Settings → General → Double tap to wake**, on by
default when recovery has a working brightness control. This recovery exposes
a virtual touchscreen rather than a hardware gesture switch: software wake
turns brightness off but keeps the display/touch path ready for taps, which can
consume more idle power than a full panel suspend. It wakes to the existing
lock screen and never forwards the two wake taps to the page underneath. Turn
the setting off to restore normal full panel blanking. Physical wake and new
SMB throughput should be checked on the handset before promotion.

Mounted SMB requests allow up to 60 seconds for a response, so short HDD
writeback stalls do not have to abort an otherwise healthy backup. Login and
share discovery still have a separate 12-second deadline. A timeout or dropped
connection still fails the operation and leaves an incomplete backup excluded
from Restore; no partial restore is retried automatically.

In later handset testing, TWRP logged a completed 17-partition backup to an
SMB-attached HDD in 2,467 seconds, with 17 successful SHA-256 archive
verification messages. No physical restore was performed. The release build
then booted into TWRP on slot A and matched the host image byte-for-byte.
Sustained input, idle wake, and held-key timing were tested on the host; no
handset touch-latency benchmark was recorded.

For a from-source build:

```sh
bash device/oplus/infiniti/scripts/prepare-smb-deps.sh
bash device/oplus/infiniti/scripts/select-recovery-source.sh
bash device/oplus/infiniti/scripts/apply-recovery-patches.sh
bash device/oplus/infiniti/scripts/validate-oxygenos-ui.sh
source build/envsetup.sh
lunch twrp_infiniti
m recoveryimage
python3 -B device/oplus/infiniti/tools/verify_oxygenos_image.py \
  out/target/product/infiniti/recovery.img --root .
```

The expected artifact path is `out/target/product/infiniti/recovery.img`.
The local platform build log is `/tmp/twrp-native-smb-build.log`. The first
implementation commit is `cab35a8`. The limit remains 100 MiB. The packed-image
verifier checks the SMB native entry point, binaries and dependencies. The three
transport binaries, as extracted from the initial packed recovery, total
685,416 raw bytes and 271,391 bytes when individually compressed with LZ4.
Standalone compression is not the exact increase in the full boot image.
The isolated Samba transport
fixture is reproducible with `scripts/test-smb-samba-fixture.py` and does
not touch the phone or any existing share. No push, merge or release was performed.
