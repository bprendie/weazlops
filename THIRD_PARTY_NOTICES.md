# Third-party software notices

## SquachWatch-CYD

- Authors: skizzophrenic and SquachWatch-CYD contributors.
- Repository: https://github.com/skizzophrenic/SquachWatch-CYD
- Version incorporated: commit `3e9be6c02265b14c798e58da01a0913866143b0f`.
- Source: `src/signatures.cpp`, selected `kUuidTable` rows and `isIBeacon()`.
- License: GNU GPL version 3; full upstream license retained in `firmware/third_party/squachwatch/LICENSE`.
- Original selected excerpts and full-source SHA-256: `firmware/third_party/squachwatch/upstream-excerpts.txt` and `provenance.json`.
- Adaptation: `firmware/third_party/squachwatch/tracker_signatures.hpp`.
- WZLG0A5T modifications, 2026-11-04: selected service families, changed data types and lookup interface, exact-length iBeacon validation, new bounded AD parser integration and local evidence/confidence/quip policy. Service-list evidence alone does not alert; nonempty service data identifies a suspected protocol family, not an exact model.

The broad upstream AirTag matcher, its nyanBOX-derived implementation, generic-chipset camera/Flock fallbacks, UI, radio code and complete database are **not** incorporated. The Apple Offline Finding matcher was written for this project from the documented packet format; it rejects proximity-pairing/AirPods frames. Attribution is not a claim of upstream endorsement or physical validation.

## Existing build dependencies

These are fetched at the versions in `platformio.ini`; their own license files and notices remain authoritative and must accompany distributions as required. No dependency is relicensed by this project's notice.

- NimBLE-Arduino 1.4.3: Apache-2.0, with upstream NimBLE notices.
- Arduino-ESP32 2.0.17, provided by PlatformIO espressif32 6.9.0: LGPL-2.1 and separately licensed ESP-IDF/components. Retain component notices and provide required corresponding source/relinking materials where applicable.
- Browser Three.js and existing bundled assets: retain their existing MIT notices and other asset-specific notices. The firmware does not compile browser code.

A public or device release should include the exact dependency sources/notices and build/install instructions alongside this repository's corresponding source. No public release is performed by this change.

## 0.8 follow-up review and selected signature facts

Reviewed SquachWatch-CYD commit `bd84f6a353039582ae11da72f7876288b7bed873`, by skizzophrenic and contributors, under the same GPL-3.0 license. Selected vendor-prefix rows, Flipper service values, FS accessory-name conventions and the BWCDEVICE UUID marker inform `firmware/bench/product_signatures.hpp` and `ble_details.hpp`. Source excerpts and complete-source SHA-256 hashes are retained in `firmware/third_party/squachwatch/review-bd84f6a/`. Local modifications use strict field boundaries, weak vendor-only labels, conservative alert gates, and malformed/negative fixtures. No complete upstream database, radio engine, UI or attack functionality is incorporated.

Remote ID wire layouts were checked against upstream `src/remote_id.cpp` and the Apache-2.0 OpenDroneID reference (`opendroneid/opendroneid-core-c`, `libopendroneid/opendroneid.c` and header). Pwnagotchi IE framing was checked against `evilsocket/pwngrid`, `wifi/defines.go`, `pack.go`, `unpack.go` (GPL-3.0). These protocol parsers are local implementations; OpenDroneID and pwngrid code is not compiled or copied into them. The current Pwnagotchi parser supports bounded uncompressed self-description JSON only, not compressed or fragmented pwngrid streams.

## 0.11.0-dev16 signature expansion

Additional selected rows from the same SquachWatch-CYD `bd84f6a353039582ae11da72f7876288b7bed873` source are adapted in `firmware/bench/signature_hints.hpp`: exact Raven service UUIDs, bodycam/glasses/serial-module hints, additional SSID conventions, and selected drone/camera vendor prefixes. Original selected lines and the verified full-source SHA-256 are retained in `firmware/third_party/squachwatch/review-bd84f6a/extension-2026-11-05-excerpts.txt`; the existing GPL-3.0 license applies. These are bounded, non-alerting local adaptations, not upstream confidence policy. Locally assigned Hak5-style addresses are explicitly hints, never registered OUIs. Generic camera-chipset prefixes and broad Raven-range matching are not imported. Source attribution is not physical-product validation or a fresh independent registry audit.

The eight new commentary pairs in `Weazl_quips.md` were supplied verbatim by the owner. They are separate from signature evidence and upstream material.

## Buddy HKDF helper

`firmware/target/mbedtls_hkdf.c` derives from Mbed TLS v2.28.9 `library/hkdf.c`, copyright The Mbed TLS Contributors, SPDX Apache-2.0 OR GPL-2.0-or-later (used under GPL-2.0-or-later). Source: https://github.com/Mbed-TLS/mbedtls/blob/v2.28.9/library/hkdf.c . Original SHA-256: `c23ddf951e5037cf279a8974a6b228711ecdc0e7ada33b0eb3937f540079391c`. Local integration replaces the library-internal common header with the pinned SDK config, enables this otherwise unlinked helper and supplies the compatible corruption error constant. AES-GCM/HMAC remain the SDK library implementations.
