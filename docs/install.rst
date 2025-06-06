.. -*- coding: utf-8 -*-

*************
Installation
*************

Generic installation:
~~~~~~~~~~~~~~~~~~~~~

In order to be able to install austaltools, the following dependencies
are required:

::

    pip install meteolib numpy pandas pyyaml readmet

You also need Geospatial Data Abstraction Library (GDAL, see the
`GDAL download page <https://gdal.org/en/stable/download.html>`_
for instructions matching your system) and the gdal Python bindings:

::

   pip install gdal

To enable plotting and for a clearer screen display, install

::

   pip install tqdm matplotlib

Then install austaltools from Pypi:

::

   pip install austaltools

or download the source distribution and install with

::

   python3 setup.py install --user

Ubuntu / Debian Linux:
~~~~~~~~~~~~~~~~~~~~~~

Add needed components of the Python Installation

::

   sudo apt install python3-pip python-is-python3 python3-setuptools

Install required dependencies (note ``libgdal-dev`` that is required for
the austaltools installation process):

::

   sudo apt install python3-numpy python3-pandas
   sudo apt install gdal-bin gdal-data python3-gdal libgdal-dev

Install recommended dependencies as you wish:

::

   sudo apt install python3-tqdm python3-matplotlib python3-venv

Then install austaltools from Pypi:

1. Variant: install for user

   ::

       pip3 install --user --break-system-packages --no-build-isolation austaltools

   This may probably produce a warning message
   ``...installed in '/home/benutzer/.local/bin' which is not on PATH.``
   meaning that you cannot yet use AustalTools like normal commands.

   Fix this by eiter adding the following code to you\ ``.profile``
   file:

   ::

       # set PATH so it includes user's private bin if it exists
       if [ -d "$HOME/.local/bin" ] ; then
           PATH="$HOME/.local/bin:$PATH"
       fi

   or - if you do not already have a ``bin`` directory in your home
   directory - by issuing the command:

   ::

       ln -s ~/.local/bin ~/bin

   and logging out and in again.

2. Variant: install in a virtual environment

   Create a new virtual environment by:

   ::

       python3 -m venv my_venv

   and ‘change into’ it by issuing the command

   ::

       . my_venv/bin/activate

   Then install austaltools inside the virtual environment:

   ::

       pip3 install --no-build-isolation austaltools

   Note that although in a virtual environment, ``--no-build-isolation``
   is needed because without this option, pip updates the python gdal
   bindings to its newest version that does not match the gdal version
   installed on your system!

   Remember that everytime you want to use AustalTools, you need to
   activate the virtual environment. You can leave it anytime issuing
   the command ``deactivate``.
