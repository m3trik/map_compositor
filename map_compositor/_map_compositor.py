# !/usr/bin/python
# coding=utf-8
import os
from typing import Dict, List, Tuple
from PySide2.QtCore import QObject, Signal
from PIL import Image
import pythontk as ptk
from uitk.switchboard import Switchboard


class MapCompositorSignals(QObject):
    message = Signal(str)
    progress = Signal(float)
    total_progress = Signal(float)


class MapCompositor:
    """Handles the composition of texture maps, including operations like compositing,
    color replacement, and conversion between different normal map formats.
    """

    def __init__(self):
        # Initialize signals for UI communication.
        self.signals = MapCompositorSignals()
        self.removeNormalMap: bool = True
        self.renameMixedAOMap: bool = True
        self.total_len: int = 0
        self.total_progress: int = 0
        self.masks: List[Image.Image] = []

    def composite_images(
        self,
        sorted_images: Dict[str, List[Tuple[str, Image.Image]]],
        output_dir: str,
        name: str = "",
    ) -> Dict[str, List[Tuple[str, Image.Image]]]:
        """ """
        failed: Dict[str, List[Tuple[str, Image.Image]]] = {}
        for typ, images in sorted_images.items():
            filepath0 = images[0][0]
            first_image = images[0][1]
            second_image = images[1][1] if len(images) > 1 else first_image
            remaining_images = images[1:]
            width, height = first_image.size
            mode = first_image.mode
            ext = ptk.format_path(filepath0, "ext")

            # Get key from type value in map_types dict. ie. 'Base_Color' from '_BC' value.
            key = ptk.get_map_type_from_filename(typ)
            bit_depth = ptk.ImgUtils.bit_depth[ptk.ImgUtils.map_modes[key]]

            # Unable to create mode I 32bit. use rgb until a fix is found.
            if mode == "I":
                first_image = first_image.convert("RGB")

            # Get the image background in RGBA format.
            map_background = ptk.get_background(first_image, "RGBA")
            # Get the image background in RGBA format.
            map_background2 = ptk.get_background(second_image, "RGBA")

            # if not a uniform background, or the background of map1 is not equal to map2:
            if not (map_background and map_background == map_background2):
                failed[typ] = images
                continue

            else:
                if not self.masks and map_background[3] == 0:
                    self.signals.message.emit(
                        f"<i><br>Attempting to create masks using source <b>{typ}</b> ..</i>"
                    )
                    # Get the images from the (filepath, image) list of tuples.
                    images = [i[1] for i in images]
                    self.masks = ptk.create_mask(images, map_background)
                    # debug: [self.save_image(i, name=output_dir+'/'+str(n)+'_mask.png') for n, i in enumerate(self.masks)]

            self.signals.message.emit(
                f"<u><br><b>{typ.rstrip('_')} {ptk.ImgUtils.map_modes[key]} {bit_depth}bit {ext.upper()}</b> {width}x{height}:</u>"
            )

            self.total_progress += 1
            self.signals.message.emit(ptk.format_path(filepath0, "file"))
            self.signals.progress.emit((self.total_progress / self.total_len) * 100)

            composited_image = first_image.convert("RGBA")
            for n, (file, im) in enumerate(remaining_images, 1):
                self.total_progress += 1
                self.signals.message.emit(ptk.format_path(file, "file"))
                self.signals.progress.emit((self.total_progress / self.total_len) * 100)

                if mode == "I":
                    im = im.convert("RGB")
                im = ptk.replace_color(im, from_color=map_background, mode="RGBA")

                try:  # (background, foreground)
                    composited_image = Image.alpha_composite(
                        composited_image, im.convert("RGBA")
                    )
                except ValueError as e:
                    self.signals.message.emit(
                        '<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> '
                        + str(e)
                        + "</hl>"
                    )

            try:
                if map_background[3] == 0:
                    map_background = ptk.ImgUtils.map_backgrounds[key]
                mode = ptk.ImgUtils.map_modes[key]
            except KeyError:
                pass

            result = Image.new(
                "RGBA", composited_image.size, map_background[:3] + (255,)
            )
            result.paste(composited_image, mask=composited_image)
            # Return image to it's original mode.
            result = result.convert(mode) if not mode == "I" else result.convert("RGB")

            result.save(f"{output_dir}/{name}_{typ}.{ext}")

            # Convert normal maps:
            if not ptk.contains_map_types(sorted_images, "Normal_OpenGL"):
                try:  # Convert DirectX to OpenGL
                    index = ptk.ImgUtils.map_types["Normal_DirectX"].index(typ)

                    new_type = ptk.ImgUtils.map_types["Normal_OpenGL"][index]
                    inverted_image = ptk.invert_channels(result, "g")
                    inverted_image.save(f"{output_dir}/{name}_{new_type}.{ext}")

                    self.signals.message.emit(
                        f"<br><u><b>{new_type.rstrip('_')} {mode} {bit_depth}bit {ext.upper()}</b> {width}x{height}:</u>"
                    )
                    self.signals.message.emit(f"Created using {name}_{typ}.{ext}")

                except ValueError:
                    if not ptk.contains_map_types(sorted_images, "Normal_DirectX"):
                        try:  # Convert OpenGL to DirectX
                            index = ptk.ImgUtils.map_types["Normal_OpenGL"].index(typ)

                            new_type = ptk.ImgUtils.map_types["Normal_DirectX"][index]
                            inverted_image = ptk.invert_channels(result, "g")
                            inverted_image.save(f"{output_dir}/{name}_{new_type}.{ext}")

                            self.signals.message.emit(
                                f"<br><u><b>{new_type.rstrip('_')} {mode} {bit_depth}bit {ext.upper()}</b> {width}x{height}:</u>"
                            )
                            self.signals.message.emit(
                                f"Created using {name}_{typ}.{ext}"
                            )

                        except ValueError:
                            continue
        return failed

    def retry_failed(self, failed, name):
        """ """
        failed_images = {}
        for typ, images in failed.items():
            for n, (filepath, image) in enumerate(images):
                try:
                    mask = self.masks[n]
                except IndexError:
                    self.signals.message.emit(
                        f'<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Composite failed: <b>{name}_{typ}: {filepath}</b></hl>'
                    )
                    continue

                key = ptk.get_map_type_from_filename(typ)  #

                try:
                    background = ptk.ImgUtils.map_backgrounds[key]
                    im = ptk.fill_masked_area(image, background, mask)
                    mode = ptk.ImgUtils.map_modes[key]
                    im = im.convert(mode)

                except KeyError:
                    # Get the averaged background color.
                    background = ptk.get_background(image, "RGBA", average=True)
                    im = ptk.fill_masked_area(image, background, mask)

                try:
                    failed_images[typ].append((filepath, im))
                except KeyError:
                    failed_images[typ] = [(filepath, im)]

        return failed_images


class MapCompositorSlots(MapCompositor):
    msg_intro = """<u>Required Substance Painter Export Settings:</u><br>Output Template: <b>Document channels</b>.</u><br>Padding: <b>Dilation + transparent</b> or <b>Dilation + default backgound color</b>.
        <br><br><u>Works best with map filenames (case insensitive) ending in:</u>"""
    msg_error_maskCreation = '<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Unable to create masks from the source images.<br>To create a mask, at least one set of source maps need a transparent or single color backround,<br>alternatively a set of mask maps can be added to the source folder. ex. &lt;map_name&gt;_mask.png</hl>'
    msg_operation_successful = (
        '<br><hl style="color:rgb(0, 255, 255);"><b>COMPLETED.</b></hl>'
    )

    # Format msg_intro using the map_types in imtools.
    for k, v in ptk.ImgUtils.map_types.items():
        line = f"<br><b>{k}:</b>  {v}"
        msg_intro += line

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        """ """
        self.sb = self.switchboard()
        self.ui = self.sb.map_compositor

        # load any saved info:
        prev_input_dirs = self.ui.settings.value("prev_input_dirs", [])
        prev_input_dirs = [i for i in prev_input_dirs if not i == "/"]
        self.ui.cmb000.add(prev_input_dirs[-10:], header="/")

        prev_output_dirs = self.ui.settings.value("prev_output_dirs", [])
        prev_output_dirs = [i for i in prev_output_dirs if not i == "/"]
        self.ui.cmb001.add(prev_output_dirs[-10:], header="/", ascending=True)

        prev_map_names = self.ui.settings.value("prev_map_names", [])
        prev_map_names = [i for i in prev_map_names if not i == "/"]
        self.ui.cmb002.add(prev_map_names[-10:], header="/", ascending=True)

        self.default_toolTip_txt000 = self.ui.txt000.toolTip()
        self.default_toolTip_txt001 = self.ui.txt001.toolTip()

        self.ui.txt003.setText(self.msg_intro)

        # disable the browser open buttons if there isn't a directory.
        if not self.ui.txt000.text():
            self.ui.b003.setDisabled(True)
        if not self.ui.txt001.text():
            self.ui.b004.setDisabled(True)

        self.signals.message.connect(self.set_message)
        self.signals.progress.connect(self.set_progress)

    @property
    def input_dir(self) -> str:
        """Get the source directory from the user input text field.

        Returns:
            (str) directory path.
        """
        return self.ui.txt000.text()

    @property
    def output_dir(self) -> str:
        """Get the export directory from the user input text field.

        Returns:
            (str) directory path.
        """
        return self.ui.txt001.text()

    @property
    def map_name(self) -> str:
        """Get the map name from the user input text field.

        Returns:
            (str)
        """
        return self.ui.txt002.text()

    def cmb000(self, index, widget):
        """Previous Source Directories"""
        text = widget.itemText(index)
        self.ui.txt000.setText(text)

    def cmb001(self, index, widget):
        """Previous Destination Directories"""
        text = widget.itemText(index)
        self.ui.txt001.setText(text)

    def cmb002(self, index, widget):
        """Previous Map Names"""
        text = widget.itemText(index)
        self.ui.txt002.setText(text)

    def txt000(self, text, widget):
        """Source Directory"""
        cmb = self.ui.cmb000

        if text:
            curItems = cmb.items[1:]
            if text not in curItems and ptk.is_valid(text):  # Add value to settings.
                cmb.add(curItems + [text], header="/", ascending=True)
                self.ui.settings.setValue("prev_input_dirs", cmb.items)

            self.ui.b003.setDisabled(False)
            widget.setToolTip(text)
        else:
            self.ui.b003.setDisabled(True)
            widget.setToolTip(self.orig_toolTip_txt000)

    def txt001(self, text, widget):
        """Destination Directory"""
        cmb = self.ui.cmb001

        if text:
            curItems = cmb.items[1:]
            if text not in curItems and ptk.is_valid(text):  # Add value to settings.
                cmb.add(curItems + [text], header="/", ascending=True)
                self.ui.settings.setValue("prev_output_dirs", cmb.items)

            self.ui.b004.setDisabled(False)
            widget.setToolTip(text)
        else:
            self.ui.b004.setDisabled(True)
            widget.setToolTip(self.orig_toolTip_txt001)

    def txt002(self, text, widget):
        """Map Name"""
        cmb = self.ui.cmb002

        if text:
            curItems = cmb.items[1:]
            if text not in cmb.items:  # add value to settings.
                cmb.add(curItems + [text], header="/", ascending=True)
                self.ui.settings.setValue("prev_map_names", cmb.items)

    def b000(self):
        """Select Input Directory"""
        input_dir = self.sb.dir_dialog(
            title="Select a directory containing image files."
        )
        if input_dir:
            self.ui.txt000.setText(input_dir)
            # Set the text AND enable the 'open' button if disabled.
            self.txt000(input_dir, self.ui.txt000)

    def b001(self):
        """Select Output Directory"""
        output_dir = self.sb.dir_dialog(title="Select an output directory.")
        if output_dir:
            self.ui.txt001.setText(output_dir)
            # Set the text AND enable the 'open' button if disabled.
            self.txt001(output_dir, self.ui.txt001)

    def b002(self):
        """Combine Maps"""
        self.ui.txt003.clear()
        self.signals.message.emit("<i>Loading maps ..</i>")
        self.sb.app.processEvents()

        images = ptk.get_images(self.input_dir)
        self.process(images, self.input_dir, self.output_dir, self.map_name)

    def b003(self):
        """ """
        try:
            os.startfile(self.input_dir)
        except (FileNotFoundError, TypeError):
            pass

    def b004(self):
        """ """
        try:
            os.startfile(self.output_dir)
        except (FileNotFoundError, TypeError):
            pass

    def process(self, images, input_dir, output_dir, map_name=None):
        """ """

        if not (input_dir and output_dir):
            self.ui.txt003.append(
                '<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> You must specify a source and destination directory.</hl>'
            )
            return
        elif not ptk.is_valid(input_dir) or not ptk.is_valid(output_dir):
            invalid_dir = input_dir if not ptk.is_valid(input_dir) else output_dir
            self.ui.txt003.append(
                f'<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Directory is invalid: <b>{invalid_dir}</b>.</hl>'
            )
            return

        if not map_name:
            map_name = ptk.format_path(input_dir, "dir")

        sorted_images = ptk.sort_images_by_type(images)
        total_maps = (
            1
            if ptk.contains_map_types(
                sorted_images, ["Normal_DirectX", "Normal_OpenGL"]
            )
            else None
        )  # Account for an additional converted normal map.

        if self.removeNormalMap:
            if ptk.contains_map_types(
                sorted_images, ["Normal_DirectX", "Normal_OpenGL"]
            ):
                normal = next(
                    (
                        i
                        for i in sorted_images.keys()  # Delete the standard normal map from the output.
                        if ptk.get_map_type_from_filename(i) == "Normal"
                    ),
                    False,
                )
                if normal:
                    del sorted_images[normal]

        if self.renameMixedAOMap:
            if "Mixed_AO" in sorted_images and "AmbientOcclusion" not in sorted_images:
                sorted_images["AmbientOcclusion"] = sorted_images.pop("Mixed_AO")

        self.total_maps = len(sorted_images) + total_maps
        self.total_len = sum([len(i) for i in sorted_images.values()])

        self.signals.message.emit(
            f"<i>Sorting <b>{self.total_len}</b> images, into <b>{self.total_maps}</b> maps ..</i>"
        )

        try:
            failed = self.composite_images(sorted_images, output_dir, map_name)
            if failed:
                self.signals.message.emit(
                    "<i><br>Processing additional maps that require a mask ..</i>"
                )
                failed_images = self.retry_failed(failed, map_name)
                if failed_images:
                    self.composite_images(failed_images, output_dir, map_name)
                    self.signals.message.emit(self.msg_operation_successful)
                else:
                    self.signals.message.emit(self.msg_error_maskCreation)
            else:
                self.signals.message.emit(self.msg_operation_successful)

        except Exception as e:
            self.signals.message.emit(
                f'<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Operation encountered the following error:<br>{e}</hl>'
            )
            raise e

    def set_message(self, message):
        self.ui.txt003.append(message)

    def set_progress(self, progress):
        self.ui.progress_bar.setValue(progress)
        self.sb.app.processEvents()


class MapCompositorUI:
    def __new__(cls, *args, **kwargs):
        sb = Switchboard(
            *args,
            ui_location="./map_compositor.ui",
            **kwargs,
        )
        ui = sb.map_compositor

        # ui.settings.clear()
        sb.set_slot_class(ui, MapCompositorSlots)  # Set explicitly for pyinstaller.
        ui.set_attributes(WA_TranslucentBackground=True)
        # ui.set_flags(Tool=True, FramelessWindowHint=True, WindowStaysOnTopHint=True)
        ui.set_style(theme="dark", style_class="bgWithBorder")
        from map_compositor import __version__

        ui.setWindowTitle(f"Map Compositor v{__version__}")
        ui.resize(ui.sizeHint())

        return ui


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ui = MapCompositorUI()
    ui.show(pos="screen", app_exec=True)

# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------
