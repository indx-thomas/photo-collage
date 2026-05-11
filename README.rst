PhotoCollage
============

*Headless command line tool to make photo collage posters*

PhotoCollage allows you to create photo collage posters from image files or
whole directories. It assembles the input photographs it is given to generate a
poster image. Photos are automatically arranged to fill the whole poster while
trying to preserve the original photo framing.

This fork removes the GTK desktop interface and exposes PhotoCollage as a
server-friendly CLI. It is suitable for scripts, Docker containers, homelabs,
and other headless Linux environments.

Features:

* generate random collage layouts from a directory of images
* choose output dimensions in pixels
* choose border color and width
* choose a background color for transparent PNG/WebP assets
* preserve framing with cover, contain, and smart crop modes
* score multiple candidate layouts and pick the best one
* use a random seed for repeatable layouts
* warn or fail when small images would be upscaled too far
* save high-resolution images
* works with a large number of photos (> 100)
* accepts command-line options or JSON/TOML configuration files

Installation
------------

Install from this repository:

.. code:: bash

   python -m pip install .

For editable local development:

.. code:: bash

   python -m pip install -e .

Usage
-----

Generate a collage from a directory:

.. code:: bash

   photocollage ./photos --output ./out/collage.jpg --width 3600 --height 2400

Use smart crop defaults for family photos. This preserves framing when a cell
would otherwise require a heavy crop:

.. code:: bash

   photocollage ./photos \
     --output ./out/collage.png \
     --width 1600 \
     --height 1200 \
     --background-color black \
     --border-color black \
     --quality best \
     --max-upscale 3

Try more candidate layouts for better composition:

.. code:: bash

   photocollage ./photos \
     --output ./out/collage.png \
     --width 1600 \
     --height 1200 \
     --crop-mode smart \
     --max-crop 0.08 \
     --layout-tries 100

Crop modes:

* ``cover`` fills every cell. This creates a tight collage, but can crop photo framing aggressively.
* ``contain`` preserves every full photo. This may add background padding inside cells.
* ``smart`` uses cover when crop is minor, but falls back to contain when cover would exceed ``--max-crop``.

For transparent logo or artwork assets, choose the canvas background explicitly:

.. code:: bash

   photocollage ./logos \
     --output ./out/collage.png \
     --width 1600 \
     --height 1200 \
     --background-color black \
     --border-color black \
     --quality best

To reject tiny source images before they become pixelated, set a maximum upscale
factor:

.. code:: bash

   photocollage ./photos \
     --output ./out/collage.png \
     --width 1600 \
     --height 1200 \
     --max-upscale 3

Supported input files are the formats Pillow can read, including common JPEG,
PNG, GIF, TIFF, BMP, WebP and related formats.

Configuration files
-------------------

JSON and TOML config files are supported. Command-line options override values
from the config file.

Example JSON config:

.. code:: json

   {
     "input": "./photos",
     "output": "./out/collage.png",
     "width": 3600,
     "height": 2400,
     "border_color": "white",
     "background_color": "black",
     "border_percent": 1.0,
     "quality": "best",
     "recursive": true,
     "seed": 42,
     "max_upscale": 3,
     "crop_mode": "smart",
     "max_crop": 0.10,
     "layout_tries": 50
   }

Run it with:

.. code:: bash

   photocollage --config collage.json

Example TOML config:

.. code:: toml

   input = "./photos"
   output = "./out/collage.png"
   width = 3600
   height = 2400
   border_color = "white"
   background_color = "black"
   border_percent = 1.0
   quality = "best"
   recursive = true
   seed = 42
   max_upscale = 3
   crop_mode = "smart"
   max_crop = 0.10
   layout_tries = 50

Run it with:

.. code:: bash

   photocollage --config collage.toml

Options
-------

.. code:: text

   positional arguments:
     input                       Input image files or directories.

   options:
     -c, --config PATH           Path to a JSON or TOML config file.
     -o, --output PATH           Output image path.
     --width PX                  Output width in pixels.
     --height PX                 Output height in pixels.
     --border-width PX           Border width in pixels.
     --border-percent N          Border width as a percentage of larger dimension.
     --border-color COLOR        Border color, e.g. black, white, #ffcc00.
     --background-color COLOR    Background color behind transparent images.
     --quality QUALITY           skeleton, fast, or best.
     --recursive                 Search input directories recursively.
     --include-hidden            Include hidden files and directories.
     --seed N                    Random seed for repeatable layouts.
     --max-upscale N             Fail if an image must be enlarged beyond N times.
     --crop-mode MODE            cover, contain, or smart. Defaults to smart.
     --max-crop N                Crop fraction threshold for smart mode. Defaults to 0.10.
     --layout-tries N            Candidate layouts to score. Defaults to 50.

Hacking
-------

If you changed the source and want to test your modifications, run:

.. code:: bash

   python -m photocollage.cli ./photos --output ./out/collage.jpg

If you wish to contribute, please lint your code and pass tests:

.. code:: bash

   flake8 .
   python -m unittest tests/test_*.py
