#
# Copyright (C) 2017 OpenWrt.org
#
# This is free software, licensed under the GNU General Public License v2.
# See /LICENSE for more information.
#

include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=conninfra
PKG_VERSION:=bbf588
include $(TOPDIR)/package/mtk/mtwifi.mk

PKG_RELEASE:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DIR:=$(call mtwifi_build_dir,conninfra)
PKG_MAINTAINER:=Kun-Ze Syue<kun-ze.syue@mediatek.com>

PKG_KCONFIG:= \
	MTK_CONNINFRA_APSOC \
	MTK_CONNINFRA_APSOC_MT7986 \
	MTK_CONNINFRA_APSOC_MT7981 \
	CONNINFRA_EMI_SUPPORT \
	FPGA_EARLY_PORTING \
	CONNINFRA_AUTO_UP

include $(INCLUDE_DIR)/package.mk

# Specify package information for this program.
define KernelPackage/conninfra/default
	CATEGORY:=MTK Properties
	TITLE:= Conninfra driver
	FILES:=$(PKG_BUILD_DIR)/conninfra.ko
	AUTOLOAD:=$(call AutoLoad,10,conninfra)
	SUBMENU:=Drivers
	DEPENDS:=@TARGET_mediatek_filogic
endef

# Transfer local kernel config to compile option
KCONFIG_FLAGS:=$(foreach c,$(PKG_KCONFIG),$(if $(call mtwifi_config,$(c)),CONFIG_$(c)=$(call mtwifi_config,$(c))))

# Transfer local kernel config to compile option
EXTRA_CFLAGS:= \
	$(patsubst CONFIG_%, -DCONFIG_%=1, $(patsubst %=m,%,$(filter %=m,$(KCONFIG_FLAGS)))) \
	$(patsubst CONFIG_%, -DCONFIG_%=1, $(patsubst %=y,%,$(filter %=y,$(KCONFIG_FLAGS)))) \
	$(patsubst CONFIG_%, -DCONFIG_%=0, $(patsubst %=n,%,$(filter %=n,$(KCONFIG_FLAGS)))) \

EXTRA_CFLAGS+=-DEEPROM_NAME=$(call mtwifi_config,first_card_EEPROM_name)

MAKE_OPTS:= \
	$(KERNEL_MAKE_FLAGS) $(MTWIFI_KERNEL_FLAGS) \
	SUBDIRS="$(PKG_BUILD_DIR)" \
	CROSS_COMPILE="$(TARGET_CROSS)" \
	ARCH="$(LINUX_KARCH)" \
	M="$(PKG_BUILD_DIR)" \
	EXTRA_CFLAGS="$(EXTRA_CFLAGS)" \
	$(KCONFIG_FLAGS)

define Build/Compile
	 $(MAKE) $(PKG_JOBS) -C "$(LINUX_DIR)" \
		$(MAKE_OPTS) \
		modules
endef

define ConninfraVariant
  define KernelPackage/conninfra-$(1)
    $$(KernelPackage/conninfra/default)
    TITLE+= ($(1))
    VARIANT:=$(1)
    PROVIDES:=kmod-conninfra
    CONFLICTS:=$(addprefix kmod-conninfra-,$(MTWIFI_PREVIOUS_VARIANTS))
  endef
  $$(eval $$(call KernelPackage,conninfra-$(1)))
  MTWIFI_PREVIOUS_VARIANTS += $(1)
endef
# One direction per pair avoids recursive Kconfig dependencies.
MTWIFI_PREVIOUS_VARIANTS :=
$(foreach variant,$(MTWIFI_VARIANTS),$(eval $(call ConninfraVariant,$(variant))))
