# !/usr/bin/python
# coding=utf-8
import os
from PySide2 import QtWidgets
from PIL import Image
import pythontk as ptk
from uitk.switchboard import Switchboard


__package__ = "map-compositor"
__version__ = "0.5.8"


class MapCompositor:
    """ """

    removeNormalMap = True
    renameMixedAOMap = True
    total_len = 0
    total_progress = 0
    masks = []

    def composite_images(self, sorted_images, output_dir, name="", callback=print):
        """ """
        failed = {}
        for typ, images in sorted_images.items():
            filepath0 = images[0][0]
            first_image = images[0][1]
            second_image = images[1][1] if len(images) > 1 else first_image
            remaining_images = images[1:]
            width, height = first_image.size
            mode = first_image.mode
            ext = ptk.format_path(filepath0, "ext")

            key = ptk.get_image_type_from_filename(
                typ
            )  # get key from type value in map_types dict. ie. 'Base_Color' from '_BC' value.
            bit_depth = ptk.Img.bit_depth[ptk.Img.map_modes[key]]

            if (
                mode == "I"
            ):  # unable to create mode I 32bit. use rgb until a fix is found.
                first_image = first_image.convert("RGB")

            map_background = ptk.get_background(
                first_image, "RGBA"
            )  # get the image background in RGBA format.
            map_background2 = ptk.get_background(
                second_image, "RGBA"
            )  # get the image background in RGBA format.

            if not (
                map_background and map_background == map_background2
            ):  # if not a uniform background, or the background of map1 is not equal to map2:
                failed[typ] = images
                continue

            else:
                if not self.masks and map_background[3] == 0:
                    callback(
                        "<i><br>Attempting to create masks using source <b>{}</b> ..</i>".format(
                            typ
                        )
                    )
                    images = [
                        i[1] for i in images
                    ]  # get the images from the (filepath, image) list of tuples.
                    self.masks = ptk.create_mask(images, map_background)
                    # debug: [self.save_image(i, name=output_dir+'/'+str(n)+'_mask.png') for n, i in enumerate(self.masks)]

            length = len(remaining_images) if len(remaining_images) > 1 else 1

            callback(
                "<u><br><b>{} {} {}bit {}</b> {}x{}:</u>".format(
                    typ.rstrip("_"),
                    ptk.Img.map_modes[key],
                    bit_depth,
                    ext.upper(),
                    width,
                    height,
                )
            )
            self.total_progress += 1
            callback(
                ptk.format_path(filepath0, "file"),
                (1 / length) * 100,
                (self.total_progress / self.total_len) * 100,
            )  # first_image self.total_progress.

            composited_image = first_image.convert("RGBA")
            for n, (file, im) in enumerate(remaining_images, 1):
                self.total_progress += 1
                callback(
                    ptk.format_path(file, "file"),
                    (n / length) * 100,
                    (self.total_progress / self.total_len) * 100,
                )  # remaining_images self.total_progress.

                if mode == "I":
                    im = im.convert("RGB")
                im = ptk.replace_color(im, from_color=map_background, mode="RGBA")

                try:
                    composited_image = Image.alpha_composite(
                        composited_image, im.convert("RGBA")
                    )  # (background, foreground)
                except ValueError as error:
                    callback(
                        '<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> '
                        + str(error)
                        + "</hl>"
                    )

            try:
                if map_background[3] == 0:
                    map_background = ptk.Img.map_backgrounds[key]  # using this may not
                mode = ptk.Img.map_modes[key]
            except KeyError:
                pass

            result = Image.new(
                "RGBA", composited_image.size, map_background[:3] + (255,)
            )
            result.paste(composited_image, mask=composited_image)
            result = (
                result.convert(mode) if not mode == "I" else result.convert("RGB")
            )  # return im to it's original mode.

            result.save("{}/{}_{}.{}".format(output_dir, name, typ, ext))

            # convert normal maps:
            if not ptk.contains_map_types(sorted_images, "Normal_OpenGL"):
                try:  # convert DirectX to OpenGL
                    index = ptk.Img.map_types["Normal_DirectX"].index(typ)

                    new_type = ptk.Img.map_types["Normal_OpenGL"][index]
                    inverted_image = ptk.invert_channels(result, "g")
                    inverted_image.save(
                        "{}/{}_{}.{}".format(output_dir, name, new_type, ext)
                    )

                    callback(
                        "<br><u><b>{} {} {}bit {}</b> {}x{}:</u>".format(
                            new_type.rstrip("_"),
                            mode,
                            bit_depth,
                            ext.upper(),
                            width,
                            height,
                        )
                    )
                    callback("Created using {}_{}.{}".format(name, typ, ext))

                except ValueError:
                    if not ptk.contains_map_types(sorted_images, "Normal_DirectX"):
                        try:  # convert OpenGL to DirectX
                            index = ptk.Img.map_types["Normal_OpenGL"].index(typ)

                            new_type = ptk.Img.map_types["Normal_DirectX"][index]
                            inverted_image = ptk.invert_channels(result, "g")
                            inverted_image.save(
                                "{}/{}_{}.{}".format(output_dir, name, new_type, ext)
                            )

                            callback(
                                "<br><u><b>{} {} {}bit {}</b> {}x{}:</u>".format(
                                    new_type.rstrip("_"),
                                    mode,
                                    bit_depth,
                                    ext.upper(),
                                    width,
                                    height,
                                )
                            )
                            callback("Created using {}_{}.{}".format(name, typ, ext))

                        except ValueError:
                            continue
        return failed

    def retry_failed(self, failed, name, callback):
        """ """
        failed_images = {}
        for typ, images in failed.items():
            for n, (filepath, image) in enumerate(images):
                try:
                    mask = self.masks[n]
                except IndexError:
                    callback(
                        '<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Composite failed: <b>{}_{}: {}</b></hl>'.format(
                            name, typ, filepath
                        )
                    )
                    continue

                key = ptk.get_image_type_from_filename(typ)  #

                try:
                    background = ptk.Img.map_backgrounds[key]
                    im = self.fill_masked_area(image, background, mask)
                    mode = ptk.Img.map_modes[key]
                    im = im.convert(mode)

                except KeyError:
                    background = ptk.get_background(
                        image, "RGBA", average=True
                    )  # get the averaged background color.
                    im = self.fill_masked_area(image, background, mask)

                try:
                    failed_images[typ].append((filepath, im))
                except KeyError:
                    failed_images[typ] = [(filepath, im)]

        return failed_images


class MapCompositorSlots(MapCompositor):
    msg_intro = """<u>Required Substance Painter Export Settings:</u><br>Padding: <b>Dilation + transparent</b> or <b>Dilation + default backgound color</b>.
        <br><br><u>Works best with map filenames (case insensitive) ending in:</u>"""
    msg_error_maskCreation = '<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Unable to create masks from the source images.<br>To create a mask, at least one set of source maps need to a transparent or have a solid single color backround,<br>alternatively a set of mask maps can be added to the source folder. ex. &lt;map_name&gt;_mask.png</hl>'
    msg_operation_successful = (
        '<br><hl style="color:rgb(0, 255, 255);"><b>COMPLETED.</b></hl>'
    )

    for (
        k,
        v,
    ) in ptk.Img.map_types.items():  # format msg_intro using the map_types in imtools.
        line = "<br><b>{}:</b>  {}".format(k, v)
        msg_intro += line

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        """ """
        self.sb = self.switchboard()

        path = f"{self.sb.default_dir}/map_compositor.json"
        ptk.set_json_file(path)  # set json file name

        # load any saved info:
        try:
            prev_input_dirs = [
                i for i in ptk.get_json("prev_input_dirs") if not i == "/"
            ]
            self.sb.ui.cmb000.add(prev_input_dirs[-10:], "/")
        except TypeError:
            pass
        try:
            prev_output_dirs = [
                i for i in ptk.get_json("prev_output_dirs") if not i == "/"
            ]
            self.sb.ui.cmb001.add(prev_output_dirs[-10:], "/", ascending=True)
        except TypeError:
            pass
        try:
            prev_map_names = [i for i in ptk.get_json("prev_map_names") if not i == "/"]
            self.sb.ui.cmb002.add(prev_map_names[-10:], "/", ascending=True)
        except TypeError:
            pass

        self.orig_toolTip_txt000 = self.sb.ui.txt000.toolTip()
        self.orig_toolTip_txt001 = self.sb.ui.txt001.toolTip()
        #
        self.sb.ui.txt000.setText(ptk.get_json("input_dir"))
        self.sb.ui.txt001.setText(ptk.get_json("output_dir"))
        self.sb.ui.txt002.setText(ptk.get_json("map_name"))
        self.sb.ui.txt003.setText(self.msg_intro)

        # disable the browser open buttons if there isn't a directory.
        if not self.sb.ui.txt000.text():
            self.sb.ui.b003.setDisabled(True)
        if not self.sb.ui.txt001.text():
            self.sb.ui.b004.setDisabled(True)

    @property
    def input_dir(self) -> str:
        """Get the source directory from the user input text field.

        Returns:
                (str) directory path.
        """
        return self.sb.ui.txt000.text()

    @property
    def output_dir(self) -> str:
        """Get the export directory from the user input text field.

        Returns:
                (str) directory path.
        """
        return self.sb.ui.txt001.text()

    @property
    def map_name(self) -> str:
        """Get the map name from the user input text field.

        Returns:
                (str)
        """
        return self.sb.ui.txt002.text()

    def cmb000(self, index, widget):
        """ """
        if index > 0:
            text = widget.itemText(index)
            self.sb.ui.txt000.setText(text)
            widget.setCurrentIndex(0)

    def cmb001(self, index, widget):
        """ """
        if index > 0:
            text = widget.itemText(index)
            self.sb.ui.txt001.setText(text)
            widget.setCurrentIndex(0)

    def cmb002(self, index, widget):
        """ """
        if index > 0:
            text = widget.itemText(index)
            self.sb.ui.txt002.setText(text)
            widget.setCurrentIndex(0)

    def txt000(self, text, widget):
        """ """
        cmb = self.sb.ui.cmb000

        if text:
            curItems = cmb.items[1:]
            if text not in curItems and ptk.is_valid(text):  # add value to json dict.
                cmb.add(curItems + [text], "/", ascending=True)
                ptk.set_json("prev_input_dirs", cmb.items)

            self.sb.ui.b003.setDisabled(False)
            widget.setToolTip(text)
        else:
            self.sb.ui.b003.setDisabled(True)
            widget.setToolTip(self.orig_toolTip_txt000)

        ptk.set_json("input_dir", text)

    def txt001(self, text, widget):
        """ """
        cmb = self.sb.ui.cmb001

        if text:
            curItems = cmb.items[1:]
            if text not in curItems and ptk.is_valid(text):  # add value to json dict.
                cmb.add(curItems + [text], "/", ascending=True)
                ptk.set_json("prev_output_dirs", cmb.items)

            self.sb.ui.b004.setDisabled(False)
            widget.setToolTip(text)
        else:
            self.sb.ui.b004.setDisabled(True)
            widget.setToolTip(self.orig_toolTip_txt001)

        ptk.set_json("output_dir", text)

    def txt002(self, text, widget):
        """ """
        cmb = self.sb.ui.cmb002

        if text:
            curItems = cmb.items[1:]
            if text not in cmb.items:  # add value to json dict.
                cmb.add(curItems + [text], "/", ascending=True)
                ptk.set_json("prev_map_names", cmb.items)

        ptk.set_json("map_name", text)

    def b000(self):
        """ """
        input_dir = ptk.get_image_dir()
        if input_dir:
            self.sb.ui.txt000.setText(input_dir)
            self.txt000(
                input_dir
            )  # set the text AND enable the 'open' button if disabled.

    def b001(self):
        """ """
        output_dir = ptk.get_image_dir()
        if output_dir:
            self.sb.ui.txt001.setText(output_dir)
            self.txt001(
                output_dir
            )  # set the text AND enable the 'open' button if disabled.

    def b002(self):
        """ """
        self.sb.ui.txt003.clear()

        images = ptk.get_images(self.input_dir)
        self.process(
            images, self.input_dir, self.output_dir, self.map_name, self.callback
        )

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

    def process(self, images, input_dir, output_dir, map_name=None, callback=print):
        """ """
        self.callback("<i>Loading maps ..</i>", clear=True)

        if not (input_dir and output_dir):
            self.sb.ui.txt003.clear() if "Error:" not in self.sb.ui.txt003.toPlainText() else None
            self.sb.ui.txt003.append(
                '<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> You must specify a source and destination directory.</hl>'
            )
            return
        elif not ptk.is_valid(input_dir):
            self.sb.ui.txt003.clear() if "Error:" not in self.sb.ui.txt003.toPlainText() else None
            self.sb.ui.txt003.append(
                '<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Directory is invalid: <b>{}</b>.</hl>'.format(
                    input_dir
                )
            )
            return
        elif not ptk.is_valid(output_dir):
            self.sb.ui.txt003.clear() if "Error:" not in self.sb.ui.txt003.toPlainText() else None
            self.sb.ui.txt003.append(
                '<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Directory is invalid: <b>{}</b>.</hl>'.format(
                    output_dir
                )
            )
            return

        # save the current lineEdit values to the json file.
        self.txt000(self.sb.ui.txt000.text(), self.sb.ui.txt000)
        self.txt001(self.sb.ui.txt001.text(), self.sb.ui.txt001)
        self.txt002(self.sb.ui.txt002.text(), self.sb.ui.txt002)

        if not map_name:
            map_name = ptk.format_path(input_dir, "dir")

        sorted_images = ptk.sort_images_by_type(images)
        total_maps = (
            1
            if ptk.contains_map_types(sorted_images, "Normal_DirectX|Normal_OpenGL")
            else None
        )  # account for an additional converted normal map.

        if self.removeNormalMap:
            if ptk.contains_map_types(
                sorted_images, ["Normal_DirectX", "Normal_OpenGL"]
            ):
                normal = next(
                    (
                        i
                        for i in sorted_images.keys()  # delete the standard normal map from the output.
                        if ptk.get_image_type_from_filename(i) == "Normal"
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

        callback(
            "<i>Sorting <b>{}</b> images, into <b>{}</b> maps ..</i>".format(
                self.total_len, self.total_maps
            )
        )

        try:
            failed = self.composite_images(
                sorted_images, output_dir, map_name, callback
            )
            if failed:
                callback("<i><br>Processing additional maps that require a mask ..</i>")
                failed_images = self.retry_failed(failed, map_name, callback)
                if failed_images:
                    self.composite_images(failed_images, output_dir, map_name, callback)
                    callback(self.msg_operation_successful)
                else:
                    callback(self.msg_error_maskCreation)
            else:
                callback(self.msg_operation_successful)

        except Exception as error:
            callback(
                '<br><hl style="color:rgb(255, 100, 100);"><b>Error:</b> Operation encountered the following error:<br>{}</hl>'.format(
                    error
                )
            )
            raise error

    def callback(self, string, progress=None, total_progress=None, clear=False):
        """ """
        if clear:
            self.sb.ui.txt003.clear()
        self.sb.ui.txt003.append(string)

        if progress is not None:
            self.sb.ui.progressBar.setValue(progress)

        if total_progress is not None:
            self.sb.ui.progressBar_total.setValue(total_progress)

            QtWidgets.QApplication.processEvents()


class MapCompositorUI(Switchboard):
    """Constructs the main ui window for `MapCompositor` class."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui_location = "map_compositor.ui"
        self.slots_location = MapCompositorSlots

        self.ui.txt003.hide()
        self.ui.toggle_expand.clicked.connect(self.toggle_text_edit)

        self.ui.resize(self.ui.sizeHint())

    def toggle_text_edit(self):
        txt = self.ui.txt003
        if txt.isVisible():
            self._height_open = self.ui.height()
            txt.hide()
            self.ui.resize(self.ui.width(), self._height_closed)
        else:
            self._height_closed = self.ui.height()
            txt.show()
            self.ui.resize(
                self.ui.width(),
                self._height_open
                if hasattr(self, "_height_open")
                else self.ui.sizeHint().height() + 100,
            )


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    sb = MapCompositorUI()
    sb.ui.set_style(theme="dark")
    sb.ui.show(app_exec=True)

# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------


# Deprecated ---------------------
