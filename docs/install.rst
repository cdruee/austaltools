.. -* -**coding**: utf-8 -*-

*************
Installation
*************

Generic installation:
~~~~~~~~~~~~~~~~~~~~~

Users can install Austaltools from the Python Package Index (PyPI) by:

::

   pip install austaltools

Installing Austaltools using ``pip`` also installs
all the necessary dependencies.

**Note:**

The Geospatial Data Abstraction Library (GDAL), which is used
by AustalTools for geospatial data handling, may not have its
full functionality if it was installed prior to AustalTools as
a system package (Linux) or a binary distribution (Windows).
In such cases, it is necessary to additionally install 'libgdal'
and its development headers
(see the `GDAL download page <https://gdal.org/en/stable/download.html>`_
for instructions matching your system).

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

   Fix this by eiter adding the following code to your ``.profile``
   file:

   ::

       # set PATH so it includes user's private bin if it exists
       if [ -d "$HOME/.local/bin" ] ; then
           PATH="$HOME/.local/bin:$PATH"
       fi

   or  - **if you do not already have a ``bin`` directory in your home directory** - by orgissuing the command:

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
   is needed because without this option, ``pip3`` updates the python gdal
   bindings to its newest version that does not match the gdal version
   installed on your system!

   Remember that everytime you want to use AustalTools, you need to
   activate the virtual environment. You can leave it anytime issuing
   the command ``deactivate``.


Requirements:
~~~~~~~~~~~~~

Austaltools uses the following python packages:

 -**cdsapi**:
  The `Climate Data Store Application Program Interface
  (CDS API) <https://cds.climate.copernicus.eu/how-to-api>`_
  is a Python library which allows you to access data from the CDS
  programmatically
 -**GDAL**:
  The
  `Geospatial Data Abstraction Library <https://gdal.org/en/stable/>`_
  is a library for translation and processing of raster and vector
  geospatial data.
 -**matplotlib**:
  `Matplotlib <https://matplotlib.org/>`_ is a comprehensive
  library for creating visualizations in Python.
 -**meteolib**:
  `Meteolib <https://github.com/cdruee/meteolib>`_ is a Python
  that standard equations, constants and conversions fully backed by
  citable refrences and/or recommendations of the
  World meteorological Organization (WMO), for general use in meteorology.
 -**netCDF4**:
  The `package netCDF4 <https://unidata.github.io/netcdf4-python/>`_
  is a Python interface to the library that implements
  access to files in the `NetCDF (Network Common Data Form)
  <https://www.unidata.ucar.edu/software/netcdf/>`_ format that
  is a community standard for sharing scientific data.
 -**numpy**:
  `NumPy <https://numpy.org/>`_ is a widely-used Python libary
  offering comprehensive mathematical functions, etc.
 -**pandas**:
  `Pandas <https://pandas.pydata.org/>`_ is a widely-used
  Python tool for data analysis and manipulation.
 -**PyYAML**:
  `PyYAML <https://pyyaml.org/>`_ is a parser and emitter
  for Python. `YAML (yet another markup language) <https://yaml.org/>`_
  a data description and serialization language that is easy to read
  for humans.
 -**readmet**:
  `readmet <https://github.com/cdruee/readmet>`_ is a open-source Python
  library for reading and writing a selection of data formats used
  in atmospheric sciences.
 -**requests**:
  `Requests <https://requests.readthedocs.io/en/latest/>`_
  is a simple-to-use Python library for making web-requests.
 -**setuptools**:
  `library <https://setuptools.pypa.io>`_
  designed to facilitate packaging Python projects.
 -**urllib3**:
  Is is a requirement of *requests*, but it needs to be imported
  separately for better control of the excessive warnings emitted
  by *requests*.

To generate the documentation, AustalTools uses:
 -**sphinx**:
  `Sphinx <https://www.sphinx-doc.org/>`_
   is a documentation generator written and used by the Python community.
 -**sphinx-argparse**:
  `Sphinx extension <https://github.com/sphinx-doc/sphinx-argparse/>`_
  to automatically document argparse commands and options.
