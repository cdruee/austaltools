"""
Module that holds untilities for manipulating netCDF4 files
"""
import collections
import itertools
import logging
import os

if os.getenv('BUILDING_SPHINX', 'false') == 'false':
    import netCDF4
    import numpy as np
else:
    from ._mock import netCDF4


try:
    from . import _storage
    from . import _tools
except ImportError:
    import _storage
    import _tools

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------

class VariableSkeleton():
    """
    Class that can hold the same attributes
    as :class:`netCDF4.Variable` except for `group`
    so it can serve as a skeleton to add to
    a :class:`netCDF4.Dataset`
    """
    ncattr = {}
    name= None

    def __init__(self,
                 name: str,
                 datatype: str,
                 dimensions: tuple = (),
                 compression: str | None = None,
                 zlib: bool = False,
                 complevel: int = 4,
                 shuffle: bool = True,
                 szip_coding: str = 'nn',
                 szip_pixels_per_block: int = 8,
                 blosc_shuffle: int = 1,
                 fletcher32: bool = False,
                 contiguous: bool = False,
                 chunksizes=None,
                 endian: str = 'native',
                 least_significant_digit=None,
                 fill_value=None,
                 chunk_cache=None):
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

# -------------------------------------------------------------------------

def get_dimensions(dataset: netCDF4.Dataset,
                   timevar: str | None = None) -> dict:
    """
    Helper function to get dimensions of a dataset

    :param dataset: dataset
    :type dataset: netCDF4.Dataset
    :param timevar: name of time variable (to be excluded)
    :type timevar: str, optional
    :return: dataset dimension names and sizes
    :rtype: dict[str, int]
    """
    return {dim: (dataset.dimensions[dim].size
                  if dim != timevar else None)
            for dim in dataset.dimensions}

# -------------------------------------------------------------------------

def get_global_attributes(dataset):
    """
    Helper function to get file attributes of a dataset

    :param dataset: dataset
    :type dataset: netCDF4.Dataset
    :return: dataset attribute names and values
    :rtype: dict[str, str]
    """
    return {attr: dataset.getncattr(attr)
            for attr in dataset.ncattrs()}

# -------------------------------------------------------------------------

def get_variables(dataset):
    """
    Helper function to get variables information of a dataset

    :param dataset: dataset
    :type dataset: netCDF4.Dataset
    :return: dataset variable names and information values:
        - dimensions: the dimensions of the variable
        - attributes: names of the attributes of the variable
        - dtype: data type
    :rtype: dict[dict[str, str|dict]]
    """
    variables = {}
    for var in dataset.variables:
        # Store attributes without the value of the time-related dimension
        variables[var] = {
            'dimensions': dataset.variables[var].dimensions,
            'attributes': dataset.variables[var].ncattrs(),
            'dtype': str(dataset.variables[var].dtype),
        }
    return variables

# -------------------------------------------------------------------------

def get_variable_attributes(dataset, var):
    """
    Helper function to get the attributes of variable of a dataset

    :param dataset: dataset
    :type dataset: netCDF4.Dataset
    :param var: variable name
    :type var: str
    :return: dataset variable names and information values:
        - dimensions: the dimensions of the variable
        - attributes: names of the attributes of the variable
        - dtype: data type
    :rtype: dict[dict[str, str|dict]]
    """
    return {attr: dataset.variables[var].getncattr(attr)
            for attr in dataset.variables[var].ncattrs()}

# -------------------------------------------------------------------------

def check_homhogenity(file_list, timevar=None, fail=False):
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

    ref_dataset = None
    ref_dimensions = None
    ref_global_attrs = None
    ref_variables = None
    report = []

    for fname in file_list:
        try:
            with netCDF4.Dataset(fname, 'r') as dataset:
                dimensions = get_dimensions(dataset, timevar)
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

# -------------------------------------------------------------------------

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
            # dummy converter, does nothing
            def convert_fun(x):
                return x
        else:
            logger.debug(f" ... convert values {sname} -> {dname}")
            convert_fun = convert[sname]
        converter = np.vectorize(convert_fun)

        # copy in chunks
        MEMORY_CAP = 1073741824 # 1GB
        # we cannot use the numpy methods of src[sname][:]
        # sinc this makes numpy allocate memory for the whole array
        shape = [x.size for x in src.variables[sname].get_dims()]
        if len(shape) == 0:
            slices_list = [0]
        else:
            slices_list = []
            longest_axis = np.argmax(shape)
            longest_len = shape[longest_axis]
            n_cells = int(np.prod(shape))
            # float64 = 8 bytes
            n_chunks = int(np.ceil((n_cells * 8) / MEMORY_CAP))
            chunk_len = int(np.floor(longest_len / n_chunks))
            borders = list(np.arange(0, longest_len, chunk_len))
            for i,b_lo in enumerate(borders):
                b_hi = (borders + [longest_len])[i + 1]
                slices = tuple(
                    slice(None)
                    if axis != longest_axis else slice(b_lo, b_hi)
                    for axis in range(len(shape))
                )
                slices_list.append(slices)
        for slices in slices_list:
            #logger.debug(str(slices))
            dst[dname][slices] = converter(src[sname][slices])

# -------------------------------------------------------------------------

def add_variable(dst: netCDF4.Dataset,
                 svar: netCDF4.Variable,
                 replace: dict[str, str | VariableSkeleton | None] = {},
                 compression: str | None = None):
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
        svar.datatype, (netCDF4.VLType, netCDF4.CompoundType)
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

# -------------------------------------------------------------------------

def timeconverter(old_unit, new_unit):
    def dtime_fun(x):
        numtime = netCDF4.num2date(x, old_unit)
        return netCDF4.date2num(numtime, new_unit)
    return dtime_fun

# -------------------------------------------------------------------------

def replace_cds_valid_time(compression:str):
    # replace time variable
    stime_name = 'valid_time'
    stime_unit = 'seconds since 1970-01-01'
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


    def dtime_fun(x):
        numtime = netCDF4.num2date(x, stime_unit)
        return netCDF4.date2num(numtime, dtime_unit)


    replace = {stime_name: dtime_var}
    convert = {stime_name: dtime_fun}

    return replace, convert

# -------------------------------------------------------------------------

def copy_structure(src, dst,
                   replace: dict[str, str | VariableSkeleton | None] = {},
                   convert: dict[str, collections.abc.Callable] = {},
                   resize: dict[str, int | None] = {},
                   compression: str | None = None,
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

    :param resize: Dictionary indicating if the copy should
      have a different size for one or more dimensions.
      In case a dimension also appears in `replace`, its name
      *before* replacement must be given here.
      To make a dimension unlimited (only one per file),
      the lenght must be changed to `None`.
      If empty, no change is made to dimension limits.
    :type resize: dict[str, int | None]

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

    # check resize argument
    for x in resize.keys():
        if not x in src.dimensions.keys():
            ValueError(f"resize name {x} is not a dimension")
    sim_dim =  src.dimensions.copy()
    for k, v in resize.items():
        sim_dim[k] = v
    if sum(x is None for x in sim_dim) > 1:
        ValueError(f"resize can make onle one dimension unlimited")
    del sim_dim

    # copy dimensions
    for k, v in src.dimensions.items():
        if replace.get(k, False) is None:
            raise ValueError(f"cannot exclude dimension {k}")
        logger.debug(f"copying dimension {k}")
        # set size
        if k in resize.keys():
            size = resize[k]
        elif v.isunlimited():
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
    for sname, svar in src.variables.items():
        if replace.get(sname, False) is None:
            logger.debug(f"skipping variable {sname}")
            continue
        logger.debug(f"copying variable {sname}")
        add_variable(dst, svar, replace, compression)

    # copy variable values
    if copy_data:
        copy_values(src, dst, replace, convert)

# -------------------------------------------------------------------------

def merge_variables(infiles: list[str],
                    target: str,
                    replace: dict[str, str | VariableSkeleton | None] = {},
                    convert: dict[str, collections.abc.Callable] = {},
                    compression: str | None = None,
                    remove_source: bool = True):
    """
    Merge multiple netcdf files contained in a zip archive
    into one nc file.

    :param infiles: List of paths to the files to read
    :type infiles: str

    :param target: path of the destination file to create
    :type target: str

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

    src_list = [netCDF4.Dataset(x, 'r') for x in infiles]

    logger.debug("creating netcdf file %s" % target)
    if os.path.exists(target):
        os.remove(target)
    dst = netCDF4.Dataset(target, "w")

    # copy file structure
    copy_structure(src_list[0], dst,
                   replace=replace, convert=convert,
                   compression=compression, copy_data=True)

    # copy variable values
    for src in src_list[1:]:
        for sname, svar in src.variables.items():
            logger.debug(f"variable: {sname}")
            add_variable(dst, svar,
                         replace=replace, compression=compression)
        copy_values(src, dst, replace=replace, convert=convert)

    # clean up
    for src in src_list:
        src.close()
    if remove_source:
        for f in infiles:
            os.remove(f)
    dst.close()
    logger.debug("finished writing netcdf file %s" % target)

# -------------------------------------------------------------------------

def merge_time(infiles: list | str, target: str,
               timevar: str = "time",
               compression: str | None = None,
               allow_duplicates: bool = False,
               remove_source: bool = True):
    """
    Function that takes a list of input NetCDF files, each representing
    temporal slices of a dataset, and merges them into a single
    output file along a specified time dimension.

    The time span covered by the input files can be overlpping and
    input files do not need to be sorted but the must not contain
    multiple entries for one time.

    The check for duplicate times occuring in the input files can be
    disabled by `allow_dulicates` but when this option is chosen,
    it is not defined, which of the respective input records
    appears in the output file.

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
        >>> merge_time(["file1.nc", "file2.nc"], "output.nc")

    """
    # get sorting order:
    in_time = []
    in_fid = []
    in_idx = []
    for fid, infile in enumerate(infiles):
        with netCDF4.Dataset(infile) as src:
            in_time += src[timevar][:].tolist()
            in_fid += [fid]*len(src[timevar])
            in_idx += [i for i in range(len(src[timevar]))]
            logger.debug(f"starting time of {infile}: {in_time[0]}")
    sorted_time, sorted_fid, sorted_idx = zip(
        *sorted(zip(in_time,in_fid, in_idx))
    )
    sorted_out = [i for i in range(len(sorted_time))]
    # check for duplicate times.
    if len(sorted_time) != len(set(sorted_time)):
        if not allow_duplicates:
            raise ValueError(f"duplicate times found in infiles")

    with netCDF4.Dataset(target, "w", format='NETCDF4') as dst:
        # copy fixed values from the first file
        logger.debug(f"initializing output")
        with netCDF4.Dataset(infiles[0]) as src:
            logger.debug(f"initializing from "
                         f"{os.path.basename(src.filepath())}")
            copy_structure(src, dst,
                           resize={timevar:None},
                           compression=compression,
                           copy_data=False)

        # create empty data fields
        dst.variables[timevar][:] = sorted_time

        for fid, infile in enumerate(infiles):
            # get positions where to put the data
            src_index = [i for i,j in zip(sorted_idx, sorted_fid)
                         if j == fid]
            dst_index = [i for i,j in zip(sorted_out, sorted_fid)
                         if j == fid]
            # copy values over
            with netCDF4.Dataset(infile) as src:
                logger.debug(f"adding data from "
                             f"{os.path.basename(src.filepath())}")
                for vname in dst.variables.keys():
                    if not isinstance(dst.variables[vname].datatype,
                            (netCDF4.VLType, netCDF4.CompoundType)):
                        # closed expression for number types (faster)
                        logger.debug(f"block-copying values from {vname}")
                        src_slices = tuple(
                            slice(None) if x != timevar else src_index
                            for x in src.variables[vname].dimensions
                        )
                        dst_slices = tuple(
                            slice(None) if x != timevar else dst_index
                            for x in dst.variables[vname].dimensions
                        )
                        #logger.debug(str(src_slices))
                        #logger.debug(str(dst_slices))
                        dst[vname][dst_slices] = src[vname][src_slices]
                    else:
                        logger.debug(f"cell-copying values from {vname}")
                        # iterate explicitly for variable-length types
                        # way slower but does not raise error
                        src_slices = [
                            [i for i in range(src.dimensions[x].size)]
                            for x in src.variables[vname].dimensions
                        ]
                        dst_slices = [
                            [i for i in range(src.dimensions[x].size)]
                            if x != timevar else dst_index
                            for x in src.variables[vname].dimensions
                        ]
                        for prod in zip(
                                itertools.product(*src_slices),
                                itertools.product(*dst_slices)):
                            src_cell, dst_cell = (list(x) for x in prod)
                            #Python >= 3.11 :
                            # dst[vname][*dst_cell] = src[vname][*src_cell]
                            # Python <= 3.10 :
                            dst[vname][tuple(dst_cell)] = src[vname][
                                tuple(src_cell)]

    # clean up
    if remove_source:
        logger.debug("removing temporary files")
        for v in _tools.progress(infiles,
                                 "removing files"):
            logger.debug(f" ... removing {v}")
            os.remove(v)

    return True

# -------------------------------------------------------------------------

def subset_xy(infile, target,
              xmin: int | float | None = None,
              xmax: int | float | None = None,
              ymin: int | float | None = None,
              ymax: int | float | None = None,
              tmin: int | float | None = None,
              tmax: int | float | None = None,
              xvar: str | None = None, yvar: str | None = None,
              timevar: str | None = None,
              by_index: bool = False,
              replace: dict = {},
              convert: dict = {},
              compression: str | None = None,
              ):
    with (netCDF4.Dataset(infile) as src,
          netCDF4.Dataset(target, "w", format='NETCDF4') as dst):
        logger.debug(f"subsetting data from "
                     f"{os.path.basename(src.filepath())}"
                     f" to "
                     f"{os.path.basename(dst.filepath())}")

        # determine the index variables
        dimensions = list(get_dimensions(src).keys())

        if xvar is None:
            candidates = [x for x in dimensions
                          if x.lower() in ['x', 'lon', 'longitude']]
            if len(candidates) > 0:
                xvar = candidates[0]
                logger.info(f"subsetting x variable {xvar}")
            else:
                raise ValueError(f"cannot determine `xvar`")
        elif xvar not in dimensions:
            raise ValueError(f"{xvar} not in dimensions")

        if yvar is None:
            candidates = [x for x in dimensions
                          if x.lower() in ['y', 'lat', 'latitude']]
            if len(candidates) > 0:
                yvar = candidates[0]
                logger.info(f"subsetting y variable {yvar}")
            else:
                raise ValueError(f"cannot determine `xvar`")
        elif yvar not in dimensions:
            raise ValueError(f"{yvar} not in dimensions")

        if timevar is None:
            candidates = [x for x in dimensions
                          if x.lower() in ['time', 'valid_time']]
            if len(candidates) > 0:
                timevar = candidates[0]
                logger.info(f"subsetting time variable {timevar}")
            else:
                raise ValueError(f"cannot determine `timevar`")
        elif timevar not in dimensions:
            raise ValueError(f"{timevar} not in dimensions")


        if by_index:
            imin = xmin if xmin is not None else 0
            imax = xmax if xmax is not None else src[xvar].size
            jmin = ymin if ymin is not None else 0
            jmax = ymax if ymax is not None else src[yvar].size
            nmin = tmin if tmin is not None else 0
            nmax = tmax if tmax is not None else src[timevar].size
        else:
            imin = (min([i for i,x in enumerate(src[xvar][:])
                         if x >= xmin])
                    if xmin is not None else 0)
            imax = (max([i + 1 for i,x in enumerate(src[xvar][:])
                         if x <= xmax])
                    if xmax is not None else src[xvar].size)
            jmin = (min([j for j,y in enumerate(src[yvar][:])
                         if y >= ymin])
                    if ymin is not None else 0)
            jmax = (max([j + 1 for j,y in enumerate(src[yvar][:])
                         if y <= ymax])
                    if ymax is not None else src[yvar].size)
            nmin = (min([n for n,t in enumerate(src[timevar][:])
                         if t >= tmin])
                    if tmin is not None else 0)
            nmax = (max([n + 1 for n,t in enumerate(src[timevar][:])
                         if t <= tmax])
                    if tmax is not None else src[timevar].size)

        resize = {
            xvar: imax - imin,
            yvar: jmax - jmin,
        }
        if not src.dimensions[timevar].isunlimited():
            resize[timevar] = nmax - nmin

        logger.debug(f"copying structure ...")
        copy_structure(src, dst, resize=resize,
                       compression=compression, copy_data=False)

        logger.debug(f"copying values ...")
        # translate incices into slices
        dim_slice = {d:slice(None) for d in dimensions
                     if d not in[xvar, yvar, timevar]}
        dim_slice[xvar] = slice(imin, imax)
        dim_slice[yvar] = slice(jmin, jmax)
        dim_slice[timevar] = slice(nmin, nmax)
        # make sure dimensions are copied first
        # this adjusts the array sizes
        for sname in list(dst.variables.keys()):
            logger.debug(f" ... variable {sname}")
            # determine subset to copy
            slices = tuple([dim_slice[d]
                            for d in src.variables[sname].dimensions])
            # determine if var is to replace, rename or discard
            replacement = replace.get(sname, False)
            if replacement is None:
                logger.debug(f" ... skipping values {sname}")
            elif replacement is False:
                # i.e. sname not in replace dict
                dname = sname
            elif isinstance(replacement, VariableSkeleton):
                # replace
                dname = replacement.name
            else:
                # rename
                dname = replacement
            # determine if var shall be converted
            if sname not in convert:
                logger.debug(f" ... copying values {sname} -> {dname}")
                dst[dname][:] = src[sname][slices]
            else:
                logger.debug(f" ... convert values {sname} -> {dname}")
                converter = np.vectorize(convert[sname])
                dst[dname][:] = converter(src[sname][slices])

