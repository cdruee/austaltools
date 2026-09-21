:tocdepth: 3

-----------
austaltools
-----------

.. |plotcontour| image:: img/plot_contour_2sigma.png
   :width: 45%
   :align: bottom

.. |plotvolout| image:: img/volout_basilika.png
   :width: 45%
   :align: bottom

.. |plotwindrose| image:: img/windrose.png
   :width: 45%
   :align: bottom

.. |plotwindfield| image:: img/windfield.png
   :width: 45%
   :align: bottom


.. argparse::
   :module: austaltools.command_line
   :func: cli_parser
   :prog: austaltools

   compare-weather
        Compare two weather timeseries by running a synthetic,
        flat-terrain AUSTAL dispersion model for each and measuring
        the overlap of their above-threshold areas.
        See :doc:`api_commands` for the full details (threshold
        selection, ``--no-parallel``, ``--keep-files``, plotting).

   fill-timeseries (ft)
        Detailed userguide see: :doc:`fill-timeseries`

   heating
        For a description of the heating description file
        ``heating.yaml`` see: :doc:`heating`

   simple
        The quickest way to create input data for AUSTAL from just a
        position and a name -- see `Provide input for AUSTAL (or
        AUSTAL2000) <index.html#provide-input-for-austal-or-austal2000>`_
        in the introduction.

   plot
        A simple plot for a quick overview (click to enlarge)
        |plotcontour|

   volout
        Example plot of a buildings volume plot  (click to enlarge)
        |plotvolout|

   windfield
        Example plot of a windfield (click to enlarge)
        |plotwindfield|

   windprofile
        Plots a vertical profile of wind speed and wind direction at
        a given position in the model domain (given by model
        coordinates or by one of the location options), optionally
        overlaid with a measured reference profile read from a plain
        ASCII file, a Scintec FORMAT-1/1.1 sodar file, or a Halo
        Photonics lidar "Processed Wind Profile" ``.hpl`` file.

   windrose
        Example plot of a windrose classified by wind speed quantiles         (click to enlarge)
        |plotwindrose|
