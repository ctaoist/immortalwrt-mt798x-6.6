#!/usr/bin/env python3
"""Check mt_wifi package variants without compiling a kernel or driver."""
import hashlib
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = {
    "mt7981-ax3000": "mt7981-ax3000",
    "mt7986-ax6000": "mt7986-ax6000",
    "mt7986-ax4200": "mt7986-ax4200-bpir3_mini",
    "mt7975-ipailna-high-power": "mt7975-ipailna-high-power",
}
PACKAGES = {
    "mt_wifi": "kmod-mt_wifi-",
    "conninfra": "kmod-conninfra-",
    "warp": "kmod-warp-",
    "wifi-profile": "wifi-dats-",
}
WIRELESS = re.compile(r"CONFIG_(MTK_|CONNINFRA_|FPGA_EARLY_PORTING|WARP_|WED_|first_card|second_card|third_card)")


def config(path):
    result = {}
    for line in path.read_text().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            result[line[2:-11]] = "n"
    return result


def make(package, variant, source, *options):
    result = subprocess.run(
        ["make", "--no-print-directory", "-r", "-s", "-j1",
         "-C", str(ROOT / "package/mtk/drivers" / package),
         f"TOPDIR={ROOT}", "DUMP=1", f"BUILD_VARIANT={variant}",
         *options, "-f", "-", "audit"],
        input="include Makefile\n" + source, text=True, capture_output=True,
        check=True,
    )
    assert not result.stderr, result.stderr
    return result.stdout


def package_records(output):
    return {
        record["Package"]: record
        for block in output.split("\n\n")
        if "Package: " in block
        for record in [dict(line.split(": ", 1) for line in block.splitlines()
                            if ": " in line)]
    }


def digest(path):
    return hashlib.sha256(path.read_bytes()).digest()


def check_packages(work):
    global_symbols = work / "kernel/symvers"
    global_symbols.mkdir(parents=True)
    for name in ("other", "mt_wifi", "conninfra", "warp"):
        (global_symbols / (name + ".symvers")).touch()
    for variant, reference in VARIANTS.items():
        symbols = work / "kernel/mtwifi" / variant / "symvers"
        symbols.mkdir(parents=True)
        (symbols / "conninfra.symvers").touch()
        expected = {k: v for k, v in config(ROOT / "defconfig" / (reference + ".config")).items()
                    if WIRELESS.match(k)}
        for package, prefix in PACKAGES.items():
            probe = "".join(f"$(info AUDIT|{k}|$(MTWIFI_{k}))\n" for k in expected)
            probe += "$(info AUDIT|build|$(PKG_BUILD_DIR))\n"
            probe += "$(info AUDIT|symvers|$(PKG_SYMVERS_DIR))\n"
            probe += "$(info AUDIT|keys|$(PKG_KCONFIG))\n"
            probe += "$(info AUDIT|hooks|$(Hooks/Prepare/Post))\n"
            probe += "$(info AUDIT_COMPILE|$(Build/Compile))\naudit:;@:\n"
            output = make(package, variant, probe,
                          f"KERNEL_BUILD_DIR={work}/kernel",
                          "CONFIG_MTK_CHIP_MT7988=y", "CONFIG_WARP_VERSION=3")
            values = dict(line.split("|", 2)[1:] for line in output.splitlines()
                          if line.startswith("AUDIT|"))
            for key, value in expected.items():
                assert values[key] == value, (package, variant, key, values[key], value)
            assert variant in values["build"], (variant, values["build"])
            if package != "wifi-profile":
                assert values["symvers"].endswith(f"mtwifi/{variant}/symvers")
                command = output.split("AUDIT_COMPILE|", 1)[1].split("\naudit", 1)[0]
                flags = dict(arg.split("=", 1) for arg in shlex.split(command)
                             if arg.startswith("CONFIG_") and "=" in arg)
                symbol_flags = [arg.split("=", 1)[1] for arg in shlex.split(command)
                                if arg.startswith("KBUILD_EXTRA_SYMBOLS=")]
                assert set(symbol_flags[-1].split()) == {
                    str(global_symbols / "other.symvers"), str(symbols / "conninfra.symvers")}
                for key in values["keys"].split():
                    reference_key = "CONFIG_" + ("MTK_" if package == "mt_wifi" else "") + key
                    value = expected.get(reference_key, "n")
                    if value == "n":
                        assert "CONFIG_" + key not in flags, (variant, key, flags.get("CONFIG_" + key))
                    else:
                        assert flags["CONFIG_" + key] == value.strip('"'), (variant, key)
            if package == "mt_wifi":
                assert "FIXUP_NEW_MCU_FW_API" in values["hooks"]
            records = package_records(output)
            record = records[prefix + variant]
            assert record["Build-Variant"] == variant
            if package == "mt_wifi":
                for dependency in ("kmod-conninfra-", "kmod-warp-", "wifi-dats-"):
                    assert "+" + dependency + variant in record["Depends"].split()
            # Every pair conflicts in exactly one direction, avoiding Kconfig cycles.
            names = [prefix + v for v in VARIANTS]
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    assert ((b in records[a].get("Conflicts", "").split()) +
                            (a in records[b].get("Conflicts", "").split())) == 1

        # Execute only the data/firmware installation recipes into a temporary
        # image directory. No module build or package build target is invoked.
        for package, installer in (("wifi-profile", "Package/wifi-dats-"),
                                   ("mt_wifi", "KernelPackage/mt_wifi-"),
                                   ("warp", "KernelPackage/warp-")):
            dest = work / variant / package
            probe = ("define AuditTarget\naudit:\n\t$(call " + installer + variant +
                     "/install,$(AUDIT_DEST))\nendef\n$(eval $(AuditTarget))\n")
            make(package, variant, probe, f"AUDIT_DEST={dest}",
                 f"PKG_BUILD_DIR={ROOT}/package/mtk/drivers/{package}/src")
            if package == "wifi-profile":
                data_dir = "mt7981" if variant.startswith("mt7981") else (
                    "mt7986-ax4200" if variant == "mt7986-ax4200" else "mt7986")
                for data in (ROOT / "package/mtk/drivers/wifi-profile/files" / data_dir).iterdir():
                    installed = dest / "etc/wireless" / (
                        data.name if data.name == "l1profile.dat" else "mediatek/" + data.name)
                    assert digest(installed) == digest(data), (variant, data.name)
            else:
                chip = "7981" if variant.startswith("mt7981") else "7986"
                assert list((dest / "lib/firmware").glob("*" + chip + "*")), (variant, package)
                other = "7986" if chip == "7981" else "7981"
                assert not list((dest / "lib/firmware").glob("*" + other + "*"))
        print(f"OK: {variant}: reference options, dependencies, firmware and data")



def check_warp_headers(work, patched):
    staging = work / "staging"
    origin = ROOT / "package/mtk/drivers/warp/src"
    headers = {p.relative_to(origin): digest(p) for p in origin.rglob("*.h")}
    installed = {}
    for variant in VARIANTS:
        build = work / "kernel/mtwifi" / variant / "warp"
        for relative in headers:
            destination = build / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin / relative, destination)
        (build / "not-a-header.c").write_text("/* Must not be staged. */\n")
        probe = ("$(info AUDIT_LIST|$(STAGING_FILES_LIST))\n"
                 "$(info AUDIT_STAMP|$(STAMP_INSTALLED))\n"
                 "define AuditTarget\naudit:\n"
                 "\t$(call Build/InstallDev,$(STAGING_DIR))\n"
                 "endef\n$(eval $(AuditTarget))\n")
        output = make("warp", variant, probe, f"STAGING_DIR={staging}",
                      f"PKG_BUILD_DIR={build}", "CONFIG_AUTOREMOVE=y")
        assert f"AUDIT_LIST|warp.{variant}.list" in output
        assert f"AUDIT_STAMP|{staging}/stamp/.warp.{variant}_installed" in output
        # Reproduce the dependency disappearing before mt_wifi starts.
        shutil.rmtree(build)
        exported = staging / "usr/include/mtwifi" / variant / "warp"
        installed[variant] = exported
        assert not build.exists()
        assert {p.relative_to(exported): digest(p) for p in exported.rglob("*")
                if p.is_file()} == headers, variant

        output = make("mt_wifi", variant,
                      "$(info AUDIT_COMPILE|$(Build/Compile))\naudit:;@:\n",
                      f"STAGING_DIR={staging}", f"KERNEL_BUILD_DIR={work}/kernel")
        command = shlex.split(output.split("AUDIT_COMPILE|", 1)[1])
        warp_flags = [arg for arg in command if arg.startswith("WARP_DIR=")]
        assert warp_flags == [f"WARP_DIR={exported}"], (variant, warp_flags)
        config_flags = [arg for arg in command if arg.startswith("CONFIG_")]
        # Evaluate the patched vendor Kbuild without invoking its module rules.
        result = subprocess.run(
            ["make", "--no-print-directory", "-rR", "-s", "-j1",
             "-f", str(patched / "mt_wifi_ap/Makefile"), "-f", "-",
             f"WIFI_DRV_PATH={ROOT}/package/mtk/drivers/mt_wifi/src",
             *config_flags, *warp_flags, "audit"],
            input="$(info AUDIT_FLAGS|$(MODULE_FLAGS))\naudit:;@:\n",
            text=True, capture_output=True, cwd=ROOT, check=True)
        assert not result.stderr, result.stderr
        include_flags = [arg for arg in shlex.split(result.stdout.split("AUDIT_FLAGS|", 1)[1])
                         if arg.startswith("-I")]
        assert f"-I{exported}" in include_flags, (variant, include_flags)
        assert f"-I{exported}/mcu" in include_flags, (variant, include_flags)
        assert not any("../warp" in arg or str(build) in arg for arg in include_flags)

    # Installing a later variant must leave every earlier header tree intact.
    for variant, exported in installed.items():
        assert {p.relative_to(exported): digest(p) for p in exported.rglob("*.h")} == headers, variant
    print(f"OK: WARP staging: {len(headers)} headers per variant survive source cleanup; isolated include paths and manifests")


def check_devices():
    source = "include " + str(ROOT / "target/linux/mediatek/image/filogic.mk") + "\n"
    source += "$(foreach d,$(TARGET_DEVICES),$(eval DEVICE_DTS:=)$(eval DEVICE_PACKAGES:=)$(eval SOC:=)$(eval $(call Device/$(d)))$(info DEVICE|$(d)|$(DEVICE_PACKAGES)))\naudit:;@:\n"
    output = subprocess.run(["make", "-rR", "-s", "-n", "-j1", "-f", "-", "audit"],
                            input=source, text=True, capture_output=True, cwd=ROOT, check=True).stdout
    devices = {line.split("|", 2)[1]: line.split("|", 2)[2].split()
               for line in output.splitlines() if line.startswith("DEVICE|")}
    converted = 0
    for name, packages in devices.items():
        drivers = {p for p in packages if p.startswith("kmod-mt_wifi-")}
        assert len(drivers) <= 1, (name, drivers)
        if drivers:
            converted += 1
            assert "kmod-mt7915e" not in packages, name
            assert {"mtwifi-cfg", "luci-app-mtwifi-cfg", "-wpad-openssl"} <= set(packages)
    for name, variant in (("sl_3000-emmc", "mt7981-ax3000"),
                          ("glinet_gl-mt6000", "mt7986-ax6000"),
                          ("bananapi_bpi-r3-mini", "mt7986-ax4200"),
                          ("ruijie_rg-x60-new", "mt7975-ipailna-high-power")):
        assert "kmod-mt_wifi-" + variant in devices[name], name
    assert not any(p.startswith("kmod-mt_wifi-") for p in devices["glinet_gl-mt2500"])
    assert "kmod-mt7915e" in devices["cudy_wr3000-v1"]
    print(f"OK: {len(devices)} device definitions, {converted} mapped to reference profiles")


def check_configuration():
    current = config(ROOT / ".config")
    if current.get("CONFIG_TARGET_mediatek_filogic") != "y":
        return
    if current.get("CONFIG_TARGET_ALL_PROFILES") == "y":
        assert current.get("CONFIG_TARGET_PER_DEVICE_ROOTFS") == "y"
        for prefix in PACKAGES.values():
            for variant in VARIANTS:
                assert current.get("CONFIG_PACKAGE_" + prefix + variant) == "m", (prefix, variant)
        for package in ("mtwifi-cfg", "luci-app-mtwifi-cfg"):
            assert current.get("CONFIG_PACKAGE_" + package) == "m", package
        print("OK: all-device .config keeps variant packages out of the shared rootfs")


def check_caldata(work):
    original = (ROOT / "target/linux/mediatek/filogic/base-files/lib/preinit/90_extract_caldata").read_text()
    function = original.split("mtwifi_extract_sl3000() {", 1)[1].split("\ndo_extract_caldata()", 1)[0]
    function = "mtwifi_extract_sl3000() {" + function
    data = b"\x81\x79" + bytes(range(256)) * 256
    for name, content, enabled, success in (
            ("valid", data, True, True),
            ("short", data[:4096], True, False),
            ("wrong-chip", b"\x86\x79" + data[2:], True, False),
            ("no-partition", None, True, False),
            ("no-wifi", None, False, True)):
        directory = work / ("caldata-" + name)
        directory.mkdir()
        factory = directory / "factory"
        if content is not None:
            factory.write_bytes(content)
        firmware = directory / "firmware"
        firmware.mkdir()
        profile = directory / "l1profile.dat"
        if enabled:
            profile.touch()
        image = directory / "eeprom"
        source = function.replace("/tmp/mtwifi-sl3000-eeprom", str(image))
        source = source.replace("/etc/wireless/l1profile.dat", str(profile))
        source = source.replace("/lib/firmware/", str(firmware) + "/")
        source = ("find_mmc_part() { printf '%s' " +
                  shlex.quote(str(factory) if content is not None else "") + "; }\n" +
                  source + "\nmtwifi_extract_sl3000\n")
        result = subprocess.run(["sh"], input=source, text=True, capture_output=True)
        assert (result.returncode == 0) == success, (name, result.stderr)
        if content is not None:
            assert factory.read_bytes() == content, name
        if name == "valid":
            for filename in ("e2p", "MT7981_iPAiLNA_EEPROM.bin"):
                assert (firmware / filename).read_bytes() == data
                assert (firmware / filename).is_symlink()
        else:
            assert not list(firmware.iterdir()), name
    print("OK: SL3000 EEPROM extraction: valid, short, wrong chip, missing partition, no Wi-Fi")


def check_patches(work):
    source = ROOT / "package/mtk/drivers/mt_wifi"
    patches = sorted((source / "patches").glob("*.patch"))
    optional = [source / "files/fix-new-mcu-fw-api.patch",
                source / "files/eeprom-flash-api.patch"]
    directory = work / "patches"
    directory.mkdir()
    paths = set()
    for patch in patches + optional:
        for path in re.findall(r"^(?:---|\+\+\+) ([^\t\n ]+)", patch.read_text(), re.M):
            if path != "/dev/null":
                paths.add(path.split("/", 1)[-1])
    for path in paths:
        origin = source / "src" / path
        if origin.is_file():
            destination = directory / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, destination)
    for patch in patches + optional:
        result = subprocess.run(["patch", "--batch", "--forward", "-p1", "-d", str(directory)],
                                input=patch.read_bytes(), capture_output=True)
        assert result.returncode == 0, (patch.name, result.stdout.decode(), result.stderr.decode())
    # The copied source tree is only used for patch application, never compiled.
    print(f"OK: {len(patches)} driver patches and both optional firmware patches")
    return directory


def main():
    (ROOT / "tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mtwifi-check-", dir=ROOT / "tmp") as directory:
        check_packages(Path(directory))
        check_caldata(Path(directory))
        patched = check_patches(Path(directory))
        check_warp_headers(Path(directory), patched)
    check_devices()
    check_configuration()


if __name__ == "__main__":
    main()
