# !/usr/bin/python
# coding=utf-8
"""Pure image-compositing engine for the map_compositor package.

No Qt, no UI imports. Status messages are written to ``self.logger``
(provided by :class:`ptk.LoggingMixin`); UI layers route output to a
text widget by calling ``self.logger.setup_logging_redirect(widget)``.
Progress-bar updates go through a thin ``progress_callback``.
"""
import os
import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image
import pythontk as ptk


Layers = List[Tuple[str, Image.Image]]
SortedImages = Dict[str, Layers]
ProgressCallback = Callable[[float], None]


class BatchResult(Enum):
    """Outcome of a full composite + retry-with-mask cycle."""

    SUCCESS = "success"            # All maps composited on the first pass.
    RETRIED = "retried"            # Some required a mask retry; all eventually saved.
    MASK_FAILURE = "mask_failure"  # Some failed and no mask was available to recover.


class NormalOutputMode(Enum):
    """How the engine handles DirectX/OpenGL normal-map output."""

    BOTH = "both"               # Save the provided format + auto-generate the complement (default).
    OPENGL_ONLY = "opengl_only" # Always output OpenGL; convert DirectX inputs.
    DIRECTX_ONLY = "directx_only"  # Always output DirectX; convert OpenGL inputs.
    NONE = "none"               # Pass inputs through as-is; do not synthesize a complement.


@dataclass(frozen=True)
class _MapInfo:
    """Per-map descriptor passed between engine helpers."""

    mode: str
    bit_depth: int
    ext: str
    width: int
    height: int


class MapCompositor(ptk.LoggingMixin):
    """Alpha-composite layered texture maps and auto-generate the
    complementary DirectX/OpenGL normal map when one is missing.

    Status messages are emitted via ``self.logger`` with HTML colouring.
    Attach to a Qt text widget with ``self.logger.setup_logging_redirect(widget)``.
    Progress-bar updates flow through ``progress_callback(percent)``.
    """

    def __init__(
        self,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        super().__init__()
        self._progress_cb: ProgressCallback = (
            progress_callback if progress_callback is not None else (lambda _p: None)
        )
        self.remove_normal_map: bool = True
        self.optimize_output: bool = False
        self.normal_output_mode: NormalOutputMode = NormalOutputMode.BOTH
        self.total_len: int = 0
        self.total_progress: int = 0
        self.masks: List[Image.Image] = []

    # Back-compat alias for the original camelCase attribute name.
    @property
    def removeNormalMap(self) -> bool:
        return self.remove_normal_map

    @removeNormalMap.setter
    def removeNormalMap(self, value: bool) -> None:
        self.remove_normal_map = value

    def reset(self) -> None:
        """Clear per-session state (masks, progress counters).

        Call at the start of each independent batch — :meth:`process_batch`
        does this for you.
        """
        self.masks = []
        self.total_progress = 0
        self.total_len = 0

    def process_batch(
        self,
        sorted_images: SortedImages,
        output_dir: str,
        name: str = "",
    ) -> BatchResult:
        """Drive a full composite → retry-with-mask → re-composite cycle."""
        self.reset()
        self.total_len = sum(len(layers) for layers in sorted_images.values())
        failed = self.composite_images(sorted_images, output_dir, name)
        if not failed:
            return BatchResult.SUCCESS
        self.logger.info(
            "Processing additional maps that require a mask ..", preset="italic"
        )
        retried = self.retry_failed(failed, name)
        if not retried:
            return BatchResult.MASK_FAILURE
        self.composite_images(retried, output_dir, name)
        return BatchResult.RETRIED

    def composite_images(
        self,
        sorted_images: SortedImages,
        output_dir: str,
        name: str = "",
    ) -> SortedImages:
        """Composite each map type and write the result.

        Returns the subset of map types whose layers had non-uniform
        backgrounds — those defer to :meth:`retry_failed`.
        """
        failed: SortedImages = {}
        for typ, layers in sorted_images.items():
            if not self._composite_type(typ, layers, sorted_images, output_dir, name):
                failed[typ] = layers
        return failed

    def retry_failed(self, failed: SortedImages, name: str) -> SortedImages:
        """Fill the masked area of each failed layer with the map-type's
        known default background, so a second composite pass can succeed.

        Masks were captured from a *different* map type's layers during the
        first pass and are aligned positionally — ``self.masks[n]`` is
        assumed to apply to the n-th layer of any map type. This relies on
        all map types having the same per-layer ordering.
        """
        out: SortedImages = {}
        for typ, layers in failed.items():
            for n, (filepath, image) in enumerate(layers):
                try:
                    mask = self.masks[n]
                except IndexError:
                    self.logger.error(
                        f"Composite failed: <b>{name}_{typ}: {filepath}</b>"
                    )
                    continue

                key = ptk.MapFactory.resolve_map_type(typ)
                bg = ptk.ImgUtils.map_backgrounds.get(key)
                if bg is None:
                    bg = ptk.get_background(image, "RGBA", average=True)
                    im = ptk.fill_masked_area(image, bg, mask)
                else:
                    im = ptk.fill_masked_area(image, bg, mask)
                    target_mode = ptk.ImgUtils.map_modes.get(key)
                    if target_mode is not None:
                        im = im.convert(target_mode)

                out.setdefault(typ, []).append((filepath, im))
        return out

    def _composite_type(
        self,
        typ: str,
        layers: Layers,
        sorted_images: SortedImages,
        output_dir: str,
        name: str,
    ) -> bool:
        """Composite one map type. Returns False to defer to mask retry."""
        filepath0, first_image = layers[0]
        second_image = layers[1][1] if len(layers) > 1 else first_image
        remaining = layers[1:]
        width, height = first_image.size
        mode = first_image.mode
        ext = ptk.format_path(filepath0, "ext")
        key = ptk.MapFactory.resolve_map_type(typ)
        bit_depth = ptk.ImgUtils.bit_depth[ptk.ImgUtils.map_modes[key]]

        # PIL mode "I" (32bit int) cannot be created directly; route via RGB.
        if mode == "I":
            first_image = first_image.convert("RGB")

        bg = ptk.get_background(first_image, "RGBA")
        bg2 = ptk.get_background(second_image, "RGBA")
        if not (bg and bg == bg2):
            return False  # non-uniform / mismatched bg → mask retry path

        if not self.masks and bg[3] == 0:
            self.logger.info(
                f"Attempting to create masks using source <b>{typ}</b> ..",
                preset="italic",
            )
            self.masks = ptk.create_mask([img for _, img in layers], bg)

        self.logger.info(
            f"{typ.rstrip('_')} {ptk.ImgUtils.map_modes[key]} {bit_depth}bit "
            f"{ext.upper()} {width}x{height}:",
            preset="header",
        )

        composited = self._alpha_composite_layers(
            first_image, remaining, bg, mode, filepath0
        )

        if bg[3] == 0:
            bg = ptk.ImgUtils.map_backgrounds.get(key, bg)

        result = Image.new("RGBA", composited.size, bg[:3] + (255,))
        result.paste(composited, mask=composited)
        result = ptk.ImgUtils.set_bit_depth(result, key)
        mode = result.mode
        bit_depth = ptk.ImgUtils.bit_depth.get(mode, bit_depth)
        out_path = os.path.join(output_dir, f"{name}_{typ}.{ext}")
        result.save(out_path)
        self._maybe_optimize(out_path, key)

        info = _MapInfo(mode=mode, bit_depth=bit_depth, ext=ext, width=width, height=height)
        self._maybe_convert_normal(result, typ, sorted_images, output_dir, name, info)
        return True

    def _maybe_optimize(self, out_path: str, map_type: str) -> None:
        """Run ImgUtils.optimize_texture on the just-saved file when enabled.

        Optimization rewrites the file in place with map-type-correct bit
        depth and (optionally) a tighter mode. No-op when disabled.
        """
        if not self.optimize_output:
            return
        try:
            ptk.ImgUtils.optimize_texture(
                out_path,
                map_type=map_type,
                optimize_bit_depth=True,
            )
        except Exception as e:
            # Optimization is best-effort — never abort the batch.
            self.logger.warning(
                f"optimize_texture failed for <b>{os.path.basename(out_path)}</b>: {e}"
            )

    def _alpha_composite_layers(
        self,
        first_image: Image.Image,
        remaining: Layers,
        bg: Tuple[int, int, int, int],
        mode: str,
        first_filepath: str,
    ) -> Image.Image:
        composited = first_image.convert("RGBA")
        self._tick(first_filepath)
        for filepath, im in remaining:
            self._tick(filepath)
            if mode == "I":
                im = im.convert("RGB")
            im = ptk.replace_color(im, from_color=bg, mode="RGBA")
            try:
                composited = Image.alpha_composite(composited, im.convert("RGBA"))
            except ValueError as e:
                self.logger.error(
                    f"alpha_composite failed for <b>{ptk.format_path(filepath, 'file')}</b>: {e}"
                )
        return composited

    def _tick(self, filepath: str) -> None:
        self.total_progress += 1
        self.logger.info(ptk.format_path(filepath, "file"))
        if self.total_len:
            self._progress_cb((self.total_progress / self.total_len) * 100)

    def _maybe_convert_normal(
        self,
        result: Image.Image,
        typ: str,
        sorted_images: SortedImages,
        output_dir: str,
        name: str,
        info: _MapInfo,
    ) -> None:
        """Generate / suppress the complementary normal map according to
        ``normal_output_mode``:

        * ``BOTH`` — emit the missing complement (existing behavior)
        * ``OPENGL_ONLY`` — emit only Normal_OpenGL; delete the DirectX
          variant if it was just written
        * ``DIRECTX_ONLY`` — symmetric to OPENGL_ONLY
        * ``NONE`` — never auto-convert
        """
        mode = self.normal_output_mode

        if mode is NormalOutputMode.NONE:
            return

        in_dx = typ in ptk.ImgUtils.map_types["Normal_DirectX"]
        in_gl = typ in ptk.ImgUtils.map_types["Normal_OpenGL"]
        if not (in_dx or in_gl):
            return  # not a normal map at all

        if mode is NormalOutputMode.BOTH:
            if ptk.MapFactory.contains_map_types(sorted_images, "Normal_OpenGL"):
                return
            if self._try_invert_normal(
                result, typ, "Normal_DirectX", "Normal_OpenGL", output_dir, name, info
            ):
                self._warn_if_normal_format_mismatch(result, declared="DirectX")
                return
            if not ptk.MapFactory.contains_map_types(sorted_images, "Normal_DirectX"):
                if self._try_invert_normal(
                    result, typ, "Normal_OpenGL", "Normal_DirectX", output_dir, name, info
                ):
                    self._warn_if_normal_format_mismatch(result, declared="OpenGL")
            return

        if mode is NormalOutputMode.OPENGL_ONLY:
            target_format, src_set, dst_set, declared = (
                "OpenGL", "Normal_DirectX", "Normal_OpenGL", "DirectX"
            )
        elif mode is NormalOutputMode.DIRECTX_ONLY:
            target_format, src_set, dst_set, declared = (
                "DirectX", "Normal_OpenGL", "Normal_DirectX", "OpenGL"
            )
        else:
            return  # unexpected mode — fail closed instead of misrouting

        # Source already matches target → no conversion, but delete any
        # opposite-format file we wrote earlier this same batch wouldn't
        # exist (each typ is processed once).
        if (target_format == "OpenGL" and in_gl) or (
            target_format == "DirectX" and in_dx
        ):
            return

        # Source is the opposite format → invert into target, then delete
        # the source file we just saved.
        if self._try_invert_normal(
            result, typ, src_set, dst_set, output_dir, name, info
        ):
            self._warn_if_normal_format_mismatch(result, declared=declared)
            try:
                os.remove(os.path.join(output_dir, f"{name}_{typ}.{info.ext}"))
            except OSError:
                pass

    def _warn_if_normal_format_mismatch(
        self, image: Image.Image, declared: str
    ) -> None:
        """Surface-integrability check: warn when the actual pixel content
        of a normal map disagrees with its declared format. Best-effort —
        swallows exceptions and numpy's zero-variance RuntimeWarning.
        """
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                detected = ptk.MapFactory.detect_normal_map_format(image)
        except Exception:
            return
        if detected and detected != declared:
            self.logger.warning(
                f"Normal map declared <b>{declared}</b> but pixel analysis "
                f"suggests <b>{detected}</b>. The auto-generated complement "
                f"may be incorrect — verify the source file's naming."
            )

    def _try_invert_normal(
        self,
        result: Image.Image,
        typ: str,
        src_set: str,
        dst_set: str,
        output_dir: str,
        name: str,
        info: _MapInfo,
    ) -> bool:
        try:
            index = ptk.ImgUtils.map_types[src_set].index(typ)
        except ValueError:
            return False
        new_type = ptk.ImgUtils.map_types[dst_set][index]
        inverted = ptk.invert_channels(result, "g")
        inverted.save(os.path.join(output_dir, f"{name}_{new_type}.{info.ext}"))
        self.logger.info(
            f"{new_type.rstrip('_')} {info.mode} {info.bit_depth}bit "
            f"{info.ext.upper()} {info.width}x{info.height}:",
            preset="header",
        )
        self.logger.info(f"Created using {name}_{typ}.{info.ext}")
        return True
