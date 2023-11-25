austaltools
======

This module conatins tools for use with Langrangian dispersion model AUSLTA (AUSbreitungsmodell nach TA Luft)

### Requirements:

    pip install numpy pandas meteolib

### Installation:

    python3 setup.py install


Documentation: 
==============

## Time dependent simulation

For this purpose there is the utility `austal-fill-time-series`
```
usage: austal-fill-timeseries [-h] [--debug | -v] (-l | -c | -w | -W) [-b HOUR] [-e HOUR] [-u HOLIDAY_WEEK [HOLIDAY_WEEK ...] | -U
                              HOLIDAY_MONTH [HOLIDAY_MONTH ...]] [-f CYCLE_FILE] [-s SOURCE_ID] [-o OUTPUT]
                              [PATH]

fill source-strength columns in "zeitreihe.dmna"

positional arguments:
  PATH                  directory where "zeitreihe.dmna" is stored [.]

options:
  -h, --help            show this help message and exit
  --debug               show informative output
  -v, --verbose         show detailed output
  -l, --list            list source column IDs in fileand exit without modifying "zeitreihe.dmna".[default]
  -c, --cycle           use production cycle from file
  -w, --week-5          source active Mon-Fri
  -W, --week-6          source active Mon-Sat
  -b HOUR, --hour-begin HOUR
                        daily work begin time in hours 0-23. Only relevant with -w or -W. [08]
  -e HOUR, --hour-end HOUR
                        daily work end time in hours, 0-23. Only relevant with -w or -W .[16]
  -u HOLIDAY_WEEK [HOLIDAY_WEEK ...], --holiday-week HOLIDAY_WEEK [HOLIDAY_WEEK ...]
                        work-free weeks 1-52 as space-delimited list. Only relevant with -w or -W. [25 26 27 28 29 30 52]
  -U HOLIDAY_MONTH [HOLIDAY_MONTH ...], --holiday-month HOLIDAY_MONTH [HOLIDAY_MONTH ...]
                        work-free months 1-12 as space-delimited list. Only relevant with -w or -W. 7]
  -f CYCLE_FILE, --cycle-file CYCLE_FILE
                        emission-cycle description file. only relevant with -c. [cycle.yaml]
  -s SOURCE_ID, --source-id SOURCE_ID
                        source ID. Required if more than one source. list IDs in file with -l.
  -o OUTPUT, --output OUTPUT
                        output of the source in g/s. Only relevant with -w or -W.
```
There are two ways to describe the emissions, fixed and variable values:
##### fixed value
This type is used to characterize a source that is either on or off.
The source output strength for each hour the source is active, is
given in g/s using parameter `-o`,`--output`.

Option `-w`/`--week-5` defines a source active Mon-Fri,
 `-W`/`--week-6` defines a source active Mon-Sat.
Options `-b` and `-e` describe the start and end times of the
emission on each day the source is active:
`-b`, `--hour-begin` defines the first active hour
(0-23)  and defaults to 8.
Only relevant with -w or -W. [08]
`-e`, `--hour-end` defines the last active hour
(0-23) and defaults to 16.
Options `-u` and `-U` can be used to define
weeks or months in which the source does not emit.
`-u`,/`--holiday-week` can be given followed by one or multiple
week numbers (0-52).
`-U`/`--holiday-month` can be given followed by one or multiple
month numbers (1-12).
Options `-u` and `-U` may be used together
to describe comples patterns.

##### variable values
To use an emission cycle with variable values,
use the variant `-c, --cycle`. For this you have to create a file called `cycle.yaml` in the same directory,
where the control file `austal.txt` is located, you have to create a file named `cycle.yaml`.
in which you can describe the emission cycle specify the start times in [YAML](https://de.wikipedia.org/wiki/YAML).
The file has the following structure (the indentations and hyphens are important!):
```
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
```   
  - Each cycle in the file has a name, here `meinname`.
  - It is valid for source 1 and substance type sO2, thus `01.so2`. 
    These names can be found as column names in the file `zeitreihe.dmna`, which austal creates.
  - the block `start` specifies the start times:
    - the start time is specified as number(s) `time` and unit `unit`.
      - The number can be either a single number (`5`) or a comma-separated list without spaces (`1,17,17`).
        spaces (`1,17,28,39`) or a sequence "from" - "to" / "in steps of" (`1-9/2`).
      - Possible units are `month`, `week`, `day` and `hour`.
    - Optionally you can add an `offset`, which is also defined by `time` and `unit`.
      is defined. This makes specifications of the form `every odd month in the 2nd and 4th week` possible,
      as in the example above, are possible.
  - The emission can be specified as `list` or `sequence`.
    - A `list` is a list of hourly values of the source strength.
      - provide values as list of the form
        ```yaml
        list: [1.2, 3.4, 5.6]
        ```
      - or as list of the form
        ```yaml
        list:
        - 1.2
        - 2.3
        - 4.5
        ```
    - A `sequence` consists of elements `ramp` and `const`, for each of which the duration
      and the source strength (the time unit `month` is not possible here).
      For `const` the value is valid for the whole time, for `ramp` the source strength changes linearly over the
      time linearly from the previous value (start = 0) to the specified value.
  - With `#` you can comment out lines in the file.

### How to apply 
You define the sources in `austal.txt` as normal, but specify the 
source strength as `?` instead of a number.

Then you start Austal using the command `austal . -z`. 
It is important that `-z` is *behind* `.` (for whatever reason).

This way you get the file `zeitreihe.dmna`.
In this file, in the line with identifier `form` 
the identifiers of the sources can be found, e.g:
```
form "te%20lt" "ra%5.0f" "ua%5.1f" "lm%7.1f" "01.so2%10.3e"
```
In this example, `01.so2` is the column for the SO2 emission from the first source.
These identifiers must match the `source` entries in `cycle.yaml`.
Each identifier needs exactly one cycle entry in `cycle.yaml`.
If necessary, `cycle.yaml` must be adapted.

Then call (`-c` = "take the cycle file", `.` = "everything in the current directory"):
```
austal-fill-timeseries -c .
```
This will overwrite `zeitreihe.dmna` with a new version **with** emission data.

With this file, you can start the simulation normally
(i.e. with `austal.txt` and the new `zeitreihe.dmna` in the current directory):
```
austal -D .
```
Austal then will report (among other things): `The specification "az ....akterm" is ignored.`


## Extracting amospheric time series from ERA5 reanalysis
```
usage: austal-weather-era5 [-h] [--debug | -v] [-y YEAR] [-p PATH] [-s NR | -l DEGRESS DEGREES] [-n NAME]
                           [-e METERS]

Climate data aggregation

options:
  -h, --help            show this help message and exit
  --debug               show informative output
  -v, --verbose         show detailed output
  -y YEAR, --year YEAR  year of interest [2018]
  -p PATH, --path PATH  path to the data files
  -s NR, --station NR   position by DWD station code [05100]
  -l DEGRESS DEGREES, --latlon DEGRESS DEGREES
                        position by geographic location
  -n NAME, --name NAME  name for the position
  -e METERS, --elevation METERS
                        suface elevation only allowed with -l
```

## Reading buildings from a Geojson file and put them into `austal.txt`
```
usage: austal-buildings-geojson.py [-h] [--debug | -v] [-f FILE] [-z ZVALUE] [-o OUTPUT] [PATH]

get buildings from geojson and convert to "austal.txt"

positional arguments:
  PATH                  directory where "zeitreihe.dmna" is stored [.]

options:
  -h, --help            show this help message and exit
  --debug               show informative output
  -v, --verbose         show detailed output
  -f FILE, --file FILE  file containing building info[haeuser.geojson]
  -z ZVALUE, --zvalue ZVALUE
                        name of property that gives building height[height]
```

## Determine steepness of the model area
```
usage: austal_steepness.py [-h] [-w WORKING_DIR] [-b] [-l] [-c COLORMAP] [-d {contour,grid}] [-p [FILE]] [-f] [-g [ID]] [--debug | -v]

plot AUSTAL topography steepness

options:
  -h, --help            show this help message and exit
  -w WORKING_DIR, --working-dir WORKING_DIR
                        working directory. In this directory the file `austal.txt` is expected. Defaults to "."
  -b, --no-buildings    do not show the buildings defined in config file
  -l, --low-colors      use only few discrete colors for better print results
  -c COLORMAP, --colormap COLORMAP
                        name of colormap to use. Defaults to "YlOrRd"
  -d {contour,grid}, --display {contour,grid}
                        choose kind of display. `contour` produces filled contours, `grid` produces coloured grid cells. Defaults to `contour`
  -p [FILE], --plot [FILE]
                        save plot to a file. If `FILE` is "-" the plot is shown on screen. If `FILE` is missing, the file name defaults to the data file name with extension `png`
  -f, --force           force overwriting plotfile if it exists.
  -g [ID], --grid [ID]  ID (number) of the grid to evaluate. Defaults to 0
  --debug               show informative output
  -v, --verbose         show detailed output

```

## Determine EAP ("Ersatz-AnemometerPosition") accoring to VDI norm
```text
usage: austal_eap.py [-h] [-w WORKING_DIR] [-b] [-l] [-c COLORMAP] [-d {contour,grid}] [-p [FILE]] [-f] [-g [ID]] [-z [METERS]] [-r {simple,file}] [--edge-nodes [EDGE_NODES]] [--max-height [MAX_HEIGHT]] [--min-ff [MIN_FF]]
                     [--debug | -v]

find substitute anemometer position according to VDI 3783 Part 16 from a wind library generated by austal

options:
  -h, --help            show this help message and exit
  -w WORKING_DIR, --working-dir WORKING_DIR
                        working directory. In this directory the file `austal.txt` is expected. Defaults to "."
  -b, --no-buildings    do not show the buildings defined in config file
  -l, --low-colors      use only few discrete colors for better print results
  -c COLORMAP, --colormap COLORMAP
                        name of colormap to use. Defaults to "YlOrRd"
  -d {contour,grid}, --display {contour,grid}
                        choose kind of display. `contour` produces filled contours, `grid` produces coloured grid cells. Defaults to `contour`
  -p [FILE], --plot [FILE]
                        save plot to a file. If `FILE` is "-" the plot is shown on screen. If `FILE` is missing, the file name defaults to the data file name with extension `png`
  -f, --force           force overwriting plotfile if it exists.
  -g [ID], --grid [ID]  ID (number) of the grid to evaluate. Defaults to 0
  -z [METERS], --height [METERS]
                        effective anemometer height, i.e. height to evaluate EAP at in m. Defaults to 10.0
  -r {simple,file}, --reference {simple,file}
                        choose kind of reference profile. `simple` produces a log wind profile, `file` reads reference profile from file. Defaults to `simple`
  --edge-nodes [EDGE_NODES]
                        number of edge nodes along each side, where data are exluded. Defaults to 3
  --max-height [MAX_HEIGHT]
                        maximum height to evaluate EAP. Defaults to 100.000000
  --min-ff [MIN_FF]     minimum wind speed below which data are exluded. Defaults to 0.500000
  --debug               show informative output
  -v, --verbose         show detailed output
```

## Simple baseline data plot
```text
usage: austal_plot.py [-h] [-w WORKING_DIR] [-b] [-l] [-c COLORMAP] [-d {contour,grid}] [-p [FILE]] [-f] [-s [STDVs]] [--debug | -v] DATA

create AUSTAL windlibrary using METRAS

positional arguments:
  DATA                  data file to plot.

options:
  -h, --help            show this help message and exit
  -w WORKING_DIR, --working-dir WORKING_DIR
                        working directory. In this directory the file `austal.txt` is expected. Defaults to "."
  -b, --no-buildings    do not show the buildings defined in config file
  -l, --low-colors      use only few discrete colors for better print results
  -c COLORMAP, --colormap COLORMAP
                        name of colormap to use. Defaults to "YlOrRd"
  -d {contour,grid}, --display {contour,grid}
                        choose kind of display. `contour` produces filled contours, `grid` produces coloured grid cells. Defaults to `contour`
  -p [FILE], --plot [FILE]
                        save plot to a file. If `FILE` is "-" the plot is shown on screen. If `FILE` is missing, the file name defaults to the data file name with extension `png`
  -f, --force           force overwriting plotfile if it exists.
  -s [STDVs], --stdvs [STDVs]
                        hash areas where the data are not significant. Sigingicant is defined as larder than `STDVs` times the standard deviation caculated by austal. If missing, `STDVs` defaults to 1.0.
  --debug               show informative output
  -v, --verbose         show detailed output
```