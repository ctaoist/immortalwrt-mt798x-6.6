# SPDX-License-Identifier: GPL-2.0-only
# Each driver/data variant reads its wireless options from the reference
# defconfig. Never import its target, toolchain or unrelated package settings.
MTWIFI_VARIANTS := mt7981-ax3000 mt7986-ax6000 mt7986-ax4200 mt7975-ipailna-high-power
MTWIFI_DEFCONFIG_mt7986-ax4200 := mt7986-ax4200-bpir3_mini
MTWIFI_PROFILE := $(if $(BUILD_VARIANT),$(BUILD_VARIANT),mt7981-ax3000)
MTWIFI_CONFIG_FILE := $(TOPDIR)/defconfig/$(or $(MTWIFI_DEFCONFIG_$(MTWIFI_PROFILE)),$(MTWIFI_PROFILE)).config

ifeq ($(wildcard $(MTWIFI_CONFIG_FILE)),)
  $(error Missing mt_wifi reference configuration: $(MTWIFI_CONFIG_FILE))
endif

MTWIFI_CONFIG_VALUES := $(shell sed -n -E \
	-e 's/^\# (CONFIG_(MTK_|CONNINFRA_|FPGA_EARLY_PORTING|WARP_|WED_|first_card|second_card|third_card)[A-Za-z0-9_]*) is not set$$/\1=n/p' \
	-e '/^CONFIG_(MTK_|CONNINFRA_|FPGA_EARLY_PORTING|WARP_|WED_|first_card|second_card|third_card)[A-Za-z0-9_]*=/p' \
	$(MTWIFI_CONFIG_FILE))
$(foreach option,$(MTWIFI_CONFIG_VALUES),$(eval MTWIFI_$(option)))

# Disabled and unspecified options must not become -DCONFIG_FOO=0: vendor
# sources also use #ifdef CONFIG_FOO, for which even a zero would enable it.
mtwifi_config = $(filter-out n,$(MTWIFI_CONFIG_$(1)))
mtwifi_build_dir = $(KERNEL_BUILD_DIR)/mtwifi/$(MTWIFI_PROFILE)/$(1)

# WARP sources may be removed by CONFIG_AUTOREMOVE before mt_wifi builds.
# Keep its exported headers in staging, isolated like each variant's symbols.
MTWIFI_WARP_HEADERS_DIR = usr/include/mtwifi/$(MTWIFI_PROFILE)/warp

PKG_FILE_DEPENDS += $(TOPDIR)/package/mtk/mtwifi.mk $(MTWIFI_CONFIG_FILE)

# Keep symbol CRCs beside each variant; the global directory must never
# contain multiple definitions of the same vendor driver symbols.
PKG_SYMVERS_DIR = $(KERNEL_BUILD_DIR)/mtwifi/$(MTWIFI_PROFILE)/symvers
MTWIFI_EXTRA_SYMBOLS = $(filter-out $(addprefix $(KERNEL_BUILD_DIR)/symvers/,mt_wifi.symvers warp.symvers conninfra.symvers),$(wildcard $(KERNEL_BUILD_DIR)/symvers/*.symvers)) $(wildcard $(PKG_SYMVERS_DIR)/*.symvers)
MTWIFI_KERNEL_FLAGS = KBUILD_EXTRA_SYMBOLS="$(MTWIFI_EXTRA_SYMBOLS)"
