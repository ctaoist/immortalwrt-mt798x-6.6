#!/usr/bin/env python3
"""Check SDK relocation and ImageBuilder package exports without compilation."""

import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("export_toolchain", ROOT / "target/sdk/export-toolchain.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def run(command, **kwargs):
    return subprocess.run(command, text=True, capture_output=True, check=True, **kwargs).stdout


def make(source, directory, *args):
    return run(["make", "--no-print-directory", "-r", "-s", "-j1", "-f", "-", "audit", *args],
               cwd=directory, input=source)


def check_relocation(work):
    original = work / "external"
    (original / "bin").mkdir(parents=True)
    (original / "lib").mkdir()
    (original / "lib/libgcc_s.so.1").write_text("library fixture\n")
    (original / "lib/libgcc_s.so").symlink_to(original / "lib/libgcc_s.so.1")
    config = work / "build.config"
    config.write_text(f'''CONFIG_EXTERNAL_TOOLCHAIN=y
CONFIG_TARGET_NAME="aarch64-openwrt-linux-musl"
CONFIG_TOOLCHAIN_ROOT="{original}"
CONFIG_TOOLCHAIN_PREFIX="aarch64-openwrt-linux-musl-"
CONFIG_TOOLCHAIN_BIN_PATH="{original}/bin"
CONFIG_TOOLCHAIN_INC_PATH="./include"
CONFIG_TOOLCHAIN_LIB_PATH="./lib"
CONFIG_LIBGCC_ROOT_DIR="{original}"
CONFIG_LIBGCC_FILE_SPEC="./lib/libgcc_s.so.1"
CONFIG_LIBC_ROOT_DIR="{original}/lib"
CONFIG_LIBC="musl"
''')
    subdir = Path("staging_dir/toolchain-aarch64-openwrt-linux-musl")
    sdk = work / "sdk"
    exporter.export_toolchain(config, sdk, subdir)
    generated = (sdk / "Config-build.in").read_text()
    assert str(original) not in generated
    run([str(ROOT / "scripts/config/conf"), "--defconfig=/dev/null", "Config-build.in"], cwd=sdk)
    shutil.copy2(ROOT / "rules.mk", sdk / "rules.mk")
    (sdk / "include").mkdir()
    for name in ("debug.mk", "verbose.mk"):
        shutil.copy2(ROOT / "include" / name, sdk / "include" / name)
    sdk = sdk.rename(work / "sdk-moved")
    original.rename(work / "external-hidden")
    (sdk / "package/probe").mkdir(parents=True)
    probe = "include $(TOPDIR)/rules.mk\n"
    keys = ("TOOLCHAIN_ROOT_DIR", "TOOLCHAIN_BIN_DIRS", "LIBGCC_S_PATH", "CONFIG_LIBC_ROOT_DIR", "TARGET_DIR_NAME")
    probe += "".join(f"$(info {key}=$({key}))\n" for key in keys)
    output = make(probe + "audit:;@:\n", sdk / "package/probe", "SDK=1", f"TOPDIR={sdk}")
    values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    assert values["TOOLCHAIN_ROOT_DIR"] == str(sdk / subdir)
    assert values["TOOLCHAIN_BIN_DIRS"] == str(sdk / subdir / "bin")
    assert values["LIBGCC_S_PATH"] == str(sdk / subdir / "lib/libgcc_s.so.1")
    assert values["CONFIG_LIBC_ROOT_DIR"].strip('"') == str(sdk / subdir / "lib")
    assert values["TARGET_DIR_NAME"] == "target-aarch64-openwrt-linux-musl_musl"
    link = sdk / subdir / "lib/libgcc_s.so"
    assert link.read_text() == "library fixture\n" and not os.path.isabs(os.readlink(link))
    # Refuse an unexported sysroot rather than silently retaining a host path.
    config.write_text(config.read_text().replace(str(original), str(work / "external-hidden")))
    bad = config.read_text().replace('CONFIG_LIBC_ROOT_DIR="' + str(work / "external-hidden/lib") + '"',
                                     'CONFIG_LIBC_ROOT_DIR="/outside-toolchain"')
    try:
        exporter.relocate_config(bad, subdir)
    except ValueError:
        pass
    else:
        raise AssertionError("an external sysroot was silently accepted")
    print("OK: moved SDK roots, library lookup, absolute symlinks and target directory preserved")


def check_vendor_export(work):
    output = make("include Makefile\n$(info EXPORT=$(SDK_DIRS))\naudit:;@:\n",
                  ROOT / "target/sdk", f"TOPDIR={ROOT}",
                  "CONFIG_TARGET_BOARD=mediatek", "CONFIG_TARGET_SUBTARGET=filogic")
    paths = next(line[7:].split() for line in output.splitlines() if line.startswith("EXPORT="))
    sdk = work / "vendor-sdk"
    sdk.mkdir()
    for path in paths:
        if path.startswith("staging_dir/"):
            continue
        source, destination = ROOT / path, sdk / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination, symlinks=True)
        else:
            shutil.copy2(source, destination)
    shutil.copy2(ROOT / "rules.mk", sdk / "rules.mk")
    shutil.copytree(ROOT / "include", sdk / "include")
    shutil.copytree(ROOT / "scripts", sdk / "scripts", symlinks=True)
    variants = ("mt7981-ax3000", "mt7986-ax6000", "mt7986-ax4200", "mt7975-ipailna-high-power")
    for package, prefix in (("mt_wifi", "kmod-mt_wifi-"), ("conninfra", "kmod-conninfra-"),
                            ("warp", "kmod-warp-"), ("wifi-profile", "wifi-dats-")):
        for variant in variants:
            output = make("include Makefile\naudit:;@:\n", sdk / "package/mtk/drivers" / package,
                          f"TOPDIR={sdk}", "DUMP=1", "SDK=1", f"BUILD_VARIANT={variant}")
            assert "Package: " + prefix + variant + "\n" in output
    assert (sdk / "package/mtk/applications/mtwifi-cfg/Makefile").is_file()
    print("OK: detached SDK contains and parses all 16 vendor package variants and their reference configs")


def check_imagebuilder(work):
    source = (ROOT / "target/imagebuilder/Makefile").read_text()
    start = source.index("# Standalone exports")
    end = source.index("ifneq ($(CONFIG_SIGNATURE_CHECK)", start)
    recipe = source[start:end]
    core, feed = work / "core", work / "feed"
    core.mkdir()
    feed.mkdir()
    for suffix in ("ipk", "apk"):
        for name in ("libc", "kernel", "kmod-mt_wifi-mt7981-ax3000"):
            (core / f"{name}_1.{suffix}").touch()
        (feed / f"wifi-dats-mt7981-ax3000_1.{suffix}").touch()
        for standalone in (False, True):
            for buildbot in (False, True):
                dest = work / f"ib-{suffix}-{standalone}-{buildbot}"
                (dest / "packages").mkdir(parents=True)
                (dest / "kernel").mkdir()
                probe = (f"PACKAGE_SUFFIX:={suffix}\nPACKAGE_SUBDIRS:={core} {feed}\n"
                         f"PKG_BUILD_DIR:={dest}\nIB_LDIR:={dest}/kernel\n"
                         f"CONFIG_IB_STANDALONE:={'y' if standalone else ''}\n"
                         f"CONFIG_BUILDBOT:={'y' if buildbot else ''}\n"
                         f"FeedPackageDir={core}\nFIND:=find\nCP:=cp -fpR\naudit:\n" + recipe)
                make(probe, work)
                actual = {p.name.rsplit('_', 1)[0] for p in dest.rglob(f"*.{suffix}")}
                expected = {"libc", "kernel"}
                if standalone or not buildbot:
                    expected.add("kmod-mt_wifi-mt7981-ax3000")
                if standalone:
                    expected.add("wifi-dats-mt7981-ax3000")
                assert actual == expected, (standalone, buildbot, actual)
    print("OK: ImageBuilder package export in standalone/buildbot modes for ipk and apk")



def check_imagebuilder_profiles(work):
    metadata = run([str(ROOT / "scripts/target-metadata.pl"), "profile_mk",
                    str(ROOT / "tmp/.targetinfo"), "mediatek/filogic"])
    source = (ROOT / "target/imagebuilder/files/Makefile").read_text()
    start = source.index("BUILD_PACKAGES:=")
    end = source.index("\nPACKAGES:=", start)
    package_rules = source[start:end]
    profiles = dict(re.findall(r"^(DEVICE_.*)_PACKAGES:=(.*)$", metadata, re.M))
    mapped = 0
    for profile, packages in profiles.items():
        drivers = [p for p in packages.split() if p.startswith("kmod-mt_wifi-")]
        if not drivers:
            continue
        mapped += 1
        probe = (metadata + "\nDEFAULT_PACKAGES:=libc kmod-mt7915e wpad-openssl\n"
                 + f"USER_PROFILE:={profile}\n" + package_rules
                 + "\n$(info PACKAGES=$(BUILD_PACKAGES))\naudit:;@:\n")
        output = make(probe, work)
        selected = next(line[9:].split() for line in output.splitlines() if line.startswith("PACKAGES="))
        assert len(drivers) == 1 and drivers[0] in selected
        assert "kmod-mt7915e" not in selected and "wpad-openssl" not in selected
        assert "mtwifi-cfg" in selected
    assert mapped == 40, mapped
    assert "kmod-mt_wifi-mt7981-ax3000" in profiles["DEVICE_sl_3000-emmc"].split()
    print("OK: ImageBuilder metadata selects one mt_wifi variant for each of the 40 mapped devices")


def main():
    (ROOT / "tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sdk-check-", dir=ROOT / "tmp") as directory:
        work = Path(directory)
        check_relocation(work)
        check_vendor_export(work)
        check_imagebuilder(work)
        check_imagebuilder_profiles(work)


if __name__ == "__main__":
    main()
