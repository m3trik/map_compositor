# !/usr/bin/python
# coding=utf-8
"""Application shell for the map_compositor UI.

The engine lives in :mod:`map_compositor.compositor` and the slot
bindings in :mod:`map_compositor.slots`; this module only assembles the
Switchboard-driven UI and provides the script entry point.
"""


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
        ui.style.set(theme="dark", style_class="bgWithBorder")

        # Expose the menu button (and standard window controls) on the header.
        ui.header.config_buttons("menu", "minimize", "hide")

        ui.setWindowTitle(f"Map Compositor v{__version__}")
        ui.resize(ui.sizeHint())
        return ui


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ui = MapCompositorUI()
    ui.show(pos="screen", app_exec=True)
