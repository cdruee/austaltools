.. You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

*************************************
Welcome to austaltools documentation!
*************************************

This documentation is currently being built up.
Please do not expect it to be complete.

=======
General
=======

.. automodule:: austaltools
   :members:

****************************************
Provide input for AUSTAL (or AUSTAL2000)
****************************************

============
austal-input
============

This is the most simple way to create input data for AUSTAL.
For example::

  austal-input 49.75 6.75 Kundelbach

will produce the files ``Kundelbach.gird`` and  ``Kundelbach.akterm``.
It calls ``austal-weather`` and ``austal-terrain`` internally,
selcting standard options (year 2000, default sources).

Its full command-line options are as the following:

.. argparse::
   :module: austaltools.austal_input
   :func: cli_parser
   :prog: austal-input

=======
Weather
=======

.. argparse::
   :module: austaltools.austal_weather
   :func: cli_parser
   :prog: austal-weather

=======
Terrain
=======

.. argparse::
   :module: austaltools.austal_terrain
   :func: cli_parser
   :prog: austal-terrain



==============
Developer info
==============



 :doc:`apidoc`

==========
References
==========

.. [WMO_8] World Meteorological Organization, 2014: Guide to Meteorological
    Instruments and Methods of Observation,  WMO-No. 8, World
    Meteorological Organization (WMO), Geneva, Switzerland, 1177pp.
.. [WMO_49] World Meteorological Organization, (WMO), 2012:
    Technical Regulations, Basic Documents No. 2, Volume I -
    General meteorological standards and recommended practices,
    Appendix A, WMO-No. 49, 2011, updated 2012,
    WMO, Geneva Switzerland,  83pp.

==================
Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
