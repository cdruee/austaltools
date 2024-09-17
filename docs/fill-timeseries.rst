---------------------------
austaltools fill-timeseries
---------------------------


Detailed usage guide
====================

There are two ways to describe the emissions, fixed and variable values:

fixed value
-----------

This type is used to characterize a source that is either on or off.
The source output strength for each hour the source is active, is
given in g/s using parameter ``-o``,``--output``.

Option ``-w``/``--week-5`` defines a source active Mon-Fri,
``-W``/``--week-6`` defines a source active Mon-Sat.

Options ``-b`` and ``-e`` describe the start and end times of the
emission on each day the source is active:

``-b``, ``--hour-begin`` defines the first active hour
(0-23)  and defaults to 8.

Only relevant with -w or -W. [08]
``-e``, ``--hour-end`` defines the last active hour
(0-23) and defaults to 16.

Options ``-u`` and ``-U`` can be used to define
weeks or months in which the source does not emit.
``-u``,/``--holiday-week`` can be given followed by one or multiple
week numbers (0-52).
``-U``/``--holiday-month`` can be given followed by one or multiple
month numbers (1-12).
Options ``-u`` and ``-U`` may be used together
to describe comples patterns.

variable values
---------------

To use an emission cycle with variable values,
use the variant ``-c, --cycle``. For this you have to create a file called ``cycle.yaml`` in the same directory,
where the control file ``austal.txt`` is located, you have to create a file named ``cycle.yaml``.
in which you can describe the emission cycle specify the start times in [YAML](https://de.wikipedia.org/wiki/YAML).

The file has the following structure (the indentations and hyphens are important!): ::

    meinname:
      source: 01.so2
      start:
        at:
          time: 1-11/2
          unit: month
        offset:
          time: 1,3
          unit: week
      sequence:
      - ramp:
          time: 1
          unit: day
          value: 9.0
      - const:
          time: 36
          unit: hour
          value: 1.1
      unit: g/h


- Each cycle in the file has a name, here ``meinname``.
- It is valid for source 1 and substance type sO2, thus ``01.so2``.
  These names can be found as column names in the file
  ``zeitreihe.dmna``, which austal creates.

  - the block ``start`` specifies the start times:

    - the start time is specified as number(s) ``time`` and unit ``unit``.

      - The number can be either a single number (``5``) or a comma-separated list without spaces (``1,17,17``).
        spaces (``1,17,28,39``) or a sequence "from" - "to" / "in steps of" (``1-9/2``).
      - Possible units are ``month``, ``week``, ``day`` and ``hour``.
    - Optionally you can add an ``offset``, which is also defined by ``time`` and ``unit``.
      is defined. This makes specifications of the form ``every odd month in the 2nd and 4th week`` possible,
      as in the example above, are possible.
  - The emission can be specified as either ``list`` or ``sequence``.

    - A ``list`` is a list of hourly values of the source strength.

      - provide values as list of the form::

         list: [1.2, 3.4, 5.6]

      - or as list of the form::

         list:
           - 1.2
           - 2.3
           - 4.5

    - A ``sequence`` consists of elements ``ramp`` and ``const``, for each of which the duration
      and the source strength (the time unit ``month`` is not possible here).
      For ``const`` the value is valid for the whole time, for ``ramp`` the source strength changes linearly over the
      time linearly from the previous value (start = 0) to the specified value.
    - ``unit`` can be given optionally, if the unit of the values given
      in the list or sequence is not `g/s` (the generic unit used by austal).
      ``unit`` may be given as a string in the form '`mass`/`time`', where
      `mass` can be one of `t`, `kg`, `g`, `mg`, `ug`, or `µg` and
      `time` can be one of `total` (the whole simulation time),
      `d` (day), `m` or `min` (minute), or `s` or `sec` (second).
      Example `kg/d` for kilograms per day.
  - With ``#`` you can comment out lines in the file.

How to apply
------------

You define the sources in ``austal.txt`` as normal, but specify the
source strength as ``?`` instead of a number.

Then you start Austal using the command ``austal . -z``.
It is important that ``-z`` is *behind* ``.`` (for whatever reason).

This way you get the file ``zeitreihe.dmna``.
In this file, in the line with identifier ``form``
the identifiers of the sources can be found, e.g: ::

  form "te%20lt" "ra%5.0f" "ua%5.1f" "lm%7.1f" "01.so2%10.3e"

In this example, ``01.so2`` is the column for the SO2 emission from the first source.
These identifiers must match the ``source`` entries in ``cycle.yaml``.
Each identifier needs exactly one cycle entry in ``cycle.yaml``.
If necessary, ``cycle.yaml`` must be adapted.

Then call (``-c`` = "take the cycle file", ``.`` = "everything in the current directory"): ::

  austal-fill-timeseries -c .

This will overwrite ``zeitreihe.dmna`` with a new version **with** emission data.

With this file, you can start the simulation normally
(i.e. with ``austal.txt`` and the new ``zeitreihe.dmna`` in the current directory): ::

  austal -D .

Austal then will report (among other things): ::

  The specification "az ....akterm" is ignored.

