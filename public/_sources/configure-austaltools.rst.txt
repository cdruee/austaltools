:orphan:

---------------------
configure-austaltools
---------------------
.. argparse::
   :module: austaltools.configure_austaltools
   :func: cli_parser
   :prog: configure-austaltools

Dataset definitions
-------------------
.. role:: json(code)
   :language: json

Datasets are defined in 'data/dataset_definitions.json':

The file is a dict that contains the dataset codes as keys
and a dict describing the dataset as value.

Each dict has the follwing entries:

"storage"
    (required, str) one of "terrain" or "weather"

"uri"
    (optional, str) A location from where the dataset can be dowloaded.
    Supported uri schemes are "doi://", "http://", and "https://".

"license"
    (required, str) The license under which the orginal source
    supplies the data.
    The license full text will be stored as "<dataset code>.LICENSE.txt"
    in the same data as the dataset when it is downloaded or assembled.
    Licenses may be specified:

    - by an idenfifier recogized by the
      Linux foundation `SPDX project <https://spdx.org/>`_
      (see `this list <https://spdx.org/licenses/>`_)
      prefixed by "spdx:".
      For example: :json:`"license": "spdx:DL-DE-BY-2.0"`

    - in a file that should reside in `austaltools/data`.
      The filename must be prefixed by "file:".
      If the filename is empty, the file "<dataset code>.LICENSE.txt"
      in `austaltools/data` will be used.
      For example: :json:`"license": "file:"`

"notice"
    (optional, str)
    The text of a notice that is shown to the user if data from
    the dataset are extracted, if and as requested by the
    original data suplier.
    The notice will be stored as "<dataset code>.NOTICE.txt"
    in the same data as the dataset when it is downloaded or assembled.

    Unless the value is `null` (without quotes!)
    the value is supplied to the
    For example: :json:`"notice": "Buy coffe for Bob"`


"assemble"
    (optional, str) The function in `austaltools._dataset` to call for
    assembling the dataset fromist original source.
    For available functions see :doc:`api_internal`
    (fundtion names start with "assemble"). For most cases,
    `assemble_DGMxx <api_internal.html#austaltools._datasets.assemble_DGMxx>`__
    is suitable:
    Example: :json:`"assemble": "assemble_DGMxx"`

"arguments"
    (optional, dictionary) The arguments to the
    selected `assemble` function

    "resolution"
        (optional, integer)
        Horizontal resolution for the produced dataset, i.e.
        size of the pixels in units of the selected projection.
        Most commontly m in case of Gauß-Krüger or UTM coodinates.
        Should be euqal to the number following "DGM" in the
        dataset code. Defaults to 25.

    "CRS":
        (optional, str)
        Geodetic refecence system of the downloaded data
        as EPSG-code, for example :json:`"CRS": "EPSG:25832"`

    "host":
        (optional, str)
        Hostname and protocol from where to download data.
        Supported protocols are :code:`"http://..."` and :code:`"https://..."`
        Data stored locally
        (e.g. if only available on physical media) may be
        specified by giving the absolute path
        as :code:`"file:///..."`.
        Example: :json:`"host": "https://geodata.example.com"`

    "check_cert":
        (optional, str)
        Wether to check the server certificates of `host` or not.
        To do so is a normal part of establishing a https connection
        and is done if the value is "true" or "yes".
        But since some of the providers use certificates that,
        although accepted by popular browsers, fail a strict
        verification, it can be disables by setting this value to
        "no" or "false". Defaults to "true".

    "path":
        (optional, str)
        The path to the data on the download server.
        Example: If the datafiles are available at
        :code:`"https://geodata.example.com/foo/bar/baz/tile*.tif"`
        give :code:`"foo/bar/baz"` here

    "filelist":
        (optional, list[str] or str)
        The list of files to download.
        File names may be either given as filenames (optionally
        including a path). In this case the download url
        is build by appending :code:`"<host>/<path>/<filename>"`.
        Or they are given as urls. In this case `host` and `path`
        are ignored.

        If `filelist` is a list (of strings), each entry
        is downloaded from the respective ulr.
        Example: :json:`"filelist": ["data1.tif", "data2.tif"]`

        If `filelist` is a filename (optionally including
        a path as prefix of http GET parameters as postfixes).
        The respective file is downloaded and parsed to yield
        the filenames to download (as if they were provided
        as list).
        Example: :json:`"filelist": "atom/dem.xml"`

        If `filelist` is the special string "generate", the list
        of files is generated using the `format` and `values`
        arguments.

        A downloaded `filelist` is parsed acording to its
        filename exension. Supported formats are 'xml', 'meta4',
        'html', 'json', and 'geojson'.
        Which information is extracted must be defined
        by the arguments `xmplath` (xml and meta4), `links` (html),
        or `jsonpath` (json and geojson).
        If the value of `filelist`
        does not end with any of these, it may be postfixed by
        two colons followed by the desired filename extension.
        This postfix is removed from the string before
        building the url to download.
        Example: "atom_feed?id=awsomedata&crs=25832::xml"

    "localstore":
        (optional, str)
        Path where downloaded files are stored locally.
        If locally stored versions of some or all files in filelist
        are present, these copies are used. Only missing files are
        downloaded.
        Intended to reduce traffic an transfer time in case multiple
        datasets are assebled from the same original data.

    "jsonpath":
        (required for json or geojson filelist, str)
        An path-like expression that selects filenames from a json-file.
        For the syntax see
        `_datasets API documentation <apidoc.html#austaltools._datasets.jsonpath>`__.
        Example  :json:`"jsonpath": "/foo/*/bar/2/url"`

    "links":
        (required for html filelist, regex)
        An `regular expression <https://docs.python.org/3/library/re.html#regular-expression-syntax>`_
        that is used to select the desired links from all links
        that are found in the downloadad html document. All
        links that contain the given expression are put on the list
        to download.
        Example :code:`"links": "dgm.*zip"`

    "xmlpath":
        (required for xml or meta4 filelist, str)
        An XPath expression that selects filenames from an xml-file.
        Note that only a small subset of the XPath specification
        is supported, see
        `_datasets API documentation <apidoc.html#austaltools._datasets.xmlpath>`__.
        Example: :code:`"xmlpath": "/file[@name=.tif$]/url"`

    "format":
        (required with `filelist` = "generate", str)
        A `C-sytle format string <https://docs.python.org/3/library/string.html#format-specification-mini-language>`_
        that is filles using the values supplied in the `values` argument.

    "values"
        (required with `filelist` = "generate", list)
        A list of strings or lists or a mixture thereof.
        The number of members of the list mus be equal to the
        field provided in the `format` string.
        The values in each member must match the type in the
        respective field of the format.

        If an entry is a sting of the form "<start>-<stop>/<step>",
        it is expanded into a list of values. If <step> is missing,
        a step of 1 is used.
        Example: `["1-9/2" ]` is expanded
        to: :json:`[[1, 3, 5, 7, 9] ]`.
        After expanding strings, a (possibly long) list of possible
        combinations of the values for each field is generated and
        fed to the format. This gives the list of files to download.

        If not all of these are expected to exist, use the argument
        `missing`

    "missing"
        (optional, str)
        If the value is "ok" or "ignore", it is ignored if
        downloading a file from `filelist` fails with an
        error code 404 ("not found").

        This option id particularly helpful with generated filelists.


    "unpack":
        (optional, str)
        How to unpack downloaded files. The default is not to unpack.

        If the value is "tif" or "false" or 'null' and the filename
        ends with '.tif', the file is taken as it is.

        If the value starts with "zip" or "unzip", a zip archife is
        expected   from which files a extracted. The files a selected
        by a `glob pattern <https://en.wikipedia.org/wiki/Glob_(programming)>`_
        (optionally including path), separated from the (un)zip keyword by
        ":", ":/", or "://".

        Example: :json:`"unpack": "zip://foo/*.tif"`

Example:

    .. code-block:: json

        "DGM10-NW": {
            "storage": "terrain",
            "assemble": "assemble_DGMxx",
            "arguments": {
                "resolution": 10,
                "host": "https://www.opengeodata.nrw.de",
                "path": "produkte/geobasis/hm/dgm1_tiff/dgm1_tiff",
                "filelist": "index.xml",
                "xmlpath": "/datasets/dataset[0]/files/file::name",
                "datapath": "",
                "CRS": "EPSG:25832"
            },
            "license": "spdx:DL-DE-ZERO-2.0",
            "notice": "none"
        },

