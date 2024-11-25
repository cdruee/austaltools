import logging
import os
import sys

import pandas as pd
import jsonschema 

import py
from samba.upgradehelpers import delta_update_basesamdb

try:
    from . import _tools
    from ._version import __version__, __title__
    from . import _corine
    from . import _datasets
    from . import import_buildings
    from . import eap
    from . import fill_timeseries
    from . import input_terrain
    from . import input_weather
    from . import steepness
    from . import transform
    from . import plot
    from . import windfield
except ImportError:
    import _tools
    from _version import __version__, __title__
    import _datasets
    import _corine
    import import_buildings
    import eap
    import fill_timeseries
    import input_terrain
    import input_weather
    import steepness
    import transform
    import plot
    import windfield


# ----------------------------------------------------

logging.basicConfig()
logger = logging.getLogger()

# ----------------------------------------------------

HEATING_LIMIT = 15 # °C
MEAN_ROOM_TEMP = 20 # °C


# ----------------------------------------------------

def hottinger_inv(hgt, dtmax, th, qmax, eta):
    # qmax: design power kW
    # hgt: heating degrees days Kd
    # th: hottinger_number = daily usage hours h/d
    # eta: efficiency 1
    # dtmax: temperature_difference K
    # annual_consumption: kWh
    annual_consumption = (
        (qmax * th * hgt) / (eta * dtmax)
    )
    return annual_consumption

# ----------------------------------------------------
def standard_room_heat_loss_factors(parts: list[dict]):
    r"""

    :param parts:
    :type parts:
    :return:
    :rtype:
    """
    H_T = []
    dU_TB = 0. # W/(m²K)
    for k in parts:
        A_k = standard_area(k)  # m²
        U_k = standard_part_heat_loss_factor(part)
        other = k.get("other", "outside")
        if other == "outside":
            dU_TBk = k.get("dU_TBk", 0.)
            f_Uk = k.get("f_Uk", 1.)
            f_iek = k.get("f_iek", 1.)
            H_T[k] = A_k * (U_k + dU_TBk) * f_Uk * f_iek
        elif other == "room":
            f_iak = k.get("f_iak", 1.)
            H_T[k] = A_k * U_k * f_iak
        elif other == "ground":
            f_thetaann = k.get("f_thetaann", 1.)
            U_equivk *= k.get("U_equivk", 1.)
            f_igk = k.get("f_igk", 1.)
            f_GWk = k.get("f_GWk", 1.)
            H_T[k] = f_thetaann * A_k * U_equivk * f_igk * f_GWk

    return H_T  # W/K


# ----------------------------------------------------
def room_heatconduction_loss(room):
    r"""
    .. math:`L_{\mathrm{conduct},i}`

    :param room:
    :type room:
    :return:
    :rtype:
    """

    H_T = standard_room_heat_loss_factors(room['parts'])
    phi_Ti = phi_Ti + H_T * (room['th_int'] - x['th_e'])
    return phi_Ti
# ----------------------------------------------------
def standard_heatingup_load(room):
    r"""
    :math:`\Phi_{hu,i}`

    :param room:
    :type room:
    :return:
    :rtype:
    """
    return 0.
# ----------------------------------------------------
def standard_heating_gain(room):
    r"""
    :math:`\Phi_{gain,i}`

    :param room:
    :type room:
    :return:
    :rtype:
    """
    return 0.

# ----------------------------------------------------
def standard_venting_loss(build):
    r"""
    \Phi_{V,i}

    :param build:
    :type build:
    :return:
    :rtype:
    """
    return 0.
# ----------------------------------------------------
def heating_load(build, t_out):
    r"""
    Total power needed to heat the building `build`.

    .. math:: L_{\mathrm{build}} =
            \sum_{i} L_{\mathrm{conduct},i} +
            \sum_{i} L_{\mathrm{heatup},i} +
            \sum_{i} L_{\mathrm{venting},i}

    Sum of all individual heat-conduction losses, venting losses and
    optional heating-up power needed to for each room.

    :param build:
    :type build: dict
    :return: power in W
    :rtype: float




    """
    t_rooms = room_temperature(build["rooms"])
    hl = 0.
    for i, room in enumerate(build['rooms']):
        hl += room_heatconduction_loss(room, t_out, i, t_rooms)
    hl += standard_venting_loss(build)
    for i, room in build['rooms'].items():
        hl += standard_heatingup_load(room)
        hl += standard_heating_gain(room)


# ----------------------------------------------------

def main(args):
    lat, lon, ele, stat_no, stat_nam = _tools.evaluate_location_opts(args)
    rechts, hoch, _ = _tools.ll2gk(lat, lon)

    if ele is None:
        if args.get("ele", None) is not None:
            ele = float(args["ele"])
        else:
            logger.warning('no elevation info. Assuming sea level. ' +
                           'You should consider providing -e')
            ele = 0.
    nam = args['output']
    logger.debug("rechts: %s, hoch: %s" % (rechts, hoch))
    logger.debug("lat: %s, lon: %s" % (lat, lon))
    logging.info('selected position: %.2f %.2f %.0f (%s)' %
                 (lat, lon, ele, format(nam)))
    year = int(args['year'])
    logger.debug("year: %s" % year)

    obs = pd.DataFrame()
    source = args['source']
    if source == "ERA5":
        obs, z0 = input_weather.get_era5_weather(lat, lon, year)
    elif source == "CERRA":
        obs, z0 = input_weather.get_cerra_weather(lat, lon, year)
    elif source == "DWD":
        if not _datasets.dataset_get(source).available:
            sys.tracebacklimit = 0
            raise ValueError(f"source {source} not available")
        path = _datasets.dataset_get(source).path
        obs, z0 = input_weather.get_dwd_weather(lat, lon, year, stat_no, path)
    else:
        raise ValueError("unknown source: %s" % source)

    #if OUTPUT_RAW != '':
    #    raw_name = 'extracted_{:05d}_{:04d}.csv'.format(nam, year)
    #    logger.info('writing raw data to: %s' % raw_name)
    #    obs.to_csv(raw_name, float_format='%.2f', index=False, na_rep='-999')

    dt = obs.index.diff().median()
    t_out = obs['t2m']
    t_out_day = obs['t2m'].resample('D').mean()
    t_diff = MEAN_ROOM_TEMP - (t_out -273.15)
    l ,b, h = 6., 8., 3.0 # m
    skin_area = b * h * 2 + l * h * 2 + l * b # m²
    k_value = 1.1 # W/m²K
    u_value = k_value * skin_area # W/K
    heating_schedule = [
        0, 0, 0, 0, 0, 0,
        1, 1, 1, 1, 1, 1,
        0.5, 0.5, 0.5, 0.5, 0.5, 1,
        1, 0.5, 0.5, 0.5, 0, 0,
    ]
    power = ( u_value * t_diff * (t_diff > 0) *
              [heating_schedule[x] for x in obs.index.hour]) # W
    #
    # build = Building()
    # build['th_a'] = -9.
    # build['th_g'] = 6.
    # build['rooms'][1] = {
    #     'th_int': 21.,
    #     'parts': [
    #         {'name': 'vorne',  'b': l, 'h': h, 'H_T': k_value, 'th_e': 'th_a'},
    #         {'name': 'links',  'l': b, 'h': h, 'H_T': k_value, 'th_e': 'th_a'},
    #         {'name': 'hinten', 'l': l, 'h': h, 'H_T': k_value, 'th_e': 'th_a'},
    #         {'name': 'rechts', 'l': b, 'h': h, 'H_T': k_value, 'th_e': 'th_a'},
    #         {'name': 'oben',   'l': b, 'b': b, 'H_T': k_value, 'th_e': 'th_a'},
    #         {'name': 'unten',  'l': b, 'b': b, 'H_T': k_value, 'th_e': 'th_g'},
    #     ]
    # }
    # power = standard_heating_load(build)
    energy = power * dt.total_seconds() # J
    emission_factors={
        'xx': 2100.E-6,  # g/J
        'nox': 50.E-6,  # g/J
        'pm-u': 20.E-6,  # g/J
        'odor': 6*168000.E-6,  # GE/J
        'wood': 1/4.04E6, # kg/J
        'kWh': 1/(3600000), # kWh
    }
    res = pd.DataFrame({'energy':energy})
    for k,v in emission_factors.items():
        res[k] = res['energy'] * v
    print(res)
    pass

# =========================================================================
# init at import:

AVAILABLE_WEATHER = input_weather.find_weather_data()
"""
List of locally available DEMs (filled upon imorting the module)

:meta hide-value:
"""

# ----------------------------------------------------

#capture = py.io.StdCaptureFD(err=False)

if __name__ == "__main__":
    args = {
        'source': 'CERRA',
        'year': '2003',
        'll': [49.75, 6.75],
        'output': 'oink'
    }
    main(args)

#out,err = capture.done()
