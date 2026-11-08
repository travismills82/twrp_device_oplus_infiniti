# Native Wi-Fi list and password entry

The OxygenOS page uses the existing native `GUIWlanList`, scan/connect actions,
keyboard, saved-profile helper and Wi-Fi controller. The supplied `wifi.png` is
a visual reference only; it is not copied into recovery. No image assets or
external theme pack are added.

The page shows a dark network list with white Wi-Fi icons, SSID names,
right-aligned measured dBm values, thin separators, a red scrollbar, a real
network count and scan status. Tap Scan to refresh. Each row represents the
existing backend's scan result; multiple access points can share an SSID.

Tapping a secured row publishes its encryption type and SSID, clears a stale
password, then opens native `wlan_password` with the keyboard focused. It does
not require the old selection/Next dialog. The password is masked and cleared
when cancelling. The input's constructor text is empty so it cannot paint a
previous password before the native mask is loaded. Open networks retain the
original direct-connect behavior.

Tools mode retains Get Status, Test Network, Scan, Connect, Start Service and
Stop Service on the same WLAN page/backing log. Back returns to the network list.
There is exactly one unconditional Back key binding. Separate conditional
set-only actions select its destination; this avoids the pinned framework's
automatic execution of a conditional root key action on page focus.
Normal footer navigation, status Wi-Fi icon, `tw_wifi_connected`, remembered
profiles and auto-connect are preserved. No network is considered connected just
because it was tapped or a scan succeeded.

Patch `0040` adds optional row actions and a signal column; existing legacy
WLAN selectors without those options keep their original behavior. Scan workers
publish a pending-list flag; only the GUI thread replaces visible rows/scroll
state. The log buffer is synchronized, producers do not scroll it, and idle log
updates no longer force a continuous render loop or draw an intermediate frame.
The old CRLF/trailing-space log source is normalized once before the semantic
patch so fresh/repeat patch application remains whitespace-clean.

The existing personal saved-profile path remains `/data/twrp/wifi`, outside
user-0 CE storage. `/data` must still be mountable; a whole-filesystem/metadata
decryption failure or wipe can make profiles unavailable. This UI does not
change encryption or introduce an unencrypted alternative credential store.

Validation includes source contracts for row selection, correct encryption
ordering, keyboard focus/masking/cancellation, live scan status, tool preservation
and worker/GUI ownership. Physical row-tap, keyboard, scan, connectivity and
graphics results are recorded with the exact tested build, not inferred from
these host checks.

On 2026-11-07 the locally built test image `42286f1c...` was cold-flashed only
to the explicitly approved recovery_a. Decryption, saved Wi-Fi reconnection,
native scan, three row/keyboard/Back cycles, masked test-character entry,
password clearing on cancel, and Tools/list Back routing passed. The saved
Samsung-style right-side Back preference was preserved. The separate GPU redraw
investigation remains open; this is not a stable-GPU or full-release claim.
Host gates pass 119 Python cases, native fixtures and nine installer tests;
all 40 patches replay cleanly and repeat without source changes. These physical
tests preceded the later [preview publication](releases/2026-11-07-modern-ui-wifi.md)
request; no GitHub build or additional flash is part of publication.
