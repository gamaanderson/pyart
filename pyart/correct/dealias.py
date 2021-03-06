"""
pyart.correct.dealias
=====================

Front end to the University of Washington 4DD code for Doppler dealiasing.

.. autosummary::
    :toctree: generated/

    dealias_fourdd
    find_time_in_interp_sonde
    _create_rsl_volume

"""

import numpy as np

from ..config import get_field_name, get_fillvalue, get_metadata
try:
    from ..io import _rsl_interface
    from . import _fourdd_interface
    _FOURDD_AVAILABLE = True
except ImportError:
    _FOURDD_AVAILABLE = False
from ._common_dealias import _parse_gatefilter
from ..util import datetime_utils
from ..exceptions import MissingOptionalDependency


def dealias_fourdd(radar, last_radar=None, sounding_heights=None,
                   sounding_wind_speeds=None, sounding_wind_direction=None,
                   gatefilter=False, filt=1, rsl_badval=131072.0,
                   keep_original=False,
                   vel_field=None, corr_vel_field=None, last_vel_field=None,
                   debug=False, max_shear=0.05, sign=1,
                   **kwargs):
    """
    Dealias Doppler velocities using the 4DD algorithm.

    Dealias the Doppler velocities field using the University of Washington
    4DD algorithm utilizing information from a previous volume scan and/or
    sounding data. Either last_radar or sounding_heights,
    sounding_wind_speeds and sounding_wind_direction must be provided.
    For best results provide both a previous volume scan and sounding data.
    Radar and last_radar must contain the same number of rays per sweep.

    Additional arguments are passed to
    :py:func:`_fourdd_interface.fourdd_dealias`.
    These can be used to fine tune the behavior of the FourDD algorithm.
    See the documentation of Other Parameters for details.  For the default
    values of these parameters see the documentation of
    :py:func:`_fourdd_interface.fourdd_dealias`.

    Parameters
    ----------
    radar : Radar
        Radar object to use for dealiasing.  Must have a Nyquist defined in
        the instrument_parameters attribute and have a
        reflectivity_horizontal and mean_doppler_velocity fields.
    last_radar : Radar, optional
        The previous radar volume, which has been successfully
        dealiased. Using a previous volume as an initial condition can
        greatly improve the dealiasing, and represents the final dimension
        in the 4DD algorithm.
    sounding_heights : ndarray, optional
        Sounding heights is meters above mean sea level.  If altitude
        attribute of the radar object if reference against something other
        than mean sea level then this parameter should also be referenced in
        that manner.
    sounding_wind_speeds : ndarray, optional
        Sounding wind speeds in m/s.
    sounding_wind_direction : ndarray, optional
        Sounding wind directions in degrees.

    Other Parameters
    ----------------
    gatefilter : GateFilter, optional.
        A GateFilter instance which specifies which gates should be
        ignored when performing velocity dealiasing.  A value of None will
        create this filter from the radar moments using any additional
        arguments by passing them to :py:func:`moment_based_gate_filter`. The
        default value assumes all gates are valid.
    filt : int, optional
        Flag controlling Bergen and Albers filter, 1 = yes, 0 = no.
    rsl_badval : float, optional
        Value which represents a bad value in RSL.
    keep_original : bool, optional
        True to keep original doppler velocity values when the dealiasing
        procedure fails, otherwise these gates will be masked.  NaN values
        are still masked.
    vel_field : str, optional
        Field in radar to use as the Doppler velocities during dealiasing.
        None will use the default field name from the Py-ART configuration
        file.
    corr_vel_field : str, optional
        Name to use for the dealiased Doppler velocity field metadata.  None
        will use the default field name from the Py-ART configuration file.
    last_vel_field : str, optional
        Name to use for the dealiased Doppler velocity field metadata in
        last_radar.  None will use the corr_vel_field name.
    maxshear : float, optional
        Maximum vertical shear which will be incorporated into the created
        volume from the sounding data.  Parameter not used when no
        sounding data is provided.
    sign : int, optional
        Sign convention which the radial velocities in the volume created
        from the sounding data will will. This should match the convention
        used in the radar data. A value of 1 represents when positive values
        velocities are towards the radar, -1 represents when negative
        velocities are towards the radar.
    compthresh : float, optional
        Fraction of the Nyquist velocity to use as a threshold when performing
        continuity (initial) dealiasing.  Velocities differences above this
        threshold will not be marked as gate from which to begin unfolding
        during spatial dealiasing.
    compthresh2 : float, optional
        The same as compthresh but the value used during the second pass of
        dealiasing.  This second pass is only performed in both a sounding
        and last volume are provided.
    thresh : float, optional
        Fraction of the Nyquist velocity to use as a threshold when performing
        spatial dealiasing.  Horizontally adjacent gates with velocities above
        this threshold will count against assigning the gate in question the
        velocity value being tested.
    ckval : float, optional
        When the absolute value of the velocities are below this value they
        will not be marked as gates from which to begin unfolding during
        spatial dealiasing.
    stdthresh : float, optional
       Fraction of the Nyquist velocity to use as a standard deviation
       threshold in the window dealiasing portion of the algorithm.
    epsilon : float, optional
        Difference used when comparing a value to missing value, changing this
        from the default is not recommended.
    maxcount : int, optional
        Maximum allowed number of fold allowed when unfolding velocities.
    pass2 : int, optional
        Controls weather unfolded gates should be removed (a value of 0)
        or retained for unfolding during the second pass (a value of 1) when
        both a sounding volume and last volume are provided.
    rm : int, optional
        Determines what should be done with gates that are left unfolded
        after the first pass of dealiasing.  A value of 1 will remove these
        gates, a value of 0 sets these gates to their initial velocity.  If
        both a sounding volume and last volume are provided this parameter is
        ignored.
    proximity : int, optional
        Number of gates and rays to include of either side of the current gate
        during window dealiasing.  This value may be doubled in cases where
        a standard sized window does not capture a sufficient number of
        good valued gates.
    mingood : int, optional
        Number of good valued gates required within the window before the
        current gate will be unfolded.
    ba_mincount : int, optional
        Number of neighbors required during Bergen and Albers filter for
        a given gate to be included, must be between 1 and 8, 5 recommended.
    ba_edgecount : int, optional
        Same as ba_mincount but used at ray edges, must be between 1 and 5,
        3 recommended.
    debug : bool, optional
        Set True to return RSL Volume objects for debugging:
        usuccess, radialVelVolume, lastVelVolume, unfoldedVolume, sondVolume

    Returns
    -------
    vr_corr : dict
        Field dictionary containing dealiased Doppler velocities.  Dealiased
        array is stored under the 'data' key.

    Notes
    -----
    Due to limitations in the C code do not call with sounding arrays over
    999 elements long.

    References
    ----------
    C. N. James and R. A Houze Jr, A Real-Time Four-Dimensional Doppler
    Dealising Scheme, Journal of Atmospheric and Oceanic Technology, 2001, 18,
    1674.

    """
    # TODO test with RHI radar scan

    # check that FourDD is available (requires TRMM RSL)
    if not _FOURDD_AVAILABLE:
        raise MissingOptionalDependency(
            "Py-ART must be build with support for TRMM RSL to use" +
            "the dealias_fourdd function.")

    # verify that sounding data or last_volume is provided
    sounding_available = ((sounding_heights is not None) and
                          (sounding_wind_speeds is not None) and
                          (sounding_wind_direction is not None))
    if (not sounding_available) and (last_radar is None):
        raise ValueError('sounding data or last_radar must be provided')

    # parse the field parameters
    if vel_field is None:
        vel_field = get_field_name('velocity')
    if corr_vel_field is None:
        corr_vel_field = get_field_name('corrected_velocity')
    if last_vel_field is None:
        last_vel_field = get_field_name('corrected_velocity')

    # get fill value
    fill_value = get_fillvalue()

    # parse radar gate filter
    gatefilter = _parse_gatefilter(gatefilter, radar, **kwargs)
    excluded = gatefilter.gate_excluded

    # create RSL volumes containing the doppler velocity and
    # doppler velocity in the last radar (if provided)
    vel_volume = _create_rsl_volume(radar, vel_field, 1, rsl_badval, excluded)

    if last_radar is not None:
        last_vel_volume = _create_rsl_volume(
            last_radar, last_vel_field, 1, rsl_badval)
    else:
        last_vel_volume = None

    # create an RslVolume containing the sounding data if it available
    if sounding_available:
        # convert the sounding data to 1D float32 arrays
        hc = np.ascontiguousarray(sounding_heights, dtype=np.float32)
        sc = np.ascontiguousarray(sounding_wind_speeds, dtype=np.float32)
        dc = np.ascontiguousarray(sounding_wind_direction, dtype=np.float32)

        success, sound_volume = _fourdd_interface.create_soundvolume(
            vel_volume, hc, sc, dc, sign, max_shear)
        if success == 0:
            raise ValueError('Error when loading sounding data')
    else:
        sound_volume = None

    # perform dealiasing
    if debug:
        return _fourdd_interface.fourdd_dealias(
            vel_volume, last_vel_volume, sound_volume,
            filt, debug=True, **kwargs)

    flag, data = _fourdd_interface.fourdd_dealias(
        vel_volume, last_vel_volume, sound_volume, filt, debug=False, **kwargs)

    # prepare data for output, set bad values and mask data
    is_bad_data = np.logical_or(np.isnan(data), data == rsl_badval)
    if keep_original:
        vel_array = radar.fields[vel_field]['data']
        data = np.where(is_bad_data, vel_array, data)
    else:
        data[is_bad_data] = fill_value
    data = np.ma.masked_equal(data, fill_value)

    # return field dictionary containing dealiased Doppler velocities
    vr_corr = get_metadata(corr_vel_field)
    vr_corr['data'] = data
    vr_corr['_FillValue'] = data.fill_value
    return vr_corr


def _create_rsl_volume(radar, field_name, vol_num, rsl_badval, excluded=None):
    """
    Create a RSLVolume containing data from a field in radar.
    """
    fill_value = get_fillvalue()
    fdata = np.copy(radar.fields[field_name]['data']).astype(np.float32)
    fdata = np.ma.filled(fdata, fill_value)
    is_bad = np.logical_or(fdata == fill_value, np.isnan(fdata))
    fdata[is_bad] = rsl_badval
    if excluded is not None:
        fdata[excluded] = rsl_badval
    rays_per_sweep = (radar.sweep_end_ray_index['data'] -
                      radar.sweep_start_ray_index['data'] + 1)
    rays_per_sweep = rays_per_sweep.astype(np.int32)
    rsl_volume = _rsl_interface.create_volume(fdata, rays_per_sweep, vol_num)
    _rsl_interface._label_volume(rsl_volume, radar)
    return rsl_volume


def find_time_in_interp_sonde(interp_sonde, target, debug=False):
    """
    Find the wind parameter for a given time in a ARM interpsonde file.

    Parameters
    ----------
    interp_sonde : netCDF4.Dataset
        netCDF4 object pointing to a ARM interpsonde file.
    target : datetime
        Target datetime, the closest time in the interpsonde file will be
        used.

    Other Parameters
    ----------------
    debug : bool
        Print debugging information.

    Returns
    -------
    height : np.ndarray
        Heights above the ground for the time closest to target.
    speed : np.ndarray
        Wind speeds at given height for the time closest to taget.
    direction : np.ndarray
        Wind direction at given height for the time closest to target.

    """

    sonde_datetimes = datetime_utils.datetimes_from_dataset(interp_sonde)

    # get closest time index to target
    idx = np.abs(sonde_datetimes - target).argmin()

    if debug:
        print('Target time is %s' % (target))
        print('Interpolated sounding time is %s' % (sonde_datetimes[idx]))

    return (interp_sonde.variables['height'][:],
            interp_sonde.variables['wspd'][idx, :],
            interp_sonde.variables['wdir'][idx, :])
