# Copyright (C) 2026 Thomas Cottrell-Duncan
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""Headless command line interface for PhotoCollage."""

import argparse
import json
import math
import os
from pathlib import Path
import random
import sys

from PIL import ImageColor

from photocollage import collage, render
from photocollage.render import PIL_SUPPORTED_EXTS as EXTS

DEFAULTS = {
    "input": [],
    "output": "collage.jpg",
    "width": 1600,
    "height": 1200,
    "border_width": None,
    "border_percent": 1.0,
    "border_color": "black",
    "background_color": "white",
    "quality": "best",
    "recursive": False,
    "include_hidden": False,
    "seed": None,
    "max_upscale": None,
    "crop_mode": "smart",
    "max_crop": 0.10,
    "layout_tries": 50,
}

QUALITY_BY_NAME = {
    "skeleton": render.QUALITY_SKEL,
    "fast": render.QUALITY_FAST,
    "best": render.QUALITY_BEST,
}


def supported_input_extensions():
    all_types = dict(list(EXTS.RW.items()) + list(EXTS.RO.items()))
    extensions = set()
    for values in all_types.values():
        extensions.update("." + value.lower() for value in values)
    return extensions


def normalize_config_keys(data):
    return {str(key).replace("-", "_"): value for key, value in data.items()}


def load_config(path):
    if path is None:
        return {}

    config_path = Path(path)
    suffix = config_path.suffix.lower()

    with config_path.open("rb") as fh:
        if suffix == ".json":
            return normalize_config_keys(json.load(fh))
        if suffix == ".toml":
            try:
                import tomllib
            except ModuleNotFoundError:
                try:
                    import tomli as tomllib
                except ModuleNotFoundError as exc:
                    raise SystemExit(
                        "TOML config requires Python 3.11+ or the optional "
                        "tomli package. Use JSON config instead."
                    ) from exc
            return normalize_config_keys(tomllib.load(fh))

    raise SystemExit("Config files must be .json or .toml")


def collect_image_files(inputs, recursive=False, include_hidden=False):
    extensions = supported_input_extensions()
    files = []

    for value in inputs:
        path = Path(value).expanduser()
        if not path.exists():
            raise SystemExit("Input path does not exist: {}".format(path))

        if path.is_file():
            candidates = [path]
        else:
            pattern = "**/*" if recursive else "*"
            candidates = [candidate for candidate in path.glob(pattern)
                          if candidate.is_file()]

        for candidate in candidates:
            if not include_hidden and any(part.startswith(".")
                                          for part in candidate.parts):
                continue
            if candidate.suffix.lower() in extensions:
                files.append(candidate)

    return [str(path) for path in sorted(set(files), key=lambda p: str(p))]


def build_page(photolist, width, height, seed=None):
    if seed is not None:
        random.seed(seed)

    ratio = float(height) / float(width)
    avg_ratio = sum(float(photo.h) / float(photo.w) for photo in photolist)
    avg_ratio = avg_ratio / len(photolist)
    virtual_no_imgs = 2 * len(photolist)
    no_cols = max(1, int(round(math.sqrt(avg_ratio / ratio * virtual_no_imgs))))

    page = collage.Page(1.0, ratio, no_cols)
    randomized_photos = list(photolist)
    random.shuffle(randomized_photos)
    for photo in randomized_photos:
        page.add_cell(photo)
    page.adjust()
    page.scale(float(width) / page.w)
    return page


def photo_cells(page):
    for col in page.cols:
        for cell in col.cells:
            if not cell.is_extension():
                yield cell


def cell_upscale(cell):
    source_long_edge = max(float(cell.photo.w), float(cell.photo.h))
    target_long_edge = max(float(cell.w), float(cell.h))
    if source_long_edge <= 0:
        return 1.0
    return target_long_edge / source_long_edge


def collect_upscale_warnings(page, max_upscale=None):
    warnings = []
    for cell in photo_cells(page):
        upscale = cell_upscale(cell)
        if upscale > 2.0:
            warnings.append((upscale, cell.photo.filename, cell.photo.w,
                             cell.photo.h, cell.w, cell.h))

    warnings.sort(reverse=True, key=lambda item: item[0])

    if max_upscale is not None:
        offenders = [item for item in warnings if item[0] > max_upscale]
        if offenders:
            lines = [
                "One or more images would be upscaled beyond --max-upscale={:.2f}.".format(max_upscale),
                "Use larger source images, lower the output size, or raise --max-upscale.",
            ]
            for upscale, filename, src_w, src_h, cell_w, cell_h in offenders[:10]:
                lines.append(
                    "- {}: {:.1f}x upscale from {}x{} to cell {:.0f}x{:.0f}".format(
                        filename, upscale, src_w, src_h, cell_w, cell_h
                    )
                )
            raise SystemExit("\n".join(lines))

    return warnings


def print_upscale_warnings(warnings):
    if not warnings:
        return

    print(
        "Warning: some images are being enlarged heavily, so output may look soft or pixelated.",
        file=sys.stderr,
    )
    for upscale, filename, src_w, src_h, cell_w, cell_h in warnings[:10]:
        print(
            "- {}: {:.1f}x upscale from {}x{} to cell {:.0f}x{:.0f}".format(
                filename, upscale, src_w, src_h, cell_w, cell_h
            ),
            file=sys.stderr,
        )


def score_cell(cell, crop_mode, max_crop):
    crop = render.cell_crop_fraction(cell)
    upscale = max(0.0, cell_upscale(cell) - 1.0)

    photo_ratio = float(cell.photo.h) / float(cell.photo.w)
    cell_ratio = float(cell.h) / float(cell.w)
    aspect_mismatch = abs(math.log(photo_ratio / cell_ratio))

    # Cover fills the collage, but can damage framing. Smart strongly avoids
    # cells that exceed max_crop because those will render as contained images.
    if crop_mode == render.CROP_CONTAIN:
        contain_penalty = aspect_mismatch * 1.5
        crop_penalty = 0.0
        overflow_penalty = 0.0
    elif crop_mode == render.CROP_SMART and crop > max_crop:
        contain_penalty = aspect_mismatch * 1.2
        crop_penalty = max_crop * max_crop
        overflow_penalty = (crop - max_crop) * 8.0
    else:
        contain_penalty = 0.0
        crop_penalty = crop * crop * 10.0
        overflow_penalty = max(0.0, crop - max_crop) * 20.0

    upscale_penalty = upscale * upscale * 0.25
    return crop_penalty + overflow_penalty + contain_penalty + upscale_penalty


def score_page(page, crop_mode, max_crop):
    cells = list(photo_cells(page))
    if not cells:
        return float("inf")
    return sum(score_cell(cell, crop_mode, max_crop) for cell in cells) / len(cells)


def build_best_page(photolist, width, height, seed=None, layout_tries=1,
                    crop_mode=render.CROP_SMART, max_crop=0.10):
    layout_tries = max(1, int(layout_tries))
    best_page = None
    best_score = None
    best_seed = None

    seed_source = random.Random(seed)
    for index in range(layout_tries):
        if seed is None:
            candidate_seed = random.randrange(0, 2 ** 32)
        elif index == 0:
            candidate_seed = seed
        else:
            candidate_seed = seed_source.randrange(0, 2 ** 32)

        page = build_page(photolist, width, height, seed=candidate_seed)
        score = score_page(page, crop_mode, max_crop)
        if best_score is None or score < best_score:
            best_page = page
            best_score = score
            best_seed = candidate_seed

    return best_page, best_score, best_seed


def render_to_file(page, output_file, border_width, border_color,
                   background_color, quality, crop_mode, max_crop):
    errors = []

    def on_fail(exception):
        errors.append(exception)

    task = render.RenderingTask(
        page,
        border_width=border_width,
        border_color=border_color,
        background_color=background_color,
        quality=QUALITY_BY_NAME[quality],
        crop_mode=crop_mode,
        max_crop=max_crop,
        output_file=output_file,
        on_fail=on_fail,
    )
    task.run()

    if errors:
        raise errors[0]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate a photo collage from image files or directories."
    )
    parser.add_argument("input", nargs="*", help="Input image files or directories.")
    parser.add_argument("-c", "--config", help="Path to a JSON or TOML config file.")
    parser.add_argument("-o", "--output", help="Output image path.")
    parser.add_argument("--width", type=int, help="Output width in pixels.")
    parser.add_argument("--height", type=int, help="Output height in pixels.")
    parser.add_argument("--border-width", type=float, help="Border width in pixels.")
    parser.add_argument(
        "--border-percent",
        type=float,
        help="Border width as a percentage of the larger output dimension.",
    )
    parser.add_argument("--border-color", help="Border color, e.g. black, white, #ffcc00.")
    parser.add_argument(
        "--background-color",
        help="Canvas/background color used behind transparent images.",
    )
    parser.add_argument("--quality", choices=sorted(QUALITY_BY_NAME), help="Rendering quality.")
    parser.add_argument("--recursive", action="store_true", default=None)
    parser.add_argument("--include-hidden", action="store_true", default=None)
    parser.add_argument("--seed", type=int, help="Random seed for repeatable layouts.")
    parser.add_argument(
        "--max-upscale",
        type=float,
        help="Fail if any source image must be enlarged by more than this factor.",
    )
    parser.add_argument(
        "--crop-mode",
        choices=render.CROP_MODES,
        help="cover fills each cell, contain preserves the whole image, smart contains only when cover would over-crop.",
    )
    parser.add_argument(
        "--max-crop",
        type=float,
        help="Maximum allowed crop fraction per image before smart mode falls back to contain.",
    )
    parser.add_argument(
        "--layout-tries",
        type=int,
        help="Number of random candidate layouts to score before rendering.",
    )
    return parser.parse_args(argv)


def merged_options(args):
    options = dict(DEFAULTS)
    options.update(load_config(args.config))

    for key in (
        "output", "width", "height", "border_width", "border_percent",
        "border_color", "background_color", "quality", "recursive",
        "include_hidden", "seed", "max_upscale", "crop_mode", "max_crop",
        "layout_tries",
    ):
        value = getattr(args, key)
        if value is not None:
            options[key] = value

    if args.input:
        options["input"] = args.input
    if isinstance(options["input"], str):
        options["input"] = [options["input"]]

    return options


def main(argv=None):
    args = parse_args(argv)
    options = merged_options(args)

    if not options["input"]:
        raise SystemExit("No input images or directories were provided.")

    files = collect_image_files(
        options["input"],
        recursive=bool(options["recursive"]),
        include_hidden=bool(options["include_hidden"]),
    )
    if not files:
        raise SystemExit("No supported image files were found.")

    crop_mode = str(options["crop_mode"])
    max_crop = float(options["max_crop"])
    if max_crop < 0.0 or max_crop > 1.0:
        raise SystemExit("--max-crop must be between 0 and 1.")

    photolist = render.build_photolist(files)
    page, layout_score, layout_seed = build_best_page(
        photolist,
        int(options["width"]),
        int(options["height"]),
        seed=options["seed"],
        layout_tries=int(options["layout_tries"]),
        crop_mode=crop_mode,
        max_crop=max_crop,
    )

    warnings = collect_upscale_warnings(page, options["max_upscale"])
    print_upscale_warnings(warnings)

    if options["border_width"] is not None:
        border_width = float(options["border_width"])
    else:
        border_width = (
            float(options["border_percent"]) / 100.0 *
            max(float(options["width"]), float(options["height"]))
        )

    border_color = ImageColor.getrgb(str(options["border_color"]))
    background_color = ImageColor.getrgb(str(options["background_color"]))
    output = str(Path(options["output"]).expanduser())
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)

    render_to_file(
        page,
        output,
        border_width=border_width,
        border_color=border_color,
        background_color=background_color,
        quality=str(options["quality"]),
        crop_mode=crop_mode,
        max_crop=max_crop,
    )

    print(
        "Wrote {} using {} image(s); layout score {:.4f}, seed {}.".format(
            output, len(files), layout_score, layout_seed
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
