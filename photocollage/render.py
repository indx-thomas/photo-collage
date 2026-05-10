# Copyright (C) 2014 Adrien Vergé
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import random
from threading import Thread
import time

import PIL.Image
import PIL.ImageDraw
import PIL.ImageFile

from photocollage.collage import Photo


QUALITY_SKEL = 0
QUALITY_FAST = 1
QUALITY_BEST = 2

CROP_COVER = "cover"
CROP_CONTAIN = "contain"
CROP_SMART = "smart"
CROP_MODES = (CROP_COVER, CROP_CONTAIN, CROP_SMART)


# Try to continue even if the input file is corrupted.
# See issue at https://github.com/adrienverge/PhotoCollage/issues/65
PIL.ImageFile.LOAD_TRUNCATED_IMAGES = True


class PIL_SUPPORTED_EXTS:
    """File extensions supported by PIL

    Compiled from:
    - http://pillow.readthedocs.org/en/2.3.0/handbook/image-file-formats.html
    - https://github.com/python-imaging/Pillow/blob/master/PIL/*ImagePlugin.py

    """
    RW = {
        "BMP": ("bmp",),
        # "EPS": ("ps", "eps",),   # doesn't seem to work
        "GIF": ("gif",),
        "IM": ("im",),
        "JPEG": ("jfif", "jpe", "jpg", "jpeg",),
        "MSP": ("msp",),
        "PCX": ("pcx",),
        "PNG": ("png",),
        "PPM": ("pbm", "pgm", "ppm",),
        "TGA": ("tga",),
        "TIFF": ("tif", "tiff",),
        "WebP": ("webp",),
        "XBM": ("xbm",),
    }
    RO = {
        "CUR": ("cur",),
        "DCX": ("dcx",),
        "FLI": ("fli", "flc",),
        "FPX": ("fpx",),
        "GBR": ("gbr",),
        "ICO": ("ico",),
        "IPTC/NAA": ("iim",),
        "PCD": ("pcd",),
        "PSD": ("psd",),
        "SGI": ("bw", "rgb", "rgba", "sgi",),
        "XPM": ("xpm",),
    }
    WO = {
        # "PALM": ("palm",),      # doesn't seem to work
        # "PDF": ("pdf",),        # doesn't seem to work
    }


def high_quality_resample():
    try:
        return PIL.Image.Resampling.LANCZOS
    except AttributeError:
        return PIL.Image.LANCZOS if hasattr(PIL.Image, "LANCZOS") else PIL.Image.ANTIALIAS


def fast_resample():
    try:
        return PIL.Image.Resampling.NEAREST
    except AttributeError:
        return PIL.Image.NEAREST


def has_alpha(img):
    return (
        img.mode in ("RGBA", "LA") or
        (img.mode == "P" and "transparency" in img.info)
    )


def composite_on_background(img, background_color):
    """Return an RGB image with alpha correctly composited on a background."""
    if not has_alpha(img):
        return img.convert("RGB")

    rgba = img.convert("RGBA")
    background = PIL.Image.new("RGBA", rgba.size, background_color + (255,))
    return PIL.Image.alpha_composite(background, rgba).convert("RGB")


def cover_crop_fraction(photo_w, photo_h, cell_w, cell_h):
    """Return the largest source-axis crop fraction needed to cover a cell."""
    scale = max(float(cell_w) / float(photo_w), float(cell_h) / float(photo_h))
    scaled_w = float(photo_w) * scale
    scaled_h = float(photo_h) * scale
    crop_w = max(0.0, scaled_w - float(cell_w)) / scaled_w
    crop_h = max(0.0, scaled_h - float(cell_h)) / scaled_h
    return max(crop_w, crop_h)


def cell_crop_fraction(cell):
    return cover_crop_fraction(cell.photo.w, cell.photo.h, cell.w, cell.h)


def random_color():
    r = random.randrange(256)
    g = random.randrange(256)
    b = random.randrange(256)
    if r + g + b > 0.7 * 3 * 256:
        r -= 50
        g -= 50
        b -= 50
    return (r, g, b)


class BadPhoto(Exception):
    def __init__(self, photoname):
        self.photoname = photoname


def build_photolist(filelist):
    ret = []

    for name in filelist:
        try:
            img = PIL.Image.open(name)
        except OSError:
            raise BadPhoto(name)
        w, h = img.size

        orientation = 0
        try:
            exif = img._getexif()
            if 274 in exif:  # orientation tag
                orientation = exif[274]
                if orientation == 6 or orientation == 8:
                    w, h = h, w
        except Exception:
            pass

        ret.append(Photo(name, w, h, orientation))
    return ret


cache = {}


class RenderingTask(Thread):
    """Execution thread to do the actual poster rendering

    Image computation is a heavy task, that can take several seconds. During
    this, the program might be unresponding. To avoid this, rendering is done
    is a separated thread.

    """
    def __init__(self, page, border_width=0.01, border_color=(0, 0, 0),
                 background_color=(255, 255, 255), quality=QUALITY_FAST,
                 crop_mode=CROP_COVER, max_crop=0.10, output_file=None,
                 on_update=None, on_complete=None, on_fail=None):
        super().__init__()

        self.page = page
        self.border_width = border_width
        self.border_color = border_color
        self.background_color = background_color
        self.quality = quality
        self.crop_mode = crop_mode
        self.max_crop = max_crop

        self.output_file = output_file

        self.on_update = on_update
        self.on_complete = on_complete
        self.on_fail = on_fail

        self.canceled = False

    def abort(self):
        self.canceled = True

    def draw_skeleton(self, canvas):
        for col in self.page.cols:
            for c in col.cells:
                if c.is_extension():
                    continue
                color = random_color()
                x, y, w, h = c.content_coords()
                xy = (x, y)
                xY = (x, y + h - 1)
                Xy = (x + w - 1, y)
                XY = (x + w - 1, y + h - 1)

                draw = PIL.ImageDraw.Draw(canvas)
                draw.line(xy + Xy, fill=color)
                draw.line(xy + xY, fill=color)
                draw.line(xY + XY, fill=color)
                draw.line(Xy + XY, fill=color)
                draw.line(xy + XY, fill=color)
                draw.line(xY + Xy, fill=color)
        return canvas

    def draw_borders(self, canvas):
        if self.border_width == 0:
            return

        W = self.page.w - 1
        H = self.page.h - 1
        border = self.border_width - 1
        color = self.border_color

        draw = PIL.ImageDraw.Draw(canvas)
        draw.rectangle((0, 0) + (border, H), color)
        draw.rectangle((W - border, 0) + (W, H), color)
        draw.rectangle((0, 0) + (W, border), color)
        draw.rectangle((0, H - border) + (W, H), color)

        for col in self.page.cols:
            # Draw horizontal borders
            for c in col.cells[1:]:
                xy = (col.x, c.y - border / 2)
                XY = (col.x + col.w, c.y + border / 2)
                draw.rectangle(xy + XY, color)
            # Draw vertical borders
            if col.x > 0:
                for c in col.cells:
                    if not c.is_extension():
                        xy = (col.x - border / 2, c.y)
                        XY = (col.x + border / 2, c.y + c.h)
                        draw.rectangle(xy + XY, color)
        return canvas

    def open_photo(self, cell):
        img = PIL.Image.open(cell.photo.filename)

        # Rotate image if EXIF says so.
        if cell.photo.orientation == 3:
            img = img.rotate(180, expand=True)
        elif cell.photo.orientation == 6:
            img = img.rotate(270, expand=True)
        elif cell.photo.orientation == 8:
            img = img.rotate(90, expand=True)

        return img

    def resample_method(self):
        if self.quality == QUALITY_FAST:
            return fast_resample()
        return high_quality_resample()

    def effective_crop_mode(self, cell):
        if self.crop_mode == CROP_SMART:
            if cell_crop_fraction(cell) > self.max_crop:
                return CROP_CONTAIN
            return CROP_COVER
        return self.crop_mode

    def resize_photo_cover(self, img, cell, method):
        shape = img.size[0] * cell.h - img.size[1] * cell.w
        if shape > 0:  # image is too thick
            img = img.resize((int(round(cell.h * img.size[0] / img.size[1])),
                              int(round(cell.h))), method)
        elif shape < 0:  # image is too tall
            img = img.resize((int(round(cell.w)),
                              int(round(cell.w * img.size[1] / img.size[0]))),
                             method)
        else:
            img = img.resize((int(round(cell.w)), int(round(cell.h))), method)

        if shape > 0:  # image is too thick
            width_to_crop = img.size[0] - cell.w
            img = img.crop((
                int(round(width_to_crop * cell.photo.offset_w)),
                0,
                int(round(img.size[0] - width_to_crop *
                    (1 - cell.photo.offset_w))),
                int(round(cell.h))
            ))
        elif shape < 0:  # image is too tall
            height_to_crop = img.size[1] - cell.h
            img = img.crop((
                0,
                int(round(height_to_crop * cell.photo.offset_h)),
                int(round(cell.w)),
                int(round(img.size[1] - height_to_crop *
                    (1 - cell.photo.offset_h)))
            ))

        return composite_on_background(img, self.background_color)

    def resize_photo_contain(self, img, cell, method):
        scale = min(float(cell.w) / float(img.size[0]),
                    float(cell.h) / float(img.size[1]))
        target_w = max(1, int(round(img.size[0] * scale)))
        target_h = max(1, int(round(img.size[1] * scale)))
        img = img.resize((target_w, target_h), method)
        img = composite_on_background(img, self.background_color)

        canvas = PIL.Image.new(
            "RGB",
            (int(round(cell.w)), int(round(cell.h))),
            self.background_color,
        )
        offset_x = int(round((canvas.size[0] - img.size[0]) / 2.0))
        offset_y = int(round((canvas.size[1] - img.size[1]) / 2.0))
        canvas.paste(img, (offset_x, offset_y))
        return canvas

    def resize_photo(self, cell, use_cache=False):
        img = self.open_photo(cell)
        method = self.resample_method()

        if self.effective_crop_mode(cell) == CROP_CONTAIN:
            return self.resize_photo_contain(img, cell, method)
        return self.resize_photo_cover(img, cell, method)

    def paste_photo(self, canvas, cell, img):
        canvas.paste(img, (int(round(cell.x)), int(round(cell.y))))
        return canvas

    def run(self):
        try:
            canvas = PIL.Image.new(
                "RGB", (int(self.page.w), int(self.page.h)),
                self.background_color)

            self.draw_skeleton(canvas)
            self.draw_borders(canvas)

            if self.quality != QUALITY_SKEL:
                n = sum([len([cell for cell in col.cells if not
                              cell.is_extension()]) for col in self.page.cols])
                i = 0.0
                if self.on_update:
                    self.on_update(canvas, 0.0)
                last_update = time.time()

                for col in self.page.cols:
                    for c in col.cells:
                        if self.canceled:  # someone clicked "abort"
                            return

                        if c.is_extension():
                            continue

                        img = self.resize_photo(c, use_cache=True)
                        self.paste_photo(canvas, c, img)

                        # Only needed for interactive rendering
                        if self.on_update:
                            self.draw_borders(canvas)

                        i += 1
                        now = time.time()
                        if self.on_update and now > last_update + 0.1:
                            self.on_update(canvas, i / n)
                            last_update = now

                self.draw_borders(canvas)

            if self.output_file:
                canvas.save(self.output_file)

            if self.on_complete:
                self.on_complete(canvas)
        except Exception as e:
            if self.on_fail:
                self.on_fail(e)
