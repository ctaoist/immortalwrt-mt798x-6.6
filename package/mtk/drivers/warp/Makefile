# All rights reserved.
#
# This is free software, licensed under the GNU General Public License v2.
# See /LICENSE for more information.

include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=warp

PKG_VERSION:=20221209-3e6ae1

MT7981_NEW_WOFW_DIR := mt7981-fw-20231228
MT7986_NEW_WOFW_DIR := mt7986-fw-20230808

include $(TOPDIR)/package/mtk/mtwifi.mk

PKG_RELEASE:=2
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DIR:=$(call mtwifi_build_dir,warp)
PKG_KCONFIG:= \
	WARP_VERSION \
	WARP_ATC_SUPPORT \
	WARP_DBG_SUPPORT \
	WARP_WDMA_RECYCLE_SUPPORT \
	WED_HW_RRO_SUPPORT \
	MTK_MEMORY_SHRINK \
	WARP_CHIPSET \
	WARP_WO_EMBEDDED_LOAD \
	WARP_MEMORY_LEAK_DBG

include $(INCLUDE_DIR)/package.mk

TAR_CMD=$(HOST_TAR) -C $(1)/.. $(TAR_OPTIONS)

define KernelPackage/warp/default
  CATEGORY:=MTK Properties
  TITLE:=MTK warp driver
  DEPENDS:=@TARGET_mediatek_filogic +kmod-mediatek_hnat
  FILES:=$(PKG_BUILD_DIR)/mtk_warp.ko
  AUTOLOAD:=$(call AutoLoad,60,mtk_warp)
  SUBMENU:=Drivers
endef

define Build/Compile
	$(MAKE) $(PKG_JOBS) -C "$(LINUX_DIR)" \
		$(KERNEL_MAKE_FLAGS) $(MTWIFI_KERNEL_FLAGS) \
		M="$(PKG_BUILD_DIR)" \
		$(foreach c,$(PKG_KCONFIG),$(if $(call mtwifi_config,$(c)),CONFIG_$(c)=$(call mtwifi_config,$(c)))) \
		modules
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/$(MTWIFI_WARP_HEADERS_DIR)
	cd $(PKG_BUILD_DIR) && $(FIND) . -type f -name '*.h' \
		-exec $(CP) --parents {} $(1)/$(MTWIFI_WARP_HEADERS_DIR)/ \;
endef

define KernelPackage/warp/install
	$(INSTALL_DIR) $(1)/lib/firmware
	if [ "$$(MTWIFI_CONFIG_WARP_CHIPSET)" = "mt7981" ]; then \
		if [ "$$(MTWIFI_CONFIG_WARP_NEW_FW)" = "y" ]; then \
			cp ./files/$$(MT7981_NEW_WOFW_DIR)/7981*WOCPU*_RAM_CODE_release.bin $(1)/lib/firmware/; \
		else \
			cp $(PKG_BUILD_DIR)/bin/7981*WOCPU*_RAM_CODE_release.bin $(1)/lib/firmware/; \
		fi; \
	elif [ "$$(MTWIFI_CONFIG_WARP_CHIPSET)" = "mt7986" ]; then \
		if [ "$$(MTWIFI_CONFIG_WARP_NEW_FW)" = "y" ]; then \
			cp ./files/$$(MT7986_NEW_WOFW_DIR)/7986*WOCPU*_RAM_CODE_release.bin $(1)/lib/firmware/; \
		else \
			cp $(PKG_BUILD_DIR)/bin/7986*WOCPU*_RAM_CODE_release.bin $(1)/lib/firmware/; \
		fi; \
	fi
endef

define WarpVariant
  define KernelPackage/warp-$(1)
    $$(KernelPackage/warp/default)
    TITLE+= ($(1))
    VARIANT:=$(1)
    PROVIDES:=kmod-warp
    CONFLICTS:=$(addprefix kmod-warp-,$(MTWIFI_PREVIOUS_VARIANTS))
  endef
  define KernelPackage/warp-$(1)/install
    $$(call KernelPackage/warp/install,$$(1))
  endef
  $$(eval $$(call KernelPackage,warp-$(1)))
  MTWIFI_PREVIOUS_VARIANTS += $(1)
endef
# One direction per pair avoids recursive Kconfig dependencies.
MTWIFI_PREVIOUS_VARIANTS :=
$(foreach variant,$(MTWIFI_VARIANTS),$(eval $(call WarpVariant,$(variant))))
