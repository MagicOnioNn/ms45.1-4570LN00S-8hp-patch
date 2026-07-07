
import sys, os

EXPECTED_SIZE = 0x70000  # 458752 bytes, MPC internal flash

# (file offset, original 4 bytes, patched 4 bytes, description)
EDITS = [
    # --- A. Decode: jump table entries + reverse case ---
    (0x45BDC, "00045C2C", "0006FF00", "A1  jumptab[11] (raw code 11) -> 7th-gear case @0x6FF00"),
    (0x45BE0, "00045C2C", "0006FF08", "A2  jumptab[12] (raw code 12) -> 8th-gear case @0x6FF08"),
    (0x45C24, "38600007", "3860000A", "A3  reverse case: li r3,7 -> li r3,10  (reverse=10)"),
    # --- B. Code cave: new 7th/8th case blocks @ 0x6FF00 (erased 0xFF) ---
    (0x6FF00, "FFFFFFFF", "38600007", "B1  cave: li r3,7   (7th gear)"),
    (0x6FF04, "FFFFFFFF", "4BFD5D2C", "B2  cave: b 0x45C30"),
    (0x6FF08, "FFFFFFFF", "38600008", "B3  cave: li r3,8   (8th gear)"),
    (0x6FF0C, "FFFFFFFF", "4BFD5D24", "B4  cave: b 0x45C30"),
    # --- C. Reverse checks: cmpwi ...,7 -> cmpwi ...,10 ---
    (0x55CB8, "2C050007", "2C05000A", "C1  reverse check gear-ratio AT:  cmpwi r5,7  -> r5,10"),
    (0x55DB8, "2C050007", "2C05000A", "C2  reverse check gear-ratio AMT: cmpwi r5,7  -> r5,10"),
    (0x6AA78, "2C1E0007", "2C1E000A", "C3  reverse check cruise:         cmpwi r30,7 -> r30,10"),
]


def h(b):
    return b.hex().upper()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    in_path = sys.argv[1]
    if len(sys.argv) > 2:
        out_path = sys.argv[2]
    else:
        root, ext = os.path.splitext(in_path)
        out_path = root + "_8gear" + (ext or ".bin")

    with open(in_path, "rb") as f:
        data = bytearray(f.read())

    print("MS45.1 4570LN00S 8-gear patcher")
    print("-------------------------------")
    print("Input : %s  (%#x bytes)" % (in_path, len(data)))

    if len(data) != EXPECTED_SIZE:
        print("WARNING: size is %#x, expected %#x (MPC internal flash)." % (len(data), EXPECTED_SIZE))
        print("         Make sure this is the MPC/internal-flash dump -- NOT the 1 MB full read.")
    print()

    # --- verify pass (no writes) ---
    to_apply, already, bad = [], 0, 0
    for off, old_h, new_h, desc in EDITS:
        old = bytes.fromhex(old_h)
        new = bytes.fromhex(new_h)
        cur = bytes(data[off:off + len(old)])
        if cur == old:
            to_apply.append((off, old, new, desc))
        elif cur == new:
            already += 1
        else:
            print("MISMATCH @ %#08x: found %s, expected %s (or patched %s)  [%s]"
                  % (off, h(cur), old_h, new_h, desc))
            bad += 1

    if bad:
        print("\n%d location(s) do not match -> WRONG FILE or WRONG VERSION." % bad)
        print("This patch is ONLY for MS45.1 version 4570LN00S. Nothing written.")
        sys.exit(2)

    if not to_apply:
        print("All edits already present -- file is already patched. Nothing to do.")
        sys.exit(0)

    # --- apply pass ---
    for off, old, new, desc in to_apply:
        data[off:off + len(new)] = new
        print("patched @ %#08x: %s -> %s   %s" % (off, h(old), h(new), desc))
    if already:
        print("(%d location(s) were already patched -- left as-is)" % already)

    with open(out_path, "wb") as f:
        f.write(data)

    print("\nDONE: %d edit(s) applied." % len(to_apply))
    print("Output: %s" % out_path)
    print("\n*** Checksums were NOT modified. Disable or recompute the internal-flash")
    print("    checksum with your flash tool before writing this to the ECU. ***")


if __name__ == "__main__":
    main()
