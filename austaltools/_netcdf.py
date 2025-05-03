"""
Module that holds untilities for manipulating netCDF4 files
"""
import collections
import glob
import logging
import os
import tempfile
import zipfile

import numpy as np
import netCDF4

try:
    from . import _storage
    from . import _tools
except ImportError:
    import _storage
    import _tools

logger = logging.getLogger(__name__)


class VariableSkeleton():
    """
    Class that can hold the same attributes
    as :class:`netCDF4.Variable` except for `group`
    so it can serve as a skeleton to add to
    a :class:`netCDF4.Dataset`
    """
    ncattr = {}
    def __init__(self,
                 name: str,
                 datatype: str,
                 dimensions: tuple = (),
                 compression: str|None = None,
                 zlib: bool = False,
                 complevel: int = 4,
                 shuffle: bool = True,
                 szip_coding: str = 'nn',
                 szip_pixels_per_block: int = 8,
                 blosc_shuffle: int = 1,
                 fletcher32: bool = False,
                 contiguous: bool = False,
                 chunksizes = None,
                 endian: str = 'native',
                 least_significant_digit = None,
                 fill_value = None,
                 chunk_cache = None):
        self.__dict__.update(locals())
        pass

    def setncattr(self, name, value):
        """
        Set the value of a variable attribute

        :param name: name of the attribute
        :type name: str

        :param value: value to set
        :type value: Any
        """
        self.ncattr[name] = value

    def getncattr(self, name):
        """
        Get the value of a variable attribute

        :param name: name of the attribute
        :type name: str

        :return value: value to set
        :rtype value: Any
        """
        return self.ncattr[name]

    def ncattrs(self):
        """
        List the names of the variable attributes set in this instance

        :param name: name of the attribute
        :type name: str

        :param value: value to set
        :type value: Any
        """
        return list(self.ncattr.keys())

def check_homhogenity(file_list, timevar = None, fail=False):
    """
    Check if all NetCDF datasets in the provided list have
    identical dimensions, attributes, variables,
    and variable attributes, except for the size of a specified dimension.

    :param file_list: List of file paths to the NetCDF datasets to check.
    :type file_list: list of str

    :param timevar: Name of the dimension variable that can vary in
      size across datasets, defaults to None.
    :type timevar: str, optional

    :param fail: If True, raises an exception when inconsistency
      is found, defaults to False.
    :type fail: bool, optional

    :return: True if all datasets are consistent; otherwise, False.
    :rtype: bool
    :raises ValueError: If `fail` is True and inconsistency is detected.
    """

    # helper function to get dimensions
    def get_dimensions(dataset):
        return {dim: (dataset.dimensions[dim].size
                      if dim != timevar else None)
                for dim in dataset.dimensions}

    # helper function to get file attributes
    def get_global_attributes(dataset):
        return {attr: dataset.getncattr(attr)
                for attr in dataset.ncattrs()}

    # helper function to get variables information
    def get_variables(dataset):
        variables = {}
        for var in dataset.variables:
            # Store attributes without the value of the time-related dimension
            variables[var] = {
                'dimensions': dataset.variables[var].dimensions,
                'attributes': dataset.variables[var].ncattrs(),
                'dtype': str(dataset.variables[var].dtype),
            }
        return variables

    # helper function to get variable information
    def get_variable_attributes(dataset, var):
        return {attr: dataset.variables[var].getncattr(attr)
                     for attr in dataset.variables[var].ncattrs()}



    ref_dataset = None
    ref_dimensions = None
    ref_global_attrs = None
    ref_variables = None
    report = []

    for fname in file_list:
        try:
            with netCDF4.Dataset(fname, 'r') as dataset:
                dimensions = get_dimensions(dataset)
                global_attrs = get_global_attributes(dataset)
                variables = get_variables(dataset)

                if ref_dataset is None:
                    # Initialize reference data
                    ref_dimensions = dimensions
                    ref_global_attrs = global_attrs
                    ref_variables = variables
                else:
                    # compare dimensions, ignoring the structure of the `timevar` dimension
                    if ref_dimensions != dimensions:
                        report.append(f"Dimension mismatch in {fname}")

                    # compare global attributes
                    if ref_global_attrs != global_attrs:
                        report.append(f"File attrib mismatch in {fname}")

                    # compare variables
                    if ref_variables != variables:
                        report.append(f"Variables mismatch in {fname}")

                    else:
                        # compare variables
                        for k, v in ref_variables.keys():
                            if (get_variable_attributes(ref_dataset, v) !=
                                    get_variable_attributes(dataset, v)):
                                report.append(f"Variables attribute "
                                              f"mismatch in {fname}, "
                                              f"attribute {v}")

        except Exception as e:
            return False, f"Error processing file {fname}: {e}"

    if len(report) > 0:
        if fail:
            raise ValueError("netCDF4 files are inconsistent:\n" +
                             "\n".join(report))
        else:
            logger.info("netCDF4 files are inconsistent")
        for x in report:
            logger.debug(x)
    return True

def copy_values(src, dst,
                replace: dict[str, str | VariableSkeleton | None] = {},
                convert: dict[str, collections.abc.Callable] = {},
                ) -> bool:
    """
    Copy values from source NetCDF dataset to destination dataset
    with optional replacement
    and conversion of variable values.

    :param src: Source NetCDF dataset.
    :type src: netCDF4.Dataset

    :param dst: Destination NetCDF dataset.
    :type dst: netCDF4.Dataset

    :param replace: Mapping of source variable names to
      destination variable names or skeletons.
    :type replace: dict[str, str | VariableSkeleton | None]

    :param convert: Mapping of source variable names to
      functions for converting data.
    :type convert: dict[str, collections.abc.Callable]

    :return: True if the operation is successful.
    :rtype: bool
    """
    logger.debug(f"copying values {os.path.basename(src.filepath())}"
                 f" -> {os.path.basename(dst.filepath())}")
    for sname in src.variables.keys():
        replacement = replace.get(sname, False)
        if replacement is None:
            logger.debug(f" ... skipping values {sname}")
        if replacement is False:
            dname = sname
        elif isinstance(replacement, VariableSkeleton):
            dname = replacement.name
        else:
            dname = replacement
        if sname not in convert:
            logger.debug(f" ... copying values {sname} -> {dname}")
            dst[dname][:] = src[sname][:]
        else:
            logger.debug(f" ... convert values {sname} -> {dname}")
            converter = np.vectorize(convert[sname])
            dst[dname][:] = converter(src[sname][:])


def add_variable(dst: netCDF4.Dataset,
                 svar: netCDF4.Variable,
                 replace: dict[str, str | VariableSkeleton | None] = {},
                 compression: str|None = None):

    """
    Add a variable to the destination NetCDF dataset,
    with support for renaming, replacing,
    and setting compression options.

    :param dst: Destination NetCDF dataset.
    :type dst: netCDF4.Dataset

    :param svar: Source NetCDF variable to add.
    :type svar: netCDF4.Variable

    :param replace:
      A dictionary that specifies variables to be replaced or removed:
        - If a variable name maps to a string,
          it is renamed.
        - If a variable name maps to a new variable object,
          it replaces the original.
        - If a variable name maps to None,
          the variable is omitted in the destination.
    :type replace: dict[str, str | VariableSkeleton | None]

    :param compression: Compression setting for the variable,
      defaults to None.
    :type compression: str, optional

    :return: True if the variable was added successfully,
      False if it already exists.
    :rtype: bool
    """
    # replace name if variable will be replaced
    replacement = replace.get(svar.name, False)
    if replacement is None:
        # skip unwanted variable
        logger.debug(f"skipping variable {svar.name}")
        return True
    elif replacement is False:
        dname = svar.name
    else:
        dname = replace[svar.name].name
        logger.debug(f" ... renaming to {dname}")

    if dname in dst.variables.keys():
        # variable already exists
        logger.debug(f" ... already exists")
        return False
    logger.debug(f"adding variable {svar.name}")

    # get properties
    cmpr = None if isinstance(
        svar.datatype,(netCDF4.VLType, netCDF4.CompoundType)
    ) else compression
    logger.debug(f" ... compression {cmpr}")
    fill = (None if '_FillValue' not in svar.ncattrs()
        else svar.getncattr('_FillValue'))
    logger.debug(f" ... fill value {fill}")
    dims = tuple([x if x not in replace else replace[x].name
            for x in svar.dimensions])
    logger.debug(f" ... dimensions: {dims}")

    # save variable definition
    dst.createVariable(dname, svar.datatype, dims,
                       compression=cmpr, fill_value=fill)
    # copy variable attributes
    if svar.name in replace:
        if isinstance(replace[svar.name], VariableSkeleton):
            sourcevar = replace[svar.name]
        else:
            # rename only
            sourcevar = svar
    else:
        sourcevar = svar
    for a in sourcevar.ncattrs():
        if a in ['_FillValue']:
            continue  # skip
        logger.debug(f" ... attribute: {a}")
        string = sourcevar.getncattr(a)
        if a == 'coordinates':
            for k, v in replace.items():
                if v is None:
                    continue
                string = string.replace(k, v.name)
        dst.variables[dname].setncattr(a, string)
    return True


def copy_structure(src, dst,
                   replace: dict[str, str | VariableSkeleton | None] = {},
                   convert: dict[str, collections.abc.Callable] = {},
                   unlimited: str| None = None,
                   compression: str|None = None,
                   copy_data: bool = False) -> None:
    """
    Copy the structure and optionally the data of a NetCDF source dataset
    to a destination dataset.

    This function facilitates the duplication of NetCDF dataset structures,
    including dimensions, variables, and global attributes.
    Users can opt to modify certain aspects, such as renaming
    variables, applying transformations to data, or changing dimensions,
    to suit specific requirements.

    :param src: The source dataset from which to copy the structure.
    :type src: netCDF4.Dataset

    :param dst: The destination dataset where the structure will be copied.
    :type dst: netCDF4.Dataset

    :param replace:
      A dictionary that specifies variables to be replaced or removed:
        - If a variable name maps to a string,
          it is renamed.
        - If a variable name maps to a new variable object,
          it replaces the original.
        - If a variable name maps to None,
          the variable is omitted in the destination.

    :type replace: dict[str, str | VariableSkeleton | None]

    :param convert: A dictionary that maps variable names to
      functions that transform their data values.
      These functions are applied to variable data during the copy.
    :type convert: dict[str, collections.abc.Callable]

    :param unlimited: The name of a dimension that should be set to
      unlimited in the destination dataset.
      If `None`, no change is made to dimension limits.
    :type unlimited: str | None

    :param compression: The compression method to apply to the copied
      variables, commonly set to `zlib`. Defaults to None
    :type compression: str | None

    :param copy_data: A boolean flag indicating whether the variable
      is copied with or without values in it.
      - If `True`, variable data is copied and transformed using `convert`.
      - If `False`, only the definition
      (dimensions, variables, attributes) is copied.

      Defaults to `False`.
    :type copy_data: bool, optional

    :raises ValueError: Raised if an attempt is made to exclude a
      mandatory dimension without proper replacement.

    """
    logger.debug(f"copying structure {os.path.basename(src.filepath())} "
                 f"-> {os.path.basename(dst.filepath())}")

    # copy global attributes
    for a in src.ncattrs():
        value = src.getncattr(a)
        dst.setncattr(a, value)

    # copy dimensions
    for k, v in src.dimensions.items():
        if replace.get(k, False) is None:
            raise ValueError(f"cannot exclude dimension {k}")
        logger.debug(f"copying dimension {k}")
        # copy only if not already in dst
        if v.isunlimited() or k == unlimited:
            size = None
        else:
            size = v.size
        # replace name if variable will be replaced
        if k in replace.keys():
            if isinstance(replace[k], VariableSkeleton):
                dname = replace[k].name
            else:
                dname = replace[k]
        else:
            dname = k
        dst.createDimension(dname, size)

    # add variables
    for sname,svar in src.variables.items():
        if replace.get(sname, False) is None:
            logger.debug(f"skipping variable {sname}")
            continue
        logger.debug(f"copying variable {sname}")
        add_variable(dst, svar, replace, compression)

    # copy variable values
    if copy_data:
        copy_values(src, dst, replace, convert)


def merge_zipped(source, destination, compression='zlib'):
    """
    Merge the files in a zipped archive downloaded from
    cds.climate.eu into one nc file.

    :param source: path of the archive file to read
    :type source: str

    :param destination: path of the destination file to create
    :type destination: str

    :param compression: (optional) compression type, defaults to `zlib`
    :type compression: str | None
    """
    source_file = os.path.abspath(source)
    logger.info("unpacking downloaded zip archive %s" % source_file)
    destination_file = os.path.abspath(destination)
    with (tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True, dir=_storage.TEMP) as td):
        with zipfile.ZipFile(source_file, 'r') as zf:
            zf.extractall(td)
        ncfiles = glob.glob(os.path.join(td, '*.nc'))
        if len(ncfiles) == 0:
            raise IOError("No files found in %s" % source)
        sources = [netCDF4.Dataset(x, 'r') for x in ncfiles]

        logger.debug("creating netcdf file %s" % destination_file)
        if os.path.exists(destination_file):
            os.remove(destination_file)
        # dst = netCDF4.Dataset(destination_file, "w")

        # replace time variable
        stime_name = 'valid_time'
        dtime_name = 'time'
        dtime_unit = 'hours since 1900-01-01'

        dtime_var = VariableSkeleton(
            dtime_name, 'd',
            dimensions=(dtime_name),
            compression=compression,
        )
        dtime_var.setncattr('long_name', dtime_name)
        dtime_var.setncattr('standard_name', dtime_name)
        dtime_var.setncattr('units', dtime_unit)
        dtime_var.setncattr('calendar', 'proleptic_gregorian')

        stimeunit = sources[0][stime_name].units
        def dtime_fun(x):
            numtime = netCDF4.num2date(x, stimeunit)
            return netCDF4.date2num(numtime, dtime_unit)

        replace = {stime_name: dtime_var}
        convert = {stime_name: dtime_fun}

        merge_files(sources, destination_file,
                    replace, convert, compression)

    #     logger.debug("copying file structure")
    #     copy_structure(sources[0], dst, replace, convert,
    #                    compression=compression, copy_data=True)
    #
    #     # copy variable values
    #     for src in sources:
    #         for sname,svar in src.variables.items():
    #             logger.debug(f"variable: {sname}")
    #             add_variable(dst, svar, replace, compression)
    #         copy_values(src, dst, replace, convert)
    #
    #     # clean up
    #     for src in sources:
    #         src.close()
    #     dst.close()
    # logger.debug("finished writing netcdf file %s" % destination_file)


def merge_files(sources: list[str], destination: str,
                replace: dict[str, str | VariableSkeleton | None] = {},
                convert: dict[str, collections.abc.Callable] = {},
                compression: str|None = None):
    """
    Merge multiple netcdf files contained in a zip archive
    into one nc file.

    :param sources: lits of paths to the files to read
    :type source: str

    :param destination: path of the destination file to create
    :type destination: str

    :param replace:
      A dictionary that specifies variables to be replaced or removed:
        - If a variable name maps to a string,
          it is renamed.
        - If a variable name maps to a new variable object,
          it replaces the original.
        - If a variable name maps to None,
          the variable is omitted in the destination.

    :type replace: dict[str, str | VariableSkeleton | None]

    :param convert: A dictionary that maps variable names to
      functions that transform their data values.
      These functions are applied to variable data during the copy.
    :type convert: dict[str, collections.abc.Callable]

    :param compression: (optional) compression type, defaults to `zlib`
    :type compression: str | None
    """

    src_list = [netCDF4.Dataset(x, 'r') for x in sources]

    logger.debug("creating netcdf file %s" % destination)
    if os.path.exists(destination):
        os.remove(destination)
    dst = netCDF4.Dataset(destination, "w")

    # copy file structure
    copy_structure(src_list[0], dst, replace, convert,
                   compression=compression, copy_data=True)

    # copy variable values
    for src in src_list[1:]:
        for sname,svar in src.variables.items():
            logger.debug(f"variable: {sname}")
            add_variable(dst, svar, replace, compression=compression)
        copy_values(src, dst, replace, convert)

    # clean up
    for src in src_list:
        src.close()
    dst.close()
    logger.debug("finished writing netcdf file %s" % destination)


def concat_time(infiles, target, timevar="time"):
    """
    Function that takes a list of input NetCDF files, each representing
    temporal slices of a dataset, and concatenates them into a single
    output file along a specified time dimension.

    :param infiles: List input files to be concatenated.
      These files should contain consistent
      structure and metadata except for the time dimension.
    :type infiles: list of str

    :param target: The path to the output file that will store the result.
    :type target: str

    :param timevar: The name of the time dimension variable used.
      It is expected that this variable indicates the
      time period covered by each file. Defaults to "time".
    :type timevar: str, optional

    :return: Returns True upon successful concatenation of all files,
      indicating the result is stored correctly.
    :rtype: bool

    :raises ValueError: If the time dimension is inconsistent
      among the input files.


    :logging: Various stages of the process are logged including:
        - The initial setup and copying of structure from the first file.
        - Updates to the time dimension during concatenation.
        - Removal of temporary files post-completion.

    :example: Usage example for three input files:
        >>> concat_time(["file1.nc", "file2.nc"], "output.nc")

    """
    compression = 'zlib'
    # get sorting order:
    in_time = []
    for infile in infiles:
        with netCDF4.Dataset(infile) as src:
            in_time.append(src[timevar][:].min())
            logger.debug(f"starting time of {infile}: {in_time[-1]}")
    sorted_infiles = [x for _, x in sorted(zip(in_time, infiles))]

    with netCDF4.Dataset(target, "w", format='NETCDF4') as dst:
        # copy fixed values from first file
        logger.debug(f"initializing output")
        with netCDF4.Dataset(sorted_infiles[0]) as src:
            logger.debug(f"initializing from "
                         f"{os.path.basename(src.filepath())}")
            copy_structure(src, dst, unlimited=timevar, copy_data=True)

        # create empty data fields
        i_time = dst.variables[timevar].size

        datavars = set(dst.variables.keys())-set(dst.dimensions.keys())
        for infile in sorted_infiles[1:]:
            with netCDF4.Dataset(infile) as src:
                logger.debug(f"adding data from "
                             f"{os.path.basename(src.filepath())}")
                # handle time first:
                logger.debug(f"appending values from {timevar}"
                             f" at position {i_time}")
                time_data = src[timevar][:]
                dst[timevar][i_time:i_time + len(time_data)] = time_data
                # then the data
                for vname in datavars:
                    logger.debug(f"copying values from {vname}"
                                 f" at position {i_time}")
                    slices = tuple(
                        slice(None)
                        if x != timevar else slice(i_time, None)
                        for x in dst.variables[vname].dimensions
                    )
                    logger.debug(str(slices))
                    dst[vname][slices] = src[vname][:]
        # remember end position
        i_time += len(dst[timevar][:])

    # clean up
    print("removing temporary files")
    for v in _tools.progress(sorted_infiles,
                             "removing files"):
        logger.debug(f" ... removing {v}")
        os.remove(v)

    return True
