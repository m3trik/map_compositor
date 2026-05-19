# !/usr/bin/python
# coding=utf-8
"""UI slot bindings for the map_compositor window.

Slots own the UI state and compose a :class:`MapCompositor` engine.
Engine status messages flow through ``self.engine.logger`` (a LoggingMixin
logger) which has a default ``StreamHandler`` for console output; we
attach uitk's :class:`TextEditLogHandler` alongside it so the UI message
panel auto-scrolls. Progress-bar updates use a thin callback.
"""

import logging
import os
from typing import Optional

import pythontk as ptk
from pythontk.core_utils.logging_mixin import LevelAwareFormatter
from qtpy.QtWidgets import QPushButton
from uitk.widgets.textEditLogHandler import TextEditLogHandler

from map_compositor.compositor import BatchResult, MapCompositor, NormalOutputMode

_DOCS_URL = "https://github.com/m3trik/map_compositor#readme"


def _build_intro() -> str:
    """One-time intro panel: minimal quickstart + link to full docs.

    The full filename-suffix table used to live here but dwarfed the
    actual instructions — readers had to scroll past ~30 rows of alias
    lists to find the basic export settings. Moved to the GitHub README;
    this panel now stays a single screen.
    """
    return (
        "<u>Quickstart</u><br>"
        "&nbsp;&nbsp;1. Set the <b>source</b> and <b>destination</b> directories.<br>"
        "&nbsp;&nbsp;2. (Optional) Set a <b>map name</b> prefix.<br>"
        "&nbsp;&nbsp;3. Click <b>Combine Maps</b>.<br><br>"
        "<u>Required Substance Painter Export Settings</u><br>"
        "&nbsp;&nbsp;Output Template: <b>Document channels</b><br>"
        "&nbsp;&nbsp;Padding: <b>Dilation + transparent</b> or "
        "<b>Dilation + default background color</b><br><br>"
        f'<span style="color:#888888">'
        f"Full filename-suffix table and detailed docs: "
        f'<a href="{_DOCS_URL}" style="color:#88AACC">{_DOCS_URL}</a>'
        "</span>"
    )


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

    # "None" disables the post-composite workflow pass; the remaining entries
    # are populated from pythontk's MapRegistry at runtime so the menu stays
    # in sync with the registry's WF.* workflow keys.
    _NO_TEMPLATE_LABEL = "None (composite only)"

    def __init__(self, switchboard) -> None:
        self.sb = switchboard
        self.ui = self.sb.loaded_ui.map_compositor

        self.engine = MapCompositor(progress_callback=self._on_progress)
        logger = self.engine.logger
        # Class-level logger — sweep stale widget handlers from prior sessions.
        for h in list(logger.handlers):
            if hasattr(h, "widget"):
                logger.removeHandler(h)
        # Attach directly; ``_set_text_handler`` would force this handler
        # process-wide. monospace=False keeps the intro's rich-text font;
        # log records still render monospace via TextEditLogHandler's <span>.
        logger.setLevel(logging.INFO)
        handler = TextEditLogHandler(self.ui.txt003, monospace=False)
        handler.setLevel(logging.INFO)
        handler.setFormatter(LevelAwareFormatter(logger=logger, strip_html=False))
        logger.addHandler(handler)

        self.default_toolTip_txt000 = self.ui.txt000.toolTip()
        self.default_toolTip_txt001 = self.ui.txt001.toolTip()

        self.ui.txt003.setText(self.msg_intro)
        self.ui.footer.setDefaultStatusText("Ready.")

        # The primary action ("Combine Maps") lives in the footer with a
        # styled background so it stands out from the status text. Connect
        # to the existing slot method directly — Switchboard won't auto-wire
        # it because the button isn't part of the .ui tree.
        self.combine_btn = QPushButton("Combine Maps")
        self.combine_btn.setToolTip("Start the compositing process.")
        self.combine_btn.clicked.connect(self.b002)
        self.ui.footer.add_widget(
            self.combine_btn, side="right", background=True, rounded=False
        )

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
    def _bind_recent_values(
        self,
        widget,
        settings_key: str,
        legacy_key: str,
        *,
        auto_record: bool = False,
    ):
        """Attach a RecentValuesOption and seed it from legacy QSettings."""
        from uitk.widgets.optionBox.options.recent_values import RecentValuesOption

        opt = RecentValuesOption(
            wrapped_widget=widget,
            settings_key=settings_key,
            max_recent=10,
            auto_record=auto_record,
        )
        widget.option_box.add_option(opt)
        if not opt.recent_values:
            for v in self.ui.settings.value(legacy_key, []):
                if v != "/":
                    opt.add_recent_value(v)
        return opt

    def _bind_dir_actions(self, widget, browse_title: str):
        """Attach Set (browse-directory) and Open (reveal-in-explorer) buttons.

        Returns the Open ActionOption so the caller can toggle its enabled
        state from the text-change handler.
        """
        from uitk.widgets.optionBox.options.action import ActionOption
        from uitk.widgets.optionBox.options.browse import BrowseOption

        open_opt = ActionOption(
            wrapped_widget=widget,
            callback=lambda: self._open_dir(widget.text()),
            icon="open_external",
            tooltip="Open this directory in the file explorer.",
        )
        widget.option_box.add_option(open_opt)

        browse_opt = BrowseOption(
            wrapped_widget=widget,
            mode="directory",
            title=browse_title,
            tooltip="Browse for a directory.",
        )
        widget.option_box.add_option(browse_opt)

        return open_opt

    @staticmethod
    def _open_dir(path: Optional[str]) -> None:
        try:
            os.startfile(path)
        except (FileNotFoundError, TypeError):
            pass

    def _on_dir_validated(self, ok: bool, text: str, open_opt):
        """Toggle the Open button in response to validated dir text."""
        open_opt.widget.setEnabled(bool(text and ok))

    def _on_progress(self, percent: float) -> None:
        """Engine→UI progress bar bridge (routes through the footer).

        Goes through ``Footer.update_progress`` rather than poking
        ``progress_bar.setValue`` directly — the bar is created with
        ``auto_hide=True`` and only becomes visible after the matching
        ``start_progress`` call in ``process()``. ``ProgressBar.update_progress``
        already pumps the event loop, so no extra ``processEvents`` here.
        """
        self.ui.footer.update_progress(int(percent))

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
            setToolTip=(
                "Choose which DirectX/OpenGL normal map variant(s) to output. "
                "Note: when an output template is selected, the template's "
                "required normal format may add a sibling file alongside the "
                "compositor's output."
            ),
            addItems=[label for label, _mode in self.NORMAL_MODE_CHOICES],
        )
        # Sync the combo to the engine's current value before connecting the
        # signal, so the initial setCurrentIndex doesn't re-trigger the slot.
        modes = [m for _label, m in self.NORMAL_MODE_CHOICES]
        widget.menu.cmb_normal_mode.setCurrentIndex(
            modes.index(self.engine.normal_output_mode)
        )
        widget.menu.cmb_normal_mode.currentIndexChanged.connect(
            self._on_normal_mode_changed
        )

        # Output template — names sourced from pythontk's MapRegistry so the
        # menu mirrors the registry's WF.* workflow keys. None = composite
        # only (no post-pass). When set, after compositing finishes the
        # engine runs MapFactory.prepare_maps with the matching workflow
        # preset to pack/rename files for the target engine.
        presets = ptk.MapRegistry().get_workflow_presets()
        self._template_choices = (self._NO_TEMPLATE_LABEL, *presets.keys())
        widget.menu.add(
            "QComboBox",
            setObjectName="cmb_output_template",
            setToolTip=(
                "Post-process composited output for a target workflow. "
                "Packs/renames the files for the chosen engine (e.g. Unity "
                "HDRP packs Metallic/AO/Smoothness into an MSAO MaskMap). "
                "Original composited files stay on disk alongside the "
                "workflow output."
            ),
            addItems=list(self._template_choices),
        )
        # Pre-select to match the engine field (default: None).
        current = self.engine.output_template or self._NO_TEMPLATE_LABEL
        try:
            widget.menu.cmb_output_template.setCurrentIndex(
                self._template_choices.index(current)
            )
        except ValueError:
            widget.menu.cmb_output_template.setCurrentIndex(0)
        widget.menu.cmb_output_template.currentIndexChanged.connect(
            self._on_output_template_changed
        )

    def _on_optimize_toggled(self, state) -> None:
        # Qt.Checked is 2 in PySide6, 2 in PySide2 — robust check via bool.
        self.engine.optimize_output = bool(state)

    def _on_normal_mode_changed(self, index: int) -> None:
        _label, mode = self.NORMAL_MODE_CHOICES[index]
        self.engine.normal_output_mode = mode

    def _on_output_template_changed(self, index: int) -> None:
        choice = self._template_choices[index]
        self.engine.output_template = (
            None if choice == self._NO_TEMPLATE_LABEL else choice
        )

    def txt000_init(self, widget):
        """Init Source Directory"""
        self._recent_input_dirs = self._bind_recent_values(
            widget,
            "map_compositor_input_dirs",
            "prev_input_dirs",
            auto_record=True,
        )
        self._open_input_dir = self._bind_dir_actions(
            widget, browse_title="Select a directory containing image files."
        )
        widget.set_validator(
            "dir",
            invalid_tooltip="Invalid directory",
            empty_tooltip=self.default_toolTip_txt000,
        )
        widget.validated.connect(
            lambda ok, text: self._on_dir_validated(ok, text, self._open_input_dir)
        )

    def txt001_init(self, widget):
        """Init Destination Directory"""
        self._recent_output_dirs = self._bind_recent_values(
            widget,
            "map_compositor_output_dirs",
            "prev_output_dirs",
            auto_record=True,
        )
        self._open_output_dir = self._bind_dir_actions(
            widget, browse_title="Select an output directory."
        )
        widget.set_validator(
            "dir",
            invalid_tooltip="Invalid directory",
            empty_tooltip=self.default_toolTip_txt001,
        )
        widget.validated.connect(
            lambda ok, text: self._on_dir_validated(ok, text, self._open_output_dir)
        )

    def txt002_init(self, widget):
        """Init Map Name"""
        self._recent_map_names = self._bind_recent_values(
            widget,
            "map_compositor_map_names",
            "prev_map_names",
            auto_record=True,
        )

    # --- button handlers ---
    def b002(self):
        """Combine Maps"""
        self.ui.txt003.clear()
        self.ui.footer.setStatusText("Loading maps …")
        self.engine.logger.info("Loading maps ..", preset="italic")
        self.sb.app.processEvents()
        images = ptk.get_images(self.input_dir)
        self.process(images, self.input_dir, self.output_dir, self.map_name)

    # --- orchestration ---
    def process(self, images, input_dir, output_dir, map_name=None):
        """Validate dirs, prepare sorted-image groups, and drive the engine."""
        if not (input_dir and output_dir):
            self.engine.logger.error(
                "You must specify a source and destination directory."
            )
            self.ui.footer.setStatusText("Source and destination directories required.")
            return

        invalid_dir = next(
            (d for d in (input_dir, output_dir) if not ptk.is_valid(d, "dir")),
            None,
        )
        if invalid_dir:
            self.engine.logger.error(f"Directory is invalid: <b>{invalid_dir}</b>.")
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
                (
                    k
                    for k in sorted_images
                    if ptk.MapFactory.resolve_map_type(k) == "Normal"
                ),
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
        # Reveal the footer's slim progress bar; engine ticks flow into
        # update_progress via _on_progress. finish_progress() in every
        # exit path auto-hides the bar after a short delay.
        self.ui.footer.start_progress(
            total=100,
            text=f"Compositing {total_maps} maps from {total_layers} layers …",
        )

        try:
            result = self.engine.process_batch(sorted_images, output_dir, map_name)
        except Exception as e:
            self.engine.logger.error(
                f"Operation encountered the following error:<br>{e}"
            )
            self.ui.footer.finish_progress(f"Failed: {e}")
            raise

        if result is BatchResult.MASK_FAILURE:
            self.engine.logger.error(
                "Unable to create masks from the source images.<br>"
                "To create a mask, at least one set of source maps need a "
                "transparent or single color background,<br>alternatively a "
                "set of mask maps can be added to the source folder. "
                "ex. &lt;map_name&gt;_mask.png"
            )
            self.ui.footer.finish_progress(
                "Mask creation failed — see message panel for details."
            )
        else:
            self.engine.logger.success("COMPLETED.")
            self.ui.footer.finish_progress(f"Wrote {total_maps} map(s) to {output_dir}")
