# !/usr/bin/python
# coding=utf-8
"""UI slot bindings for the map_compositor window.

Slots own the UI state and compose a :class:`MapCompositor` engine.
Engine status messages flow through ``self.engine.logger`` (a LoggingMixin
logger) which we route to the message panel via ``setup_logging_redirect``;
progress-bar updates use a thin callback.
"""
import os
from typing import Optional

import pythontk as ptk
from pythontk.core_utils.logging_mixin import DefaultTextLogHandler

from map_compositor.compositor import BatchResult, MapCompositor, NormalOutputMode


def _build_intro() -> str:
    """One-time intro string listing the supported map-type suffixes."""
    intro = (
        "<u>Required Substance Painter Export Settings:</u><br>"
        "Output Template: <b>Document channels</b>.<br>"
        "Padding: <b>Dilation + transparent</b> or "
        "<b>Dilation + default background color</b>."
        "<br><br><u>Works best with map filenames (case insensitive) ending in:</u>"
    )
    for k, v in ptk.ImgUtils.map_types.items():
        intro += f"<br><b>{k}:</b>  {v}"
    return intro


class MapCompositorSlots:
    """UI slot handler. Composes a :class:`MapCompositor` via ``self.engine``."""

    msg_intro = _build_intro()

    # (display label, NormalOutputMode) — order shown in the header combo.
    NORMAL_MODE_CHOICES = (
        ("Both (auto-convert)", NormalOutputMode.BOTH),
        ("OpenGL only", NormalOutputMode.OPENGL_ONLY),
        ("DirectX only", NormalOutputMode.DIRECTX_ONLY),
        ("No conversion", NormalOutputMode.NONE),
    )

    def __init__(self, switchboard) -> None:
        self.sb = switchboard
        self.ui = self.sb.loaded_ui.map_compositor

        self.engine = MapCompositor(progress_callback=self._on_progress)
        # The engine's logger is a class-level property shared across instances.
        # If the UI was opened before, its DefaultTextLogHandler is still bound
        # to that (now-destroyed) widget — sweep stale handlers before attaching.
        for h in list(self.engine.logger.handlers):
            if isinstance(h, DefaultTextLogHandler):
                self.engine.logger.removeHandler(h)
        self.engine.logger.setup_logging_redirect(self.ui.txt003)

        self.default_toolTip_txt000 = self.ui.txt000.toolTip()
        self.default_toolTip_txt001 = self.ui.txt001.toolTip()

        self.ui.txt003.setText(self.msg_intro)
        self.ui.footer.setDefaultStatusText("Ready.")

        if not self.ui.txt000.text():
            self.ui.b003.setDisabled(True)
        if not self.ui.txt001.text():
            self.ui.b004.setDisabled(True)

    # --- engine pass-through (back-compat with previous public API) ---
    @property
    def removeNormalMap(self) -> bool:
        return self.engine.remove_normal_map

    @removeNormalMap.setter
    def removeNormalMap(self, value: bool) -> None:
        self.engine.remove_normal_map = value

    # --- input/output text-field properties ---
    @property
    def input_dir(self) -> str:
        return self.ui.txt000.text()

    @property
    def output_dir(self) -> str:
        return self.ui.txt001.text()

    @property
    def map_name(self) -> str:
        return self.ui.txt002.text()

    # --- shared helpers ---
    def _bind_recent_values(self, widget, settings_key: str, legacy_key: str):
        """Attach a RecentValuesOption and seed it from legacy QSettings."""
        from uitk.widgets.optionBox.options.recent_values import RecentValuesOption

        opt = RecentValuesOption(
            wrapped_widget=widget,
            settings_key=settings_key,
            max_recent=10,
        )
        widget.option_box.add_option(opt)
        if not opt.recent_values:
            for v in self.ui.settings.value(legacy_key, []):
                if v != "/":
                    opt.add_recent_value(v)
        return opt

    @staticmethod
    def _open_dir(path: Optional[str]) -> None:
        try:
            os.startfile(path)
        except (FileNotFoundError, TypeError):
            pass

    def _apply_dir_text(self, text, widget, open_btn, default_tooltip, recent):
        if text:
            if ptk.is_valid(text, "dir") and recent is not None:
                recent.record(text)
            open_btn.setDisabled(False)
            widget.setToolTip(text)
        else:
            open_btn.setDisabled(True)
            widget.setToolTip(default_tooltip)

    def _on_progress(self, percent: float) -> None:
        """Engine→UI progress bar bridge (routes through the footer)."""
        self.ui.footer.progress_bar.setValue(int(percent))
        self.sb.app.processEvents()

    # --- widget init handlers ---
    def header_init(self, widget):
        """Populate the header menu with global options."""
        widget.menu.add(
            "QCheckBox",
            setText="Optimize output",
            setObjectName="chk_optimize",
            setChecked=self.engine.optimize_output,
            setToolTip=(
                "Run ImgUtils.optimize_texture on each saved map "
                "(enforces map-type bit depth and mode)."
            ),
            stateChanged=self._on_optimize_toggled,
        )
        widget.menu.add(
            "QComboBox",
            setObjectName="cmb_normal_mode",
            setToolTip="Choose which DirectX/OpenGL normal map variant(s) to output.",
            addItems=[label for label, _mode in self.NORMAL_MODE_CHOICES],
        )
        # Sync the combo to the engine's current value before connecting the
        # signal, so the initial setCurrentIndex doesn't re-trigger the slot.
        modes = [m for _label, m in self.NORMAL_MODE_CHOICES]
        widget.menu.cmb_normal_mode.setCurrentIndex(modes.index(self.engine.normal_output_mode))
        widget.menu.cmb_normal_mode.currentIndexChanged.connect(
            self._on_normal_mode_changed
        )

    def _on_optimize_toggled(self, state) -> None:
        # Qt.Checked is 2 in PySide6, 2 in PySide2 — robust check via bool.
        self.engine.optimize_output = bool(state)

    def _on_normal_mode_changed(self, index: int) -> None:
        _label, mode = self.NORMAL_MODE_CHOICES[index]
        self.engine.normal_output_mode = mode

    def txt000_init(self, widget):
        """Init Source Directory"""
        self._recent_input_dirs = self._bind_recent_values(
            widget, "map_compositor_input_dirs", "prev_input_dirs"
        )

    def txt001_init(self, widget):
        """Init Destination Directory"""
        self._recent_output_dirs = self._bind_recent_values(
            widget, "map_compositor_output_dirs", "prev_output_dirs"
        )

    def txt002_init(self, widget):
        """Init Map Name"""
        self._recent_map_names = self._bind_recent_values(
            widget, "map_compositor_map_names", "prev_map_names"
        )

    # --- text-change handlers ---
    def txt000(self, text, widget):
        """Source Directory"""
        self._apply_dir_text(
            text, widget, self.ui.b003, self.default_toolTip_txt000,
            getattr(self, "_recent_input_dirs", None),
        )

    def txt001(self, text, widget):
        """Destination Directory"""
        self._apply_dir_text(
            text, widget, self.ui.b004, self.default_toolTip_txt001,
            getattr(self, "_recent_output_dirs", None),
        )

    def txt002(self, text, widget):
        """Map Name"""
        if text and hasattr(self, "_recent_map_names"):
            self._recent_map_names.record(text)

    # --- button handlers ---
    def b000(self):
        """Select Input Directory"""
        d = self.sb.dir_dialog(title="Select a directory containing image files.")
        if d:
            self.ui.txt000.setText(d)
            self.txt000(d, self.ui.txt000)

    def b001(self):
        """Select Output Directory"""
        d = self.sb.dir_dialog(title="Select an output directory.")
        if d:
            self.ui.txt001.setText(d)
            self.txt001(d, self.ui.txt001)

    def b002(self):
        """Combine Maps"""
        self.ui.txt003.clear()
        self.ui.footer.setStatusText("Loading maps …")
        self.engine.logger.info("Loading maps ..", preset="italic")
        self.sb.app.processEvents()
        images = ptk.get_images(self.input_dir)
        self.process(images, self.input_dir, self.output_dir, self.map_name)

    def b003(self):
        """Open Input Directory"""
        self._open_dir(self.input_dir)

    def b004(self):
        """Open Output Directory"""
        self._open_dir(self.output_dir)

    # --- orchestration ---
    def process(self, images, input_dir, output_dir, map_name=None):
        """Validate dirs, prepare sorted-image groups, and drive the engine."""
        if not (input_dir and output_dir):
            self.engine.logger.error(
                "You must specify a source and destination directory."
            )
            self.ui.footer.setStatusText(
                "Source and destination directories required."
            )
            return

        invalid_dir = next(
            (d for d in (input_dir, output_dir) if not ptk.is_valid(d, "dir")),
            None,
        )
        if invalid_dir:
            self.engine.logger.error(
                f"Directory is invalid: <b>{invalid_dir}</b>."
            )
            self.ui.footer.setStatusText(f"Invalid directory: {invalid_dir}")
            return

        if not map_name:
            map_name = ptk.format_path(input_dir, "dir")

        sorted_images = ptk.MapFactory.sort_images_by_type(images)
        has_normal_pair = ptk.MapFactory.contains_map_types(
            sorted_images, ["Normal_DirectX", "Normal_OpenGL"]
        )
        # +1 for the auto-generated complementary normal map.
        total_maps_extra = 1 if has_normal_pair else 0

        if self.engine.remove_normal_map and has_normal_pair:
            normal = next(
                (k for k in sorted_images if ptk.MapFactory.resolve_map_type(k) == "Normal"),
                None,
            )
            if normal:
                del sorted_images[normal]

        # When the user has both DX *and* GL sources but only wants one
        # format, drop the redundant one — otherwise the engine would
        # process each independently and the iteration order would decide
        # which content survives (the second-processed format overwrites
        # the first via the auto-invert path).
        mode = self.engine.normal_output_mode
        if (
            mode is NormalOutputMode.OPENGL_ONLY
            and "Normal_OpenGL" in sorted_images
            and "Normal_DirectX" in sorted_images
        ):
            del sorted_images["Normal_DirectX"]
        elif (
            mode is NormalOutputMode.DIRECTX_ONLY
            and "Normal_OpenGL" in sorted_images
            and "Normal_DirectX" in sorted_images
        ):
            del sorted_images["Normal_OpenGL"]

        # Drop maps superseded by present packed maps (e.g. ORM → drops
        # Metallic/Roughness/AO; MSAO → drops more). In-place mutation.
        # NB: pythontk's sort_images_by_type already aliases legacy variants
        # like Mixed_AO into Ambient_Occlusion, so no manual rename is needed.
        ptk.MapFactory.filter_redundant_maps(sorted_images)

        total_layers = sum(len(v) for v in sorted_images.values())
        total_maps = len(sorted_images) + total_maps_extra

        self.engine.logger.info(
            f"Sorting <b>{total_layers}</b> images, into "
            f"<b>{total_maps}</b> maps ..",
            preset="italic",
        )
        self.ui.footer.setStatusText(
            f"Compositing {total_maps} maps from {total_layers} layers …"
        )

        try:
            result = self.engine.process_batch(sorted_images, output_dir, map_name)
        except Exception as e:
            self.engine.logger.error(
                f"Operation encountered the following error:<br>{e}"
            )
            self.ui.footer.setStatusText(f"Failed: {e}")
            raise

        if result is BatchResult.MASK_FAILURE:
            self.engine.logger.error(
                "Unable to create masks from the source images.<br>"
                "To create a mask, at least one set of source maps need a "
                "transparent or single color background,<br>alternatively a "
                "set of mask maps can be added to the source folder. "
                "ex. &lt;map_name&gt;_mask.png"
            )
            self.ui.footer.setStatusText(
                "Mask creation failed — see message panel for details."
            )
        else:
            self.engine.logger.success("COMPLETED.")
            self.ui.footer.setStatusText(
                f"Wrote {total_maps} map(s) to {output_dir}"
            )
