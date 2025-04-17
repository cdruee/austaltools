:orphan:

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
to describe more complex patterns.

variable values
---------------

To use an emission cycle with variable values,
use the variant ``-c, --cycle``.
For this you have to create a file called ``cycle.yaml``
in the same directory, where the control file ``austal.txt`` is located.
In this file which you can describe the emission cycle for each
indiviual source and pollutant in the
[YAML](https://de.wikipedia.org/wiki/YAML) language.

**defining each pollutant explicitly**

The file has the following structure (the indentations and hyphens are important!): ::

    myname:
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

      - The number can be either a single number (`5`)
        or a comma-separated list without spaces (`1,17,17`).
        spaces (`1,17,28,39`) or a sequence "from" - "to" / "in steps of" (`1-9/2`).
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

**using a pre-calulated timeseries**

Instead of giving ``start`` and ``sequence``,
use the keyword ``timeseries``.

Under this keyword, either a file can be specified or
the data can be given as a list.

In case a file is used, ``timeseries`` must contain the value ``file``.
By default, the file must be in csv format:

   - comma-separated lines,
   - fist line contains comma-seprated list of column names,
   - timestamps are in first column

Optionally, the format may be selected by giving the additional
value ``format``. For the time being

Example: ::

     cycle_nox:
       column: 01.nox
         timeseries:
           file:
             name: emissiondata.csv
             var: NOx

In case data are given as list, ``timeseries`` must contain
the keyword ``table``. Under this the keywords ``data`` and ``var``
must exist, ``columns`` may be given optionally.
``data`` has to contain the data as a list ofr records:

  - one line per timestamp,
  - comma-sepetrated columns,
  - timestamps are in first column

``var`` selects the columt to pick.
``column`` allows to specify the columns names as a seperate list,
instead of the first row under ``data``.

Example: ::

     cycle_so2:
       column: 01.so2
         timeseries:
           data:
             var: SO2
             data:
             - 2000-01-01 00:00,0.0003,0.0010
             - 2000-01-01 01:00,0.0004,0.0023
             - 2000-01-01 02:00,0.0005,0.0034
     ...
             - 2000-12-31 22:00,0.0002,0.0052
             - 2000-12-31 23:00,0.0001,0.0019
             columns: [time, SO2, PAK]

**using templates**

If multiple pollutants from one source or pollutants from multiple sources
are emitted following the same schedule. The schedule may be defined
in a template that is referred to in one or more cycles::

     template1
       factors:
         nox: 1.0
         so2: 2.75
       start:
         at:
         time: 1-52
         unit: week
       offset:
         time: 1
         unit: day
       sequence:
        - const:
            time: 24
            unit: hour
            value: 1.1
       unit: g/h

     cycle1:
       column: 01.nox
       template:
         name: template1
     cycle2:
       column: 01.so2
       template:
         name: template1
     cycle3
       column: 02.xx
       template:
         name: template1
         substance: so2
         multiplier: 2.5

In this example: ``template1`` defines a template, including the schedule
and a substance-independent emission value (Here: ``1.1 g/s``). For
each pollutant emitted, this value is multiplied by a substance-specific
factor (here: 1.0 for nox, i.e. the substance-independen value in
this example is actually the NOx output). All pullutants used late
must be defined in this place.

``cycle1`` the defines the cycle of NOx emission from source `01`
that follows the schedule in ``template1``.
The pollutant substance (``nox``) is determined from the
column name (``01.nox``)

``cycle2`` the defines the cycle of SO2 emission from source `01`
that follows the schedule in ``template1``.
The pollutant substance (``so2``) is determined from the
column name (``01.nox``)

``cycle3`` the defines the cycle of the emission of an unknown substance
(``xx``) from source `02` that follows the schedule in ``template1``.
This emission is 2.5 times stronger than the SO2 release from
source `01`.
The pollutant substance (``so2``) is hence is
explicitly selected using the keyword ``substance``.
To clarify: The emission at each time a ``cycle3`` is
the product of: <substance-independent emission value> x
<substance-specific factor> x <multiplier>


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

