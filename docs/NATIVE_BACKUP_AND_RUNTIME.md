# Native TWRP backups and recovery-runtime experiments

## Scope

The active development branch is `feature/twrp-native-backup-gpu`, based on
stable `twrp-16.0` (`b3d2b743fdab9fe60b0a92d9e448c49ac996283f`). The old
`feature/twrp-ufs-manager` branch is preserved as history. Its manager, widgets,
utility and theme pages are **not** included in this branch or new image.
Incremental theme builds also remove its old owned pages and Advanced entry.

Use normal **Backup → select partitions/storage → swipe**, and the normal
**Restore** screen. The historical `twrp-partition-backup` terminal command now
opens that screen instead of making unchecked flat `dd` files. Existing WLAN,
Wi-Fi icon/state, OLED styling, charging, pigz -9 / Zstd -11 file compression,
decryption startup and A/B recovery-clone protection are retained.

## Partition coverage

There are 51 configured native backup targets. Read-only inventory in the
installed recovery resolved 48; this firmware has no `system_dlkm_oki`,
`my_company` or `my_preload` target. These remain optional for other firmware.
Presence is not proof that an image can currently be restored safely.

| Group | Native backup method and restore conditions |
| --- | --- |
| Data | Decrypted file-level archive; normal data-media exclusion remains |
| Internal media | File archive to external/ADB storage, not onto its own filesystem |
| Boot, init_boot, vendor_boot, DTBO, recovery, VBMeta | Full active-slot image; matching device/firmware and an unmounted, writable target |
| System, vendor, product, ODM, DLKM and OEM logical images | Full individual logical image; valid existing mapping/size, no mounted users/holders, compatible AVB/firmware |
| Persist, modem, DSP, Bluetooth, EFS and OEM reserve/splash images | Existing filesystem/raw choices; same-handset firmware-compatible restoration, quiescent target |

The added entries cover `fs_bkup`, `mdm1oemnvbktmp`, `oplusreserve1`,
`oplusreserve3`, `oplusreserve5`, active-slot `splash`, and `splash_odm`.
They are backup/restore entries, not newly exposed generic Install Image targets.
Modem/EFS/calibration backups must not be transplanted between handsets.

Whole LUNs, GPT creation/restoration, `super` metadata rewriting, raw userdata,
RPMB, device secrets and unqualified boot-chain/security partitions are not
automatically exposed as ordinary restore targets. A raw encrypted userdata
image cannot be stored inside itself. File-level Data plus an external media
backup remains the supported normal workflow. Restoring metadata/key material
requires a compatible userdata/key state; an image checksum cannot prove that.

`scripts/audit-native-backups.py --live` produces a read-only JSON inventory of
normal targets and exclusions using an already-rooted ADB session. It does not
mount, flash, toggle the modem, or include SIM identifiers/PINs/GPT UUIDs.

## Native-engine safeguards

Patch `0027` retains the missing-storage-object null guard discovered during
the earlier project. Patch `0028` hardens the existing native engine:

- Raw .win restores must be complete partition-sized images, not zero-byte,
  truncated, oversized or sparse flash payloads. Ordinary Install Image/ZIP
  workflows are separate and are not changed by this rule.
- Raw restore preflight checks actual block geometry, block read-only status,
  mounted major/minor devices, device-mapper holders and whether the archive
  resides on its target. Selected raw targets/subpartitions are checked before
  the restore write loop. Targets are opened exclusively without truncation.
- Raw backups reject writable-mounted sources and unsafe self-destinations.
  Immutable read-only mounts can still be read; this is not a general snapshot
  or modem-quiescence guarantee.
- Recursive file backups are rejected, except the existing Data workflow that
  explicitly excludes/preserves media. Non-data file restores cannot wipe the
  filesystem containing their archive.
- Native raw I/O handles interrupted/short reads and writes, checks durable
  destination sync errors, and preserves ADB FIFO semantics. This does not make
  an interrupted physical restore atomic.
- The capacity calculation no longer underflows below its 32 MiB reserve.
- New on-storage backup sessions retain `.twrp-incomplete` until completion.
  Restore checks the marker **after mounting the selected storage**, regardless
  of the user's digest-check setting. Legacy archives still use TWRP's existing
  format and digest handling; their historical completeness cannot be inferred.

An unmounted/read-write mapping may need a deliberate recovery preparation
step before logical image restoration. The tool does not forcibly stop crypto
services, tear down snapshots, resize mappings or bypass a failed guard.

## GPU compositor — experimental implementation

Patch `0029` now integrates GLES composition of fills, textures and text masks,
with the existing DRM scanout and a CPU fallback/replay journal. The initial
missing KGSL node was resolved with the active firmware's normal module load;
no module was force-loaded. Actual recovery shader/readback, pixel conformance
and live RAM-only GUI tests passed on the connected Adreno 840 phone.

This remains experimental and readback-based, not zero-copy display acceleration
or a blanket performance gain. See [RECOVERY_GPU.md](RECOVERY_GPU.md) for startup,
dependencies, measured limitations, diagnostics and the restoration safety boundary.

## Can radio, IMS and audio files be linked from Android?

Yes, some native files can be reused from read-only mounts of the installed
ROM, as with the active decryption HALs. A link only resolves a filename: it
does not supply compatible libraries, Binder services, device nodes, init
ordering, SELinux rules, vendor configuration, carrier provisioning or audio
routing. Globally mixing stock and recovery library paths is not a safe loader
strategy; isolated namespaces and exact dependency qualification are needed.

The observed ROM uses `qcrilNrd`, `imsdaemon`, `ims-dataservice-daemon`,
`ims_rtp_daemon`, `audiohalservice.qti`, `audioserver`, `com.android.phone` and
`com.qti.phone`, along with Android Telecom/Telephony/IMS services. ART and the
framework are present in Android, not in this minimal recovery environment.

An Android dialer app would depend on those framework services. A native TWRP
accept/decline UI could avoid ART for its UI, but would still need a working
native modem/IMS registration, incoming-call control and bidirectional audio
implementation, or a port/replacement of the missing framework behavior.
Neither symlinks nor an APK alone supplies that stack.

Reference architecture: [AOSP IMS](https://source.android.com/docs/core/connect/ims)
and [Android InCallService](https://developer.android.com/reference/android/telecom/InCallService).

This remains a separate research direction, not an enabled feature. A running
modem can update NV/EFS state independently of Linux mounts; cellular mode must
be mutually exclusive with affected backup/restore/wipe/flash operations. Merely
stopping a radio daemon is not proof that the modem is quiescent. Incoming calls,
carrier IMS, call audio and emergency calling have not been implemented/tested.
No radio services were enabled and no modem/NV settings were changed here.

## Validation and deployment boundary

Host integration tests cover target/slot selection, excluded targets, retired
theme cleanup/idempotence, Wi-Fi preservation and engine guard ordering. Portable
C++ fixtures cover exact image lengths, capacity underflow, interrupted/short
I/O, mounted/read-only devices and mapper holders using disposable directories.
Existing OTA, sideload, Wi-Fi and decrypt-readiness source checks are retained.

The new image is built locally and remains experimental. Phone testing used
the already-installed recovery with temporary RAM-only code/firmware and normal
module loading; no new recovery image was installed. Both recovery partition
hashes remained `401ef2ccba7bcdb4a707ba3ccfb20aca02bb3e3861d9c69ea49f022a2de5985f`.
No new image was flashed; no destructive restore was tested. New engine behavior
and added native GUI selections still require physical qualification before a
stable release. No GitHub workflow or release was started.
