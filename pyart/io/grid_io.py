"""
pyart.io.grid_io
================

Reading and writing Grid objects.

.. autosummary::
    :toctree: generated/

    read_grid
    write_grid
    read_legacy_grid
    _make_coordinatesystem_dict

"""

import warnings

import numpy as np
import netCDF4
import datetime

from ..core.grid import Grid
from .cfradial import _ncvar_to_dict, _create_ncvar
from .common import _test_arguments


def read_grid(filename, exclude_fields=None, **kwargs):
    """
    Read a netCDF grid file

    Parameters
    ----------
    filename : str
        Filename of NetCDF grid file to read.

    Other Parameters
    ----------------
    exclude_fields : list
        A list of fields to exclude from the grid object.

    Returns
    -------
    grid : Grid
        Grid object containing gridded data.

    """
    # test for non empty kwargs
    _test_arguments(kwargs)

    if exclude_fields is None:
        exclude_fields = []

    reserved_variables = [
        'time', 'x', 'y', 'z',
        'origin_latitude', 'origin_longitude', 'origin_altitude',
        'point_x', 'point_y', 'point_z', 'projection',
        'point_latitude', 'point_longitude', 'point_altitude',
        'radar_latitude', 'radar_longitude', 'radar_altitude',
        'radar_name', 'radar_time', 'base_time', 'time_offset',
        'ProjectionCoordinateSystem']

    dset = netCDF4.Dataset(filename, mode='r')

    # metadata
    metadata = dict([(k, getattr(dset, k)) for k in dset.ncattrs()])

    # required reserved variables
    time = _ncvar_to_dict(dset.variables['time'])
    origin_latitude = _ncvar_to_dict(dset.variables['origin_latitude'])
    origin_longitude = _ncvar_to_dict(dset.variables['origin_longitude'])
    origin_altitude = _ncvar_to_dict(dset.variables['origin_altitude'])
    x = _ncvar_to_dict(dset.variables['x'])
    y = _ncvar_to_dict(dset.variables['y'])
    z = _ncvar_to_dict(dset.variables['z'])

    # projection
    projection = _ncvar_to_dict(dset.variables['projection'])
    projection.pop('data')
    # map _include_lon_0_lat_0 key to bool type
    if '_include_lon_0_lat_0' in projection:
        v = projection['_include_lon_0_lat_0']
        projection['_include_lon_0_lat_0'] = {'true': True, 'false': False}[v]

    # read in the fields
    fields = {}

    # fields in the file has a shape of (1, nz, ny, nx) with the leading 1
    # indicating time but should shaped (nz, ny, nx) in the Grid object
    field_shape = tuple([len(dset.dimensions[d]) for d in ['z', 'y', 'x']])
    field_shape_with_time = (1, ) + field_shape

    # check all non-reserved variables, those with the correct shape
    # are added to the field dictionary, if a wrong sized field is
    # detected a warning is raised
    field_keys = [k for k in dset.variables if k not in reserved_variables]
    for field in field_keys:
        if field in exclude_fields:
            continue
        field_dic = _ncvar_to_dict(dset.variables[field])
        if field_dic['data'].shape == field_shape_with_time:
            field_dic['data'].shape = field_shape
            fields[field] = field_dic
        else:
            bad_shape = field_dic['data'].shape
            warnings.warn('Field %s skipped due to incorrect shape' % (field))

    # radar_ variables
    if 'radar_latitude' in dset.variables:
        radar_latitude = _ncvar_to_dict(dset.variables['radar_latitude'])
    else:
        radar_latitude = None

    if 'radar_longitude' in dset.variables:
        radar_longitude = _ncvar_to_dict(dset.variables['radar_longitude'])
    else:
        radar_longitude = None

    if 'radar_altitude' in dset.variables:
        radar_altitude = _ncvar_to_dict(dset.variables['radar_altitude'])
    else:
        radar_altitude = None

    if 'radar_name' in dset.variables:
        radar_name = _ncvar_to_dict(dset.variables['radar_name'])
    else:
        radar_name = None

    if 'radar_time' in dset.variables:
        radar_time = _ncvar_to_dict(dset.variables['radar_time'])
    else:
        radar_time = None

    dset.close()

    return Grid(
        time, fields, metadata,
        origin_latitude, origin_longitude, origin_altitude, x, y, z,
        projection=projection,
        radar_latitude=radar_latitude, radar_longitude=radar_longitude,
        radar_altitude=radar_altitude, radar_name=radar_name,
        radar_time=radar_time)


def write_grid(filename, grid, format='NETCDF4',
               write_proj_coord_sys=True, proj_coord_sys=None,
               arm_time_variables=False,
               write_point_x_y_z=False, write_point_lon_lat_alt=False):
    """
    Write a Grid object to a CF-1.5 and ARM standard netcdf file

    To control how the netCDF variables are created, set any of the following
    keys in the grid attribute dictionaries.

        * _Zlib
        * _DeflateLevel
        * _Shuffle
        * _Fletcher32
        * _Continguous
        * _ChunkSizes
        * _Endianness
        * _Least_significant_digit
        * _FillValue

    See the netCDF4 documentation for details on these settings.

    Parameters
    ----------
    filename : str
        Filename to save grid to.
    grid : Grid
        Grid object to write.
    format : str, optional
        NetCDF format, one of 'NETCDF4', 'NETCDF4_CLASSIC',
        'NETCDF3_CLASSIC' or 'NETCDF3_64BIT'. See netCDF4 documentation for
        details.
    write_proj_coord_sys bool, optional
        True to write a information on the coordinate transform used in the map
        projection to the ProjectionCoordinateSystem variable following the CDM
        Object Model.  The resulting file should be intepreted as containing
        geographic grids by tools which use the Java NetCDF library
        (THREDDS, toolsUI, etc).
    proj_coord_sys : dict or None, optional
        Dictionary of parameters which will be written to the
        ProjectionCoordinateSystem NetCDF variable if write_proj_coord_sys is
        True.  A value of None will attempt to generate an appropiate
        dictionary by examining the projection attribute of the grid object.
        If the projection is not understood a warnings will be issued.
    arm_time_variables : bool, optional
        True to write the ARM standard time variables base_time and
        time_offset. False will not write these variables.
    write_point_x_y_z : bool, optional
        True to include the point_x, point_y and point_z variables in the
        written file, False will not write these variables.
    write_point_lon_lat_alt : bool, optional
        True to include the point_longitude, point_latitude and point_altitude
        variables in the written file, False will not write these variables.

    """
    dset = netCDF4.Dataset(filename, mode='w', format=format)

    # create dimensions
    dset.createDimension('time', None)
    dset.createDimension('z', grid.nz)
    dset.createDimension('y', grid.ny)
    dset.createDimension('x', grid.nx)
    if grid.nradar != 0:
        dset.createDimension('nradar', grid.nradar)
        if grid.radar_name is not None:
            nradar_str_length = len(grid.radar_name['data'][0])
            dset.createDimension('nradar_str_length', nradar_str_length)

    # required variables
    _create_ncvar(grid.time, dset, 'time', ('time', ))
    _create_ncvar(grid.x, dset, 'x', ('x', ))
    _create_ncvar(grid.y, dset, 'y', ('y', ))
    _create_ncvar(grid.z, dset, 'z', ('z', ))
    _create_ncvar(grid.origin_latitude, dset, 'origin_latitude', ('time', ))
    _create_ncvar(grid.origin_longitude, dset, 'origin_longitude', ('time', ))
    _create_ncvar(grid.origin_altitude, dset, 'origin_altitude', ('time', ))

    # write the projection dictionary as a scalar
    projection = grid.projection.copy()
    projection['data'] = np.array(1, dtype='int32')
    # NetCDF does not support boolean attribute, covert to string
    if '_include_lon_0_lat_0' in projection:
        include = projection['_include_lon_0_lat_0']
        projection['_include_lon_0_lat_0'] = ['false', 'true'][include]
    _create_ncvar(projection, dset, 'projection', ())

    # set the default projection coordinate system if requested
    if write_proj_coord_sys:
        if proj_coord_sys is None:
            # determine coordinate system automatically
            proj_coord_sys = _make_coordinatesystem_dict(grid)

        if proj_coord_sys is None:
            warnings.warn(
                'Cannot determine ProjectionCoordinateSystem parameter for ' +
                'the given projection, the file will not be written ' +
                ' without this information')

        else:
            proj_coord_sys['data'] = np.array(1, dtype='int32')
            _create_ncvar(
                proj_coord_sys, dset, 'ProjectionCoordinateSystem', ())

    # radar_ attributes
    radar_attr_names = [
        'radar_latitude', 'radar_longitude', 'radar_altitude', 'radar_time']
    for attr_name in radar_attr_names:
        attr = getattr(grid, attr_name)
        if attr is not None:
            _create_ncvar(attr, dset, attr_name, ('nradar', ))

    if grid.radar_name is not None:
        _create_ncvar(grid.radar_name, dset, 'radar_name',
                      ('nradar', 'nradar_str_length'))

    # create ARM time variables base_time and time_offset, if requested
    if arm_time_variables:
        time = grid.time
        dt = netCDF4.num2date(time['data'][0], time['units'])
        td = dt - datetime.datetime.utcfromtimestamp(0)
        td = td.seconds + td.days * 24 * 3600

        base_time = {
            'data': np.array([td], dtype=np.int32),
            'string': dt.strftime('%d-%b-%Y,%H:%M:%S GMT'),
            'units': 'seconds since 1970-1-1 0:00:00 0:00',
            'ancillary_variables': 'time_offset',
            'long_name': 'Base time in Epoch',
        }
        _create_ncvar(base_time, dset, 'base_time', ())

        time_offset = {
            'data': np.array(time['data'], dtype=np.float64),
            'long_name': 'Time offset from base_time',
            'units': time['units'].replace('T', ' ').replace('Z', ''),
            'ancillary_variables': 'time_offset',
            'calendar': 'gregorian',
        }
        _create_ncvar(time_offset, dset, 'time_offset', ('time', ))

    # optionally write point_ variables
    if write_point_x_y_z:
        _create_ncvar(grid.point_x, dset, 'point_x', ('z', 'x', 'y'))
        _create_ncvar(grid.point_y, dset, 'point_y', ('z', 'x', 'y'))
        _create_ncvar(grid.point_z, dset, 'point_z', ('z', 'x', 'y'))
    if write_point_lon_lat_alt:
        dims = ('z', 'y', 'x')
        _create_ncvar(grid.point_latitude, dset, 'point_latitude', dims)
        _create_ncvar(grid.point_longitude, dset, 'point_longitude', dims)
        _create_ncvar(grid.point_altitude, dset, 'point_altitude', dims)

    # field variables
    for field, field_dic in grid.fields.items():
        # append 1, to the shape of all data to indicate the time var.
        field_dic['data'].shape = (1, ) + field_dic['data'].shape
        _create_ncvar(field_dic, dset, field, ('time', 'z', 'y', 'x'))
        field_dic['data'].shape = field_dic['data'].shape[1:]

    # metadata
    for k, v in grid.metadata.items():
        setattr(dset, k, v)

    # Add Conventions if not already present
    if 'Conventions' not in dset.ncattrs():
        dset.setncattr('Conventions', 'PyART_GRID-1.1')

    dset.close()
    return


def _make_coordinatesystem_dict(grid):
    """
    Return a dictionary containing parameters for a coordinate transform.

    Examine the grid projection attribute and other attributes and
    return a dictionary containing parameters which can be written to a netCDF
    variable to specify a Horizontal coordinate transform recognized by
    Unidata's CDM. Return None when the projection defined in the grid
    cannot be mapped to a CDM coordinate tranform.
    """
    projection = grid.projection
    origin_latitude = grid.origin_latitude['data'][0]
    origin_longitude = grid.origin_longitude['data'][0]
    cdm_transform = {
        'latitude_of_projection_origin': origin_latitude,
        'longitude_of_projection_origin': origin_longitude,
        '_CoordinateTransformType': 'Projection',
        '_CoordinateAxes': 'x y z time',
        '_CoordinateAxesTypes': 'GeoX GeoY Height Time',
    }

    if projection['proj'] == 'ortho':
        cdm_transform['grid_mapping_name'] = 'orthographic'

    elif projection['proj'] == 'laea':
        cdm_transform['grid_mapping_name'] = 'lambert_azimuthal_equal_area'

    elif projection['proj'] in ['aeqd', 'pyart_aeqd']:
        cdm_transform['grid_mapping_name'] = 'azimuthal_equidistant'
        # CDM uses a ellipsoid where as PyProj uses a sphere by default,
        # therefore there will be slight differences in these transforms
        cdm_transform['semi_major_axis'] = 6370997.0
        cdm_transform['inverse_flattening'] = 298.25  # proj uses a sphere
        cdm_transform['longitude_of_prime_meridian'] = 0.0
        cdm_transform['false_easting'] = 0.0
        cdm_transform['false_northing'] = 0.0

    elif projection['proj'] == 'tmerc':
        cdm_transform['grid_mapping_name'] = 'transverse_mercator'
        cdm_transform['longitude_of_central_meridian'] = origin_longitude
        cdm_transform['scale_factor_at_central_meridian'] = 1.00

    elif projection['proj'] == 'lcc':
        cdm_transform['grid_mapping_name'] = 'lambert_conformal_conic'
        cdm_transform['standard_parallel'] = origin_latitude
        cdm_transform['longitude_of_central_meridian'] = origin_longitude

    elif projection['proj'] == 'aea':
        cdm_transform['grid_mapping_name'] = 'albers_conical_equal_area'
        cdm_transform['standard_parallel'] = origin_latitude
        cdm_transform['longitude_of_central_meridian'] = origin_longitude

    elif projection['proj'] == 'stere':
        cdm_transform['grid_mapping_name'] = 'stereographic'
        cdm_transform['scale_factor_at_projection_origin'] = 1.00

    elif projection['proj'] in ['npstere', 'spstere']:
        cdm_transform['grid_mapping_name'] = 'polar_stereographic'
        cdm_transform['standard_parallel'] = origin_latitude

    # 'cea' may be able to map to 'lambert_cylindrical_equal_area' and
    # 'merc' to 'mercator' but both projections seems to always be
    # centered at the equator regardless of the value of the
    # standard_parallel parameter
    else:
        cdm_transform = None

    return cdm_transform


def read_legacy_grid(filename, exclude_fields=None, **kwargs):
    """
    Read a legacy netCDF grid file.

    Legacy files were produced by Py-ART version 1.5 and before.

    Parameters
    ----------
    filename : str
        Filename of NetCDF grid file to read.

    Other Parameters
    ----------------
    exclude_fields : list
        A list of fields to exclude from the grid object.

    Returns
    -------
    grid : Grid
        Grid object containing gridded data.

    """
    warnings.warn(
        "read_legacy_grid is depreciated and will be removed in a future " +
        "version of Py-ART", DeprecationWarning)
    # test for non empty kwargs
    _test_arguments(kwargs)

    if exclude_fields is None:
        exclude_fields = []

    ncobj = netCDF4.Dataset(filename, mode='r')

    # metadata
    metadata = dict([(k, getattr(ncobj, k)) for k in ncobj.ncattrs()])

    # axes
    axes_keys = ['time', 'time_start', 'time_end', 'base_time',
                 'time_offset', 'z_disp', 'y_disp', 'x_disp',
                 'alt', 'lat', 'lon', 'z', 'lev', 'y', 'x']
    axes = dict((k, _ncvar_to_dict(ncobj.variables[k])) for k in axes_keys
                if k in ncobj.variables)

    # read in the fields
    # determine the correct shape of the fields
    # ARM standard requires the left-most dimension to be time, so the shape
    # of the fields in the file is (1, nz, ny, nx) but the field data should
    # be shaped (nz, ny, nx) in the Grid object
    dim_keys = ['nz', 'ny', 'nx', 'z', 'y', 'x']
    field_shape = tuple([len(ncobj.dimensions[k]) for k in dim_keys
                         if k in ncobj.dimensions])
    field_shape_with_time = (1, ) + field_shape

    # check all non-axes variables, those with the correct shape
    # are added to the field dictionary, if a wrong sized field is
    # detected a warning is raised
    field_keys = [k for k in ncobj.variables if k not in axes_keys and
                  k not in exclude_fields]
    fields = {}
    for field in field_keys:
        field_dic = _ncvar_to_dict(ncobj.variables[field])
        if field_dic['data'].shape == field_shape_with_time:
            field_dic['data'].shape = field_shape
            fields[field] = field_dic
        else:
            bad_shape = field_dic['data'].shape
            warn('Field %s skipped due to incorrect shape' % (field))

    ncobj.close()
    return Grid.from_legacy_parameters(fields, axes, metadata)
