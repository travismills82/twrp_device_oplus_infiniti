# Active-slot TWRP updater for OnePlus 15

Development branch: `feature/active-slot-twrp-updater`. Based on the published
`twrp-16.0` device tree at `81ad372` and pinned TWRP source `6bd8134ec8ff`.
Recovery implementation commits: `8f82c43` and `a861753`. The development
image embeds `a861753`. Protected release-job integration: `6611c26`.
The stable branch and published assets are untouched.

## Recovery UI

The Device & System tile at `[802, 904, 230, 146]` is now **Check for TWRP Updates**.
The four Quick Actions are unchanged, and the native Reboot page is accessible
through **Reboot Menu** on the update page. The tile and detail page report live
state, not a fixed version. The tile background always uses the same charcoal
style as its neighbors; only the icon indicates availability:

| State | Tile foreground | Tap behavior |
| --- | --- | --- |
| Offline or current | White icon | Show status or check again |
| Checking | White icon | Open the status page; do not start another check |
| Newer signed compatible release | Green icon | Start update without another confirmation |
| Downloading, installing, or reading back | White icon with percentage | Show current stage, progress, and download speed |
| Check or install failed | White icon | Show the error and allow a new check |

The status page shows installed and offered build identities, active slot,
installation target, and signed release notes. Stable is the default; the preview
toggle opts in for this recovery session only and invalidates the current offer.
The GUI uses a bounded nonblocking pipe to a separate recovery helper. Only the
main GUI loop processes its status messages. Checking does not take the normal
TWRP operation lock; installing does, including the native ORS busy gate.

## Release selection, version and authenticity

The helper reads the first 20 releases from the
[official GitHub Releases API](https://docs.github.com/en/rest/releases/releases#list-releases).
It ignores drafts, preview releases unless selected, missing assets, mismatched
repository URLs, and incompatible manifests. It chooses the highest eligible
**signed build number**, not the newest date or name. The booted image contains
`/system/etc/op15-updater-identity.json` with schema, codename, TWRP version,
build, timestamp, device-tree commit, channel, image size, compatibility
protocol and a raw Ed25519 public key. CI uses
`GITHUB_RUN_NUMBER * 1000 + GITHUB_RUN_ATTEMPT`. Do not reset or reuse this
sequence for future releases; same-build and downgrade attempts are rejected.

The canonical [release assets](https://docs.github.com/en/rest/releases/assets)
are `recovery.img`, `twrp-update.json`, `twrp-update.json.sig` and `SHA256SUMS`.
The existing slot-A-only flashable ZIP remains a separate asset; it is not
consumed by the in-recovery updater. The manifest is signed as exact UTF-8
bytes using detached, 64-byte Ed25519. The JSON contains the build identity
except for the trust key, and adds `tag`, `asset`, `sha256`, `notes` and
`profiles`. The signed image hash covers **all 104,857,600 bytes**, including
padding and the recovery AVB footer. The separate checksum is a convenience
for human verification, not the source of trust. A hash or key obtained from
an unsigned release is never accepted.

A compatible profile includes the bootloader project (`24831` or `24863`),
one slot (`_a` or `_b`), and lowercase SHA-256 hashes of the **entire** active
`boot`, `init_boot`, `vendor_boot`, `dtbo`, `vbmeta` and **existing** recovery
partitions, in fields `boot`, `init_boot`, `vendor_boot`, `dtbo`, `vbmeta`,
and `from_recovery`. Qualify the exact firmware and kernel per supported slot
before approving a signing profile. In particular, do not copy a profile from
A to B or treat a matching marketing version as evidence. A custom kernel or
firmware change invalidates the corresponding profile until it is requalified.

Auto-check runs on Wi-Fi connection, with backoff between checks. The bundled
curl and CA store are reused, bound to `wlan0` with validated HTTPS/TLS 1.2+
and HTTPS-only redirects. The check is bounded by HTTP and aggregate timeouts.
The image is streamed to mounted Data after a space check; an interrupted
download may retry once from an empty file. No downloaded code is executed.
GitHub throttling/HTTP errors, DNS, TLS, missing connectivity, length mismatch,
and signature failures do not initiate writes.

## Installation and recovery

1. Require supported TWRP and unlocked/orange bootloader state. The slot must
   agree between `ro.boot.slot_suffix` and the bootloader-provided kernel
   bootconfig or command line; inconsistent or absent information is refused.
   Resolve the block device from the bootdevice/by-name aliases, require agreement
   when both exist, and confirm the actual kernel GPT `PARTNAME` and size.
2. Re-fetch and verify the exact offered build/hash on tap. Verify the
   image's complete signed SHA-256, v4 Android ramdisk-only boot format,
   footer bounds, AVB signature, salted recovery payload hash and partition
   descriptor. Require the same AVB key, algorithm and rollback policy as the
   known installed recovery. The project's AVB test key is **not** the GitHub
   signing key. This does not alter AVB or guarantee that a maintainer's
   inaccurate compatibility profile will boot.
3. Require at least 50% battery, mounted Data and Metadata, a known clean
   bootloader virtual A/B state, and a shared libsnapshot metadata lock. Refuse
   stale snapshot boot indicators, merge records, snapshot records or active
   COW/base/snapshot mappings rather than attempting to repair an OTA. Unreadable
   or unrecognizable OTA state is also a blocker.
4. Keep and verify a full rollback file under root-only `/data/twrp/updater`,
   outside recovery and excluded from normal Data archives. Recheck the slot,
   OTA state, power and source hashes. Open only the confirmed recovery target
   exclusively, refuse mounts/holders, check its cache-flush support and
   durably mark the transaction as writing before the first write.
5. Stream writes with checked counts, synchronize and flush the block cache,
   then hash a complete readback. Only an exact match marks the journal
   verified and requests TWRP's native reboot to **recovery**. The updater
   never writes the inactive recovery or any other raw partition, and never
   changes the Android boot slot.
6. On the next recovery boot, verify the build, commit, slot and complete image
   hash against the receipt. A different kernel boot ID is required. A
   verified receipt is consumed once and the UI reports success. Neither
   interrupted nor completed receipts can initiate another write or reboot.

An interrupted recovery write is not atomic. A failed write or checksum keeps
the current recovery running and preserves the verified rollback and receipt
without attempting another write to a suspect target. Do not reboot blindly.
Inspect the device state, preserve the rollback independently if still
accessible, and use a known bootloader recovery path under the usual rollback
safety procedure. A file on Data does not guarantee access after a failure;
retain a verified independent image when qualifying a device. An unsupported
SELinux, block-cache, OTA-metadata, or firmware configuration blocks writes;
the updater does not relax enforcement or bypass these checks.

## Maintainer setup

- Generate and securely retain a dedicated Ed25519 private key offline,
  outside the Git checkout. Bootstrap a verified recovery with the matching
  public key; release verification pins it before any network request.
  Existing unsigned releases are ignored. Key rotation requires a new
  verified bootstrap with this format.
- Configure the protected GitHub environment `op15-updater-release` for the
  canonical repository and reviewed `twrp-16.0` branch. Provide
  `OP15_UPDATER_SIGNING_KEY` as an environment secret and
  `OP15_UPDATER_COMPATIBILITY_PROFILES` as an environment variable (JSON array
  of boot-qualified profiles). Set `OP15_UPDATER_PUBLIC_KEY` as a repository
  variable (32-byte raw public key, 64 lowercase hex characters) so the
  unprivileged build job can embed it. Require a maintainer reviewer. The
  private key is only available to the separate protected release job, in a
  mode-0600 temporary file removed by its signing step.
- Workflow dispatch does **not** publish by default. Builds are retained as
  workflow artifacts. For a signed release, select `PUBLISH_RELEASE` explicitly
  from the canonical branch. The workflow verifies the reviewed commit and
  the packed identity in both the build and protected release jobs, then signs
  the manifest and publishes only the verified recovery and ZIP assets. Prerelease
  publication is explicit. `tools/op15_update_release.py` also supports offline
  packaging with the same key, format and compatibility checks.

## Validation and artifacts

Only host fixtures and local builds were authorized. No device was flashed or
rebooted, no release or Actions run was created, and no production signing key
or phone-derived compatibility profile was generated.

The tests cover signed selection and tampering, bounded/incomplete transfers,
slot A and B selection, ambiguity and wrong-device rejection, exact isolated
writes, write/readback failures, OTA guard states, reboot receipt gating, and
generated UI routes and states. An ephemeral Ed25519 key seals a fixture
manifest, and the native AVB validator checks the packed image and rejects
disposable copies with a corrupt payload or footer. The hardware gates still
need qualification on an independently recoverable device: GitHub check over
recovery Wi-Fi, exact slot and OTA evidence, an authorized signed install and
whole-partition readback, and a verified reboot on the same slot. Prove slot A
and slot B independently before permitting each in production.

Local build command: `source build/envsetup.sh; lunch twrp_infiniti; m recoveryimage`.
Initial candidate directory: `/home/travis/Android/op15-updater-build.K5i2jL/verified/`.
Development builds have no production public key and cannot offer or install
an update.

| Check | Result |
| --- | --- |
| Pinned-source patch replay and generated UI comparison | PASS, including exact regenerated XML equality and the existing theme memory budget |
| Shell, Python and workflow syntax; `git diff --check` | PASS; workflow was not dispatched |
| Existing source/host regression suites | PASS: 136 Python unit tests, native fixture binaries, font sanitizers, A/B OTA, backup, decryption, GPU, Wi-Fi, sideload, charging and SMB contracts |
| Isolated Samba regression using the unchanged host client | PASS: signed SMB 3.1.1, FUSE I/O, timeout, verification and interruption fixtures |
| New updater checks | PASS: signed releases, version/slot/OTA gates, bounded transfers, writes/readback, reboot receipt and native UI contracts |
| Final packed image and AVB | PASS: arm64 updater, exact embedded identity, native UI, GPU and existing helper payloads; signed host fixture rejected corrupt AVB payload and footer copies |
| Slot-A-only ZIP | PASS: ZIP integrity and all nine installer fixtures, including no writes to `recovery_b` |
| Production GitHub release and physical updater workflow | NOT TESTED; key, approved profiles and a device test are still required |

- `recovery.img`: **104,857,600 bytes**, at the unchanged 100 MiB limit;
  SHA-256 `7d4d8be0b266edcf1983ab3b741afc87b0f7c13fb1531d801f9906d75d05fe7a`.
- `TWRP-infiniti-updater-test.zip`: **84,106,055 bytes**;
  SHA-256 `2a7748b4d617c36ca4f29637d07bda16433d0727001675331da8fa3f51f249ab`.
- The updater ELF is **203,752 bytes**, or **103,853 bytes** as standalone
  legacy LZ4. The full compressed boot payload before the AVB footer grew from
  **96,931,840** to **97,054,720 bytes** (+**122,880 bytes**), leaving
  **7,733,248 bytes** below the AVB payload limit. The padded image size did not
  change. No new runtime library was bundled specifically for the updater.

The tile appearance refresh is development build 2 from `7810556`.
`/home/travis/Android/op15-updater-build.K5i2jL/tile-refresh/recovery.img`
is **104,857,600 bytes** with SHA-256
`b354d68f0191ddf0a41d85a0318c4e3d48a46189a7f32aba64090c8f88d678df`.
The dashboard and updater tests, clean patch replay, and packed UI/AVB
verification passed. This revision was not flashed.
