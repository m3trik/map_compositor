# !/usr/bin/python
# coding=utf-8
"""Application shell for the map_compositor UI.

The engine lives in :mod:`map_compositor.compositor` and the slot
bindings in :mod:`map_compositor.slots`; this module only assembles the
Switchboard-driven UI and provides the script entry point.
"""
from qtpy import QtCore, QtWidgets

# High-DPI scaling must be enabled before QApplication is constructed,
# otherwise the standalone launcher renders Header/Footer text at
# ~half the size they take inside Maya or tentacle (both hosts
# pre-configure DPI scaling on their own QApplication, which we then
# reuse). Only set the attributes when we will be the ones creating
# the QApplication — setting them after construction is a no-op and
# can emit a warning. The symbols are gone on Qt 6 (scaling is the
# default), so each lookup is guarded for forward compatibility.
if QtWidgets.QApplication.instance() is None:
    for _attr in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        flag = getattr(QtCore.Qt, _attr, None)
        if flag is not None:
            QtCore.QCoreApplication.setAttribute(flag, True)


class MapCompositorUI:
    def __new__(cls, *args, **kwargs):
        from uitk import Switchboard
        from map_compositor import __version__
        from map_compositor.slots import MapCompositorSlots

        sb = Switchboard(
            *args,
            ui_source="./map_compositor.ui",
            slot_source=MapCompositorSlots,
            **kwargs,
        )
        ui = sb.loaded_ui.map_compositor

        ui.set_attributes(WA_TranslucentBackground=True)
        # Use the uitk Header in place of the native OS frame so the
        # options menu (and other header controls) stay visible.
        ui.set_flags(FramelessWindowHint=True)
        ui.style.set(theme="dark", style_class="bgWithBorder")

        # Expose the menu button (and standard window controls) on the header.
        # The title ("MAP COMPOSITOR") is set declaratively in the .ui file —
        # edit it via Qt Designer rather than here. Only the version
        # (release-dependent) is wired in at runtime.
        ui.header.config_buttons("menu", "minimize", "fullscreen", "hide")
        ui.header.setVersion(__version__)

        ui.setWindowTitle(f"Map Compositor v{__version__}")
        ui.resize(ui.sizeHint())
        return ui


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ui = MapCompositorUI()
    ui.show(pos="screen", app_exec=True)
