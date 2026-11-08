# Cellular data status indicator

**Historical patch contract:** the final OxygenOS dashboard intentionally removes
cellular bars/arrows at the owner's request. Patches 0031/0033 retain dormant
variables and regression coverage for the earlier presentation; the description
below is not the current visible status bar. No SIM/eSIM data service or calling
stack is enabled by this preview release.

Patch `0031-theme-cellular-data-status-icon.patch` adds a small blue pair of
up/down data arrows to the left of the cellular signal bars and Wi-Fi in the
OnePlus 15 portrait status bar. Eight native XML fills draw the icon; no PNG,
font, external theme pack, raster asset or separate GUI executable is required.
The existing Wi-Fi resource, placement, variable and WLAN pages are unchanged.
A small native conditional-fill update hook requests a page repaint only when
visibility changes, so connecting and disconnecting do not leave a stale icon.

`tw_cellular_connected` defaults to `0` and is not a saved preference. Every
primitive is visible only when this variable is `1`. The arrows indicate an
available cellular data connection, not measured signal strength, LTE/5G type
or instantaneous packet activity.

## Backend contract

Patch `0033-theme-visible-cellular-signal-bars.patch` additionally draws four
ascending outlined bars immediately beside Wi-Fi (an eight-pixel minimum gap).
They remain visible even with no modem/data service. Offline/disabled data uses
gray; `tw_cellular_connected=1` lights the outlines blue and shows the separate
data arrows. A small gray X means **no verified signal reading or data path**.
The current offline modem therefore shows gray empty bars with X. Wi-Fi never
lights the cellular icon. No fixed LTE/5G label is claimed without a radio report.

`tw_cellular_signal_valid=0` and `tw_cellular_signal_level=-1` are non-persistent
defaults. A future radio controller may set level `0` through `4` and valid `1`
only from fresh, validated signal measurements/registration information. Valid
levels `1` through `4` fill the corresponding number of bars (blue when data is
connected, gray otherwise); valid level `0` leaves empty outlines. Blue outlines
with no signal measurement mean only a verified data path, not four-bar signal
strength. Missing, stale, unavailable or offline
readings must reset valid to `0` and level to `-1`. Signal strength and cellular
data connectivity are separate: the original data arrows remain gated by
`tw_cellular_connected=1`. No live signal backend is implemented by these patches.

A future native cellular controller must publish the GUI state through
`DataManager::SetValue("tw_cellular_connected", "1")` only after confirming a
usable data connection on the selected subscription and interface. It must
publish `0` on disconnect, teardown, shutdown or failure. SIM presence, modem
`running`, registration alone, an RMNET node, or an unverified cached property
must not light the icon. No connected flag is currently published by the radio
experiments, which have not established cellular Internet in recovery.

This is the UI consumer, **not** cellular-data enablement. It does not start a
modem, change a SIM/eSIM profile, expose cellular restore controls, weaken
restore guards or make the experimental radio stack safe for release.

## Verification

`scripts/test-cellular-status.py` checks the off-by-default state, exact
connected condition, vector bounds, blue accent, absence of raster assets and
preservation of the Wi-Fi indicator. A portable C++ fixture exercises the actual
fill-update method for show, hide and unchanged states. The recovery-patch application
script runs these checks, including in the existing build workflow.
Additional cases check always-visible outlines, data-driven blue tint,
unknown-state X, valid signal levels 0-4, gray inactive readings, invalid readings
and non-overlapping placement directly next to Wi-Fi.

Any device-side visibility preview must be clearly labeled as a GUI preview
with real cellular data offline. Do not represent a forced GUI flag as a
successful cellular connection, and restore the indicator to off afterwards.
