# WARNING EXPERIMENTAL SOFTWARE!!!
It's untested. It was created using elias's Ghidra MS45.1 disassembly project combined with Claude Opus 4.8 AI model using Max effort connected via. GhidraMCP.

If you have a BMW BN2000 Platform with MK60 DSC (Bosch DSC8 has some problems even if ECU has gear_info patched that haven't been fixed yet.) that has M54 engine and 8hp45 swapped using native configuration, feel free to test and report back.

# Siemens MS45.1 8‑Gear Patch — BMW M54 DME for ZF 8HP Retrofit

Teach a BMW **MS45.1** engine ECU to recognize **8 forward gears**, so it can run behind a retrofitted **ZF 8HP** automatic instead of topping out at 6th gear.

Ships a self‑verifying **Python patcher**. Firmware target: version **`4570LN00S`**.

> ⚠️ **This modifies ECU firmware.** It changes how the engine controller interprets transmission gear data. Read the [Disclaimer](#disclaimer). You are responsible for your vehicle, its road‑legal/emissions status, and validating the result on the bench before driving.

---

## Contents

- [Background — why the patch is needed](#background--why-the-patch-is-needed)
- [What the patch does](#what-the-patch-does)
- [Requirements & files](#requirements--files)
- [Usage](#usage)
- [The patch (byte‑level)](#the-patch-byte-level)
- [Verification](#verification)
- [CAN integration (transmission side)](#can-integration-transmission-side)
- [Checksums](#checksums)
- [Compatibility & porting](#compatibility--porting)
- [Disclaimer](#disclaimer)
- [Credits](#credits)

---

## Background — why the patch is needed

The MS45.1 receives gear position from the transmission controller (EGS) over PT‑CAN message **`0x0BA` GETRIEBEDATEN**. Inside the DME, the decoder takes the **low nibble of byte 0** — the raw gearbox status code (`ST_GR_GRB`) — and maps it to an internal `gear_info` value through a **jump table**:

| Raw code (`0x0BA` byte 0 & 0xF) | Stock `gear_info` | Meaning |
|:---:|:---:|:---|
| 5, 6, 7, 8, 9, 10 | 1, 2, 3, 4, 5, 6 | 1st–6th |
| 2 | 7 | reverse |
| 0, 1, 3, 4, 11–15 | 0 | Neutral / Park / invalid |

Stock firmware handles **6 forward gears + reverse**. The 7th/8th‑gear raw codes (`1011b`, `1100b`) fall through to the default and read as *neutral*. A ZF 8HP has 8 forward gears — so without this patch the DME never sees 7th or 8th, and its gear‑dependent logic (rev limiting, shift torque handling, etc.) is wrong in the top two gears.

## What the patch does

Extends the decode to a full 8 speeds and relocates **reverse** off of value 7 so it doesn't collide with true 7th gear:

| Raw code (`0x0BA` byte 0 & 0xF) | Patched `gear_info` | Meaning |
|:---:|:---:|:---|
| 5, 6, 7, 8, 9, 10 | 1, 2, 3, 4, 5, 6 | 1st–6th (unchanged) |
| **11 (`1011b`)** | **7** | **7th (new)** |
| **12 (`1100b`)** | **8** | **8th (new)** |
| 2 | **10** | reverse (moved from 7) |
| else | 0 | Neutral / Park / invalid |

Mechanically it:

1. **Adds two case blocks** (`li r3,7`, `li r3,8`, each branching to the shared `gear_info` store) in an erased region of flash, and points the jump‑table entries for raw codes 11/12 at them.
2. **Moves reverse** from `gear_info = 7` to `gear_info = 10` (the value 7 is now free for 7th gear).
3. **Updates the three places** that test `gear_info == 7` to mean "reverse" so they test `== 10` instead (two in the gear‑ratio routine, one in cruise control).

Downstream is safe at gear 8: `gear_info` is only ever *compared* or *copied* (never used as a raw array index), and the gear‑indexed rev‑limit tables are **interpolated** against an axis with breakpoints 0–8, so gear 8 lands on a real entry with no over‑index. All edits are in the **MPC internal flash** only.

## Requirements & files

- **Python 3** (standard library only) — for the patcher.
- Your **ECU flash tool** — this patch does **not** touch checksums; disable or recompute them there.
- The internal‑flash dump: **`4570LN00S_MPC.bin`** (448 KB, `0x70000`). **This is the only file the patch modifies.**

An MS45.1 "full read" is three regions — internal (MPC) flash, external flash, and the calibration partition. Only the **internal flash** contains the gear‑decode code, so only `4570LN00S_MPC.bin` changes. The external‑flash full read and the `.DAT` calibration file are **left untouched**.

| File | Size | Modified? |
|:---|:---|:---:|
| `4570LN00S_MPC.bin` (internal flash) | `0x70000` | **Yes** |
| `4570LN00S_fullread.bin` (external flash) | `0x100000` | No |
| `4570LN00S_partial.bin` (calib `.DAT`) | `0x1D000` | No |

## Usage

### Python

1. Both files (script + 4570LN00S MPC) has to be in the same location.
2. Type:
```bash
python ms45_4570LN00S_8gear.py (MPC_filename).bin
# -> writes (MPC_filename)_8gear.bin
```

The script:

- **Verifies** every target location against the expected original bytes *before writing anything* — if any location doesn't match (wrong file or wrong version), it aborts and writes nothing.
- Is a **no‑op** if the file is already patched.
- Leaves **checksums untouched**. (Disable checksums or calculate them using your flashtool)

Keep a backup of the original MPC.

## The patch (byte‑level)

All offsets are file offsets into 4570LN00S MPC.

**A — decode: jump table + reverse case**

| Offset | Old | New | Effect |
|:---|:---|:---|:---|
| `0x45BDC` | `00 04 5C 2C` | `00 06 FF 00` | jump‑table entry[11] (code 11) → 7th‑gear case |
| `0x45BE0` | `00 04 5C 2C` | `00 06 FF 08` | jump‑table entry[12] (code 12) → 8th‑gear case |
| `0x45C24` | `38 60 00 07` | `38 60 00 0A` | reverse case `li r3,7` → `li r3,10` |

**B — code cave: new case blocks @ `0x6FF00` (erased `0xFF`)**

| Offset | Old | New | Instruction |
|:---|:---|:---|:---|
| `0x6FF00` | `FF FF FF FF` | `38 60 00 07` | `li r3, 7` (7th) |
| `0x6FF04` | `FF FF FF FF` | `4B FD 5D 2C` | `b 0x45C30` |
| `0x6FF08` | `FF FF FF FF` | `38 60 00 08` | `li r3, 8` (8th) |
| `0x6FF0C` | `FF FF FF FF` | `4B FD 5D 24` | `b 0x45C30` |

**C — reverse checks: `cmpwi …,7` → `cmpwi …,10`**

| Offset | Old | New | Location |
|:---|:---|:---|:---|
| `0x55CB8` | `2C 05 00 07` | `2C 05 00 0A` | gear‑ratio, AT branch |
| `0x55DB8` | `2C 05 00 07` | `2C 05 00 0A` | gear‑ratio, AMT branch |
| `0x6AA78` | `2C 1E 00 07` | `2C 1E 00 0A` | cruise control |

> The two branch words in **B** (`4B FD 5D 2C`, `4B FD 5D 24`) are computed for the cave at `0x6FF00`. If you relocate the cave, recompute them — a wrong branch will crash the ECU.

## Verification

The patch was derived and verified in Ghidra on the full merged image (internal + external flash + calib):

- **One gear decoder.** `0x1A2 GETRIEBEDATEN_2` is not decoded by the DME; gear reaches it only via `0x0BA`.
- **One real‑gear write.** The only non‑zero write to `gear_info` is the `0x0BA` decoder; the sole other writer just zeros it on CAN timeout.
- **Reverse fully relocated.** All three `gear_info == 7` reverse checks are patched — nothing else compares `gear_info` to 7.
- **Gear‑8 safe downstream.** Gear‑indexed tables interpolate against a 0–8 axis; `gear_info` is never a raw index.
- **Full transmission↔engine handshake intact.** The DME's torque‑request decode (`0x0B5`), engine‑torque output (`0xA8/A9/AA`), reverse flag (`0x3B0`), KL15 (`0x130`) and speed (`0x1A0`) are all present and **gear‑count‑independent** — the `0x0B5` torque decoder was decompiled and confirmed to have no gear assumptions. `0x0BA` was the only frame that needed changing.

Also: the ECU must be **coded as automatic** so the `0x0BA` / EGS gear path is the active one.

## IMPORTANT

- Created on firmware version **`4570LN00S`** (BN2000, E6x MS45.1) using elias's MS45.1 457LO02S disassembly project and then creating another project on**`4570LN00S`** version.
- The *logic* is the same across MS45.1 versions, but **addresses differ per version** — do not blindly apply these offsets to another dump (the script guards against this by checking the original bytes).
- To port to another version (e.g. `457LO02S`): locate the `0x0BA` entry in the CAN config table, read its decoder's jump table and the `gear_info` store offset, then find the three `cmpwi …,7` reverse checks relative to that offset. The structure is identical; only the numbers move.

## Disclaimer

This is a hobbyist reverse‑engineering / retrofit tool provided **as‑is, without warranty of any kind**. Modifying engine‑control firmware can affect drivability, safety systems, emissions compliance, and road‑legal status, and can render an ECU inoperable. **Use entirely at your own risk.** Only modify hardware you own; verify every offset against your own dump; validate on a bench before driving; and comply with all laws and regulations in your jurisdiction. The authors accept no liability for any damage, loss, injury, or legal consequence arising from use of this software or information.


## Credits

Aleksandre (NDH Automotive) — for developing the native 8HP swap

Rokutis — for MSV80 patch that was an inspiration to do it

elias — for his MS45.1 Disassembly project

pazi88 — for his MS45 repo with various resources
