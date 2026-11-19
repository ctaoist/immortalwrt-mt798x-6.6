#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Copy a self-contained external cross toolchain and relocate SDK defaults."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess


ROOT_OPTION = re.compile(r"CONFIG_(?:TOOLCHAIN_ROOT|(?:LIB\w+|LDD|LDCONFIG)_ROOT_DIR)$")
PATH_OPTIONS = {"CONFIG_TOOLCHAIN_" + kind + "_PATH" for kind in ("BIN", "INC", "LIB")}


def relocate_config(config, subdir):
    values = dict(re.findall(r'^([A-Z0-9_]+)="(.*)"$', config, re.M))
    root = Path(values["CONFIG_TOOLCHAIN_ROOT"]).resolve()
    if not root.is_dir() or root == Path("/"):
        raise ValueError(f"invalid external toolchain root: {root}")
    if re.search(r"^CONFIG_NATIVE_TOOLCHAIN=y$", config, re.M):
        raise ValueError("a native host toolchain cannot be exported as a cross SDK")

    def relative(value):
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        try:
            return path.resolve().relative_to(root)
        except ValueError:
            raise ValueError(f"toolchain path is outside TOOLCHAIN_ROOT: {value}") from None

    replacements = {}
    for key, value in values.items():
        if ROOT_OPTION.fullmatch(key):
            replacements[key] = str(subdir / relative(value))
        elif key in PATH_OPTIONS:
            replacements[key] = " ".join("./" + str(relative(p)) for p in value.split())
        elif key == "CONFIG_TOOLCHAIN_PREFIX" and "/" in value:
            # TARGET_CROSS is looked up through TOOLCHAIN_BIN_PATH in the SDK.
            prefix = relative(value)
            bins = [relative(p) for p in values["CONFIG_TOOLCHAIN_BIN_PATH"].split()]
            if prefix.parent not in bins:
                raise ValueError("toolchain prefix is outside TOOLCHAIN_BIN_PATH")
            replacements[key] = prefix.name

    def replace(match):
        key = match[1]
        return f'{key}="{replacements[key]}"' if key in replacements else match[0]

    return root, re.sub(r'^([A-Z0-9_]+)=".*"$', replace, config, flags=re.M)


def export_toolchain(config_file, sdk_dir, subdir):
    if subdir.is_absolute() or ".." in subdir.parts:
        raise ValueError("the destination must be relative to the SDK")
    root, config = relocate_config(config_file.read_text(), subdir)
    # Validate links before copying. Absolute links within the root are made
    # relative; links to files outside the exported tree cannot be shipped.
    links = []
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            path = Path(base) / name
            if path.is_symlink():
                try:
                    target = path.resolve().relative_to(root)
                except ValueError:
                    raise ValueError(f"toolchain symlink leaves TOOLCHAIN_ROOT: {path}") from None
                if os.path.isabs(os.readlink(path)):
                    links.append((path.relative_to(root), target))

    destination = sdk_dir / subdir
    shutil.copytree(root, destination, symlinks=True)
    for path, target in links:
        link = destination / path
        link.unlink()
        link.symlink_to(os.path.relpath(destination / target, link.parent))

    converted = subprocess.run(
        ["perl", str(Path(__file__).with_name("convert-config.pl"))],
        input=config, text=True, capture_output=True, check=True,
    )
    (sdk_dir / "Config-build.in").write_text(converted.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("sdk_dir", type=Path)
    parser.add_argument("toolchain_subdir", type=Path)
    args = parser.parse_args()
    try:
        export_toolchain(args.config, args.sdk_dir, args.toolchain_subdir)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"SDK toolchain export failed: {error}\n")


if __name__ == "__main__":
    main()
