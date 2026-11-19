# Filogic 多设备 mt_wifi 构建

同一 Filogic 构建共用一个 Linux 内核配置，每个设备使用自己的 DTS 和根文件系统。
`mt_wifi`、`conninfra`、`warp` 和 `wifi-dats` 各自生成四个变体，芯片、固件、
WARP 和射频设置直接读取本目录的参考配置；全局 `.config` 中旧的 `CONFIG_MTK_*`
等选项不再控制这四个变体。参考文件中的最后一次赋值生效，包括 `is not set`。

| 变体 | 参考配置 | 默认设备数 |
| --- | --- | --- |
| mt7981-ax3000 | mt7981-ax3000.config | 25 |
| mt7986-ax6000 | mt7986-ax6000.config | 6 |
| mt7986-ax4200 | mt7986-ax4200-bpir3_mini.config | 1 |
| mt7975-ipailna-high-power | mt7975-ipailna-high-power.config | 8 |

普通 AX6000 和高功率参考配置中重叠的机型默认采用普通 AX6000；仅高功率参考文件
列出的锐捷机型采用高功率变体。`*_dae.config` 的无线选项与对应普通配置相同，
DAE/BPF 等应用及内核功能仍由全局 `.config` 选择。`*-nowifi.config` 是无无线的
替代方案，不是一套额外的射频参数。

只映射参考配置中的现有设备、可确认的旧名称/分区布局变体，以及指定的 SL3000。
没有匹配参考配置的设备维持原有驱动。旧配置中已不存在的设备名称不会凭空生成镜像；
MT7988 和额外 PCIe 无线卡不属于这四套 mt_wifi 变体的适配范围。

## 使用

保留全局配置中的 `CONFIG_TARGET_MULTI_PROFILE=y` 和
`CONFIG_TARGET_PER_DEVICE_ROOTFS=y`，选中所需设备。当前工作区仍保留原来的
`CONFIG_TARGET_ALL_PROFILES=y`，但只对下列 40 个设备切换 mt_wifi。
全设备构建时，各变体包及 mtwifi-cfg/LuCI 为 `m`，由设备默认依赖装进对应镜像，
不要把四套变体同时设为 `y`。设备默认包同时排除 mt7915e 及 wpad-openssl。

构建主机需要 GNU awk（Debian/Ubuntu 的 `gawk` 包）。本次校验环境中的
`staging_dir/host/bin/awk` 指向不存在的 `/usr/bin/gawk`，因此校验临时使用了
项目 `tmp/mtwifi-host-tools` 中解压的工具；实际编译前应补齐主机的 gawk。

```sh
make -j2 defconfig
python3 scripts/check-mtwifi-profiles.py
make -j2 V=s
```

不同变体在 `build_dir/.../linux-mediatek_filogic/mtwifi/<变体>/` 中准备和编译，
共享内核 ABI，但独立保存驱动源码、对象和 Module.symvers。源码包依赖确保
conninfra、warp 先于 mt_wifi 完成。更新参考配置会使对应准备戳失效。

WARP 在自动清理源码之前，通过 `Build/InstallDev` 将头文件及其子目录安装到
`staging_dir/<目标>/usr/include/mtwifi/<变体>/warp/`，mt_wifi 从这里读取头文件。
因此可以保留 `CONFIG_AUTOREMOVE=y`；各变体的头文件、安装戳和文件清单互相独立。
切换到此规则后，先重新编译 WARP，再编译 mt_wifi：

```sh
make -j2 package/mtk/drivers/warp/compile V=s
make -j2 package/mtk/drivers/mt_wifi/compile V=s
```

公共内核需要 WIRELESS_EXT、WEXT_CORE/PROC/SPY/PRIV、MediaTek Ethernet/WED
及 HNAT。本分支内核使用 NETSYS_V2，适用于这里的 MT7981/MT7986 组合。
完整 defconfig 中的调试、cgroup、BPF 等配置并非每个镜像各一份，仍需统一选择。
这次调整不导入参考文件的旧 target、工具链或其他应用设置。

SL3000 在挂载根文件系统之后、加载无线模块之前，从 eMMC 的 factory 分区读取
EEPROM 和预校准数据到 RAM，校验芯片标识和最小长度，再提供给 mt_wifi。
此过程不写 factory 分区；conninfra 改为普通启动阶段加载。真实硬件上的
无线、MAC 地址、功率和校准状态仍需编译刷机后确认。

回归检查包含四套配置及依赖、符号文件隔离、WARP 源码清理后的头文件引用、
固件和数据安装、SL3000 校准数据
读取的成功/失败场景，以及完整驱动补丁链。这些检查不等于完整编译或实机测试。
当前 feeds 另有 ndisc6/rdisc6 自引用、mihomo-alpha/meta 相互依赖及若干缺失包
的配置诊断，与此处的 Wi-Fi 变体无关。

## SDK 和 ImageBuilder

当前 `.config` 已启用 `CONFIG_SDK=y`、`CONFIG_IB=y` 和
`CONFIG_IB_STANDALONE=y`，继续使用原来的外部交叉工具链。完整构建成功后，
`bin/targets/mediatek/filogic/` 下会生成 SDK 和 ImageBuilder 压缩包。
SDK 携带四套驱动配方、源码、参考配置及本分支的 mtwifi-cfg，避免从远端 feed
取到尚未包含这些改动的旧配方。ImageBuilder 的 standalone 模式会收齐本次
已构建的本地软件包，包括 BUILDBOT 模式下的驱动和数据包。

SDK 会复制 `TOOLCHAIN_ROOT` 中的真实工具链，不使用构建主机上的绝对路径
包装器。工具链根目录及运行库根目录转换为相对于 SDK 的路径，解压到新目录后
由 `rules.mk` 解析；外部工具链对应的 target 目录名保持不变。此功能适用于
可迁移、sysroot 自包含的外部交叉工具链；本机原生工具链不能导出为独立 SDK。
工具链之外的头文件、库目录或符号链接不会被静默遗漏，导出会提示需先整理到
工具链根目录内。当前 GCC 13.3.0/musl 工具链已通过复制、换目录后的编译器、
sysroot、crt1.o 和 libgcc 路径查询检查，未执行代码编译。

在导出的 SDK 中安装所需 feeds/依赖后，可按正常包路径构建，例如：

```sh
./scripts/feeds update -a
./scripts/feeds install -a
make -j2 defconfig
make -j2 package/mtk/drivers/mt_wifi/compile V=s
```

在导出的 ImageBuilder 中按设备选择镜像：

```sh
make info
make -j2 image PROFILE=sl_3000-emmc
```

设备默认包会选择相应变体，不要通过 `PACKAGES` 将多套变体同时装入同一镜像。
ImageBuilder 只组合已编译的内核和软件包；SDK 编译内核模块也必须沿用该次
构建的内核配置及 ABI。应配套使用同一次构建生成的 SDK、ImageBuilder 和
软件包；修改公共内核配置后须重新导出，不能混用官方 SDK 或其他构建的 kmod。
完整压缩包生成、SDK 实际编译及 ImageBuilder 实际出镜像仍由后续构建验证。

无需编译的导出回归检查：

```sh
python3 scripts/check-sdk-exports.py
```

## 已映射设备

### mt7981-ax3000

- `abt_asr3000`
- `cetron_ct3003`
- `cetron_ct3003-ubootmod`
- `cmcc_a10`
- `cmcc_a10-stock`
- `cmcc_a10-ubootmod`
- `cmcc_rax3000m`
- `cmcc_rax3000m-emmc-mtk`
- `cmcc_rax3000m-nand-mtk`
- `cmcc_xr30-stock`
- `h3c_magic-nx30-pro`
- `h3c_magic-nx30-pro-nmbm`
- `huasifei_wh3000-emmc`
- `imou_lc-hx3001`
- `jcg_q30-pro`
- `konka_komi-a31`
- `livinet_zr-3020`
- `livinet_zr-3020-ubootmod`
- `qihoo_360t7`
- `sl_3000-emmc`
- `xiaomi_mi-router-ax3000t`
- `xiaomi_mi-router-ax3000t-mtkuboot`
- `xiaomi_mi-router-ax3000t-ubootmod`
- `xiaomi_mi-router-wr30u-stock`
- `xiaomi_mi-router-wr30u-ubootmod`

### mt7986-ax6000

- `glinet_gl-mt6000`
- `jdcloud_re-cp-03`
- `tplink_tl-xdr6086`
- `tplink_tl-xdr6088`
- `xiaomi_redmi-router-ax6000-stock`
- `xiaomi_redmi-router-ax6000-ubootmod`

### mt7986-ax4200

- `bananapi_bpi-r3-mini`

### mt7975-ipailna-high-power

- `ruijie_ew-6000gx-pro`
- `ruijie_ew-6000gx-pro-expand`
- `ruijie_ew-6000gx-pro-stock`
- `ruijie_ew-6000gx-pro-ubootmod`
- `ruijie_rg-x60-new`
- `ruijie_rg-x60-new-expand`
- `ruijie_rg-x60-new-stock`
- `ruijie_rg-x60-new-ubootmod`
