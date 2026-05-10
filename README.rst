PhotoCollage
============

*Headless command line tool to make photo collage posters*

PhotoCollage allows you to create photo collage posters from image files or
whole directories. It assembles the input photographs it is given to generate a
poster image. Photos are automatically arranged to fill the whole poster while
keeping each photo as large as possible.

This fork removes the GTK desktop interface and exposes PhotoCollage as a
server-friendly CLI. It is suitable for scripts, Docker containers, homelabs,
and other headless Linux environments.

Features:

* generate random collage layouts from a directory of images
* choose output dimensions in pixels
* choose border color and width
* use a random seed for repeatable layouts
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

Use a deterministic seed and recurse through subdirectories:

.. code:: bash

   photocollage ./photos \
     --recursive \
     --seed 42 \
     --output ./out/collage.png \
     --width 3508 \
     --height 2480 \
     --border-color white \
     --border-percent 1.5

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
     "output": "./out/collage.jpg",
     "width": 3600,
     "height": 2400,
     "border_color": "white",
     "border_percent": 1.0,
     "quality": "best",
     "recursive": true,
     "seed": 42
   }

Run it with:

.. code:: bash

   photocollage --config collage.json

Example TOML config:

.. code:: toml

   input = "./photos"
   output = "./out/collage.jpg"
   width = 3600
   height = 2400
   border_color = "white"
   border_percent = 1.0
   quality = "best"
   recursive = true
   seed = 42

Run it with:

.. code:: bash

   photocollage --config collage.toml

Options
-------

.. code:: text

   positional arguments:
     input                 Input image files or directories.

   options:
     -c, --config PATH     Path to a JSON or TOML config file.
     -o, --output PATH     Output image path.
     --width PX            Output width in pixels.
     --height PX           Output height in pixels.
     --border-width PX     Border width in pixels.
     --border-percent N    Border width as a percentage of larger dimension.
     --border-color COLOR  Border color, e.g. black, white, #ffcc00.
     --quality QUALITY     skeleton, fast, or best.
     --recursive           Search input directories recursively.
     --include-hidden      Include hidden files and directories.
     --seed N              Random seed for repeatable layouts.

Hacking
-------

If you changed the source and want to test your modifications, run:

.. code:: bash

   python -m photocollage.cli ./photos --output ./out/collage.jpg

If you wish to contribute, please lint your code and pass tests:

.. code:: bash

   flake8 .
   python -m unittest tests/test_*.py
