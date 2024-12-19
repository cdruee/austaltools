#!/usr/bin/env python3
import argparse
import csv
import inspect
import logging
import os
import sys

import yaml
from tqdm import tqdm
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import meteolib as m

try:
    from . import _tools
    # from ._version import __version__, __title__
    # from . import _corine
    from . import _datasets
    # from . import import_buildings
    # from . import eap
    # from . import fill_timeseries
    # from . import input_terrain
    from . import input_weather
    # from . import steepness
    # from . import transform
    # from . import plot
    # from . import windfield
except ImportError:
    import _tools
    # from _version import __version__, __title__
    import _datasets
    # import _corine
    # import import_buildings
    # import eap
    # import fill_timeseries
    # import input_terrain
    import input_weather
    # import steepness
    # import transform
    # import plot
    # import windfield

# ----------------------------------------------------

logging.basicConfig()
logger = logging.getLogger()

# ----------------------------------------------------

cp = m.constants.cp

WALL_SLAB = 0.04  # m
TIMESTEP = 1  # s
PRESSURE = 101325  # Pa

HEATING_LIMIT = 15 # °C
MEAN_ROOM_TEMP = 20 # °C

# ------------------------------------------------

_OUTPUT_ROOMS = None
_OUTPUT_WALLS = None

# ----------------------------------------------------


# class output_standard_file():
#     def __init__(self):


class Wall:
    """
    Wall element

    roow_w     ->         (positive flux)            -> room c

    width:    |   slab     | slab | ... |   slab  |
    t             *           *      *        *
    width: | slab + excess | slab | ... | slab + excess |
    flux   *               *      *     *               *
    """
    name = str()
    partof = str()
    thickness = .36   # m
    lenght = float()  # m
    height = float()  # m
    area_full = float()  # m²
    area = float()  # m²
    orient = np.nan   # deg clockwise from north
    d_slab = float()  # m
    n_slab = int()    # 1
    t_slab = list()   # °C
    n_flux = int()    # 1
    f_flux = list()   # W/m²
    d_flux = list()   # m
    # source: https://www.schweizer-fn.de/stoff/wleit_isolierung/wleit_isolierung.php
    heat_conduct = 0.58  # W/mK (brick wall)
    # source https://www.schweizer-fn.de/stoff/wkapazitaet/wkapazitaet_baustoff_erde.php
    heat_capacty = 836.  # J/kgK (brick wall)
    density = 1400       # kg/m³ (brick wall)
    def __init__(self, name, d, room_w, room_c,
                 l=None, h=None, area=None,
                 c=None, k=None, rho=None,
                 partof=None, t_start=None):
        self.name = name
        self.room_w = room_w
        self.room_c = room_c
        if c is not None:
            self.heat_capacty = c
        if k is not None:
            self.heat_conduct = k
        if rho is not None:
            self.density = rho
        if l is not None and h is not None:
            self.lenght = l
            self.height = h
            self.area_full = l * h
        if area is not None:
            self.area_full = area
        # area is full area minus embeddded elements (corrected by WallList)
        self.partof = partof
        self.area = self.area_full
        # calculate number of slabs
        self.thickness = d
        self.d_slab = WALL_SLAB
        self.n_slab = int(self.thickness / self.d_slab)
        # calculate distances between slab centers for
        # flux calculation (add excess thickness at the two
        # outermost slabs)
        excess = (self.thickness - (self.n_slab * self.d_slab)) / 2.
        self.n_flux = self.n_slab + 1
        self.d_flux = self.n_flux * [np.nan]
        self.f_flux = self.n_flux * [np.nan]
        for i in range(self.n_flux):
            if i == 0 :
                self.d_flux[i] = excess + self.d_slab
            elif i == self.n_flux :
                self.d_flux[i] = self.d_slab + excess
            else:
                self.d_flux[i] = self.d_slab
        # initialize temperature
        if t_start is None:
            # assume linear temperature profile if no t_start is given
            t_a = room_w.temp
            t_b = room_c.temp
            self.t_slab = [(t_b -t_a)/(self.n_slab + 1) * (x + 1)
                           for x in range(self.n_slab)]
        else:
            # set alls slabs to have temperature t_start
            self.t_slab = self.n_slab * [t_start]

    def tick(self, rooms, timedelta=TIMESTEP):
        # if self.name == 'front':
        #     pass
        for i in range(self.n_flux):
            if i == 0:
                dth = self.t_slab[0] - rooms[self.room_w].temp
            elif i == self.n_slab:
                dth = rooms[self.room_c].temp - self.t_slab[i - 1]
            else:
                dth = self.t_slab[i] - self.t_slab[i - 1]
            self.f_flux[i] = - self.heat_conduct * dth / self.d_flux[i]
        for i in range(self.n_slab):
            diff = (self.f_flux[i] - self.f_flux[i + 1])
            dtdt = diff / (self.density * self.d_slab * self.heat_capacty)
            self.t_slab[i] += dtdt * timedelta
        # if self.name == 'front':
        #     print (rooms[self.room_w].temp, self.t_slab,rooms[self.room_c].temp )
        return

class WallList(dict):
    def __setitem__(self, index, value: Wall):
        dict.__setitem__(self, index, value)
        if index != value.name:
            raise ValueError(f'key does not match name in {value.name}')
        for x in self.values():
            if x.partof is not None:
                if x.partof not in self.keys():
                    raise ValueError(
                        f'partof element not found in: {value.name}')
                if x.partof == x.name:
                    raise ValueError(
                        f'partof self found in: {value.name}')
                self[value.partof].area -= value.area
                if self[value.partof].area < 0:
                    raise ValueError(
                        f'parts larger than parent: '
                        f'{self[value.partof].name}')

    def append(self, wall: Wall):
        self[wall.name] = wall

    def tick(self, rooms, timedelta: float = TIMESTEP):
        for x in self.values():
            x.tick(rooms, timedelta)



class Room:
    specials = ['outside', 'soil']
    name = str()
    temp = float()
    target_temp = np.nan  # °C
    target_power = np.nan  # 1 (1= 100% of self.power)
    maxpower = float()  # W
    power = float()  # W
    width = float()  # m
    lenght = float()  # m
    height = float()  # m
    area = float()  # m² overrides width * lenght
    volume = float()  # m³ overrides area * height
    add_c = 0.        # J/K additional heat capacity by objects in the room
    wall_sign = {}
    def __init__(self, name, width=None, lenght=None, height=None,
                 maxpower=None, area=None, volume=None,
                 t_set=None, p_set=None, t_start=None):
        self.name = name
        if self.is_special():
            if t_start is None:
                self.temp = np.nan
            else:
                self.temp = t_start
            self.target_temp = np.nan
            self.target_power = np.nan
            self.maxpower = 0.
            self.lenght = np.nan
            self.height = np.nan
            self.area = np.nan
            self.volume = 0.
        else:
            if t_start is not None:
                self.t_start = t_start
            else:
                self.t_start = t_set
            if t_set is not None:
                self.target_temp = t_set
            else:
                self.target_temp = np.nan
            if p_set is not None:
                self.target_power = p_set
            else:
                self.target_power = np.nan
            if maxpower is None:
                raise ValueError('maxpower is required with normal rooms')
            else:
                self.maxpower = maxpower
            self.width = width
            self.lenght = lenght
            self.height = height
            if area is not None:
                self.area = area
            else:
                if lenght is None and width is None:
                    raise ValueError(
                        'either width & length or area'
                        'are required with normal rooms')
                self.area = self.width * self.lenght
            if volume is not None:
                self.volume = volume
            else:
                if lenght is None and width is None:
                    raise ValueError(
                        'either height or volume'
                        'are required with normal rooms')
                self.volume = self.area * self.height

    def init_walls(self, walls: WallList):
        for w in walls.values():
            if w.room_w == self.name:
                self.wall_sign[w.name] = -1.
            if w.room_c == self.name:
                self.wall_sign[w.name] = +1.

    def get_fluxes(self, walls: WallList):
        fluxes = {}
        for w in walls.values():
            if w.name in self.wall_sign.keys():
                if self.wall_sign[w.name] > 0:
                    fluxes[w.name] =        w.f_flux[-1] * w.area
                elif self.wall_sign[w.name] < 0:
                    fluxes[w.name] = -1. *  w.f_flux[ 0] * w.area

        return fluxes

    def is_special(self):
        if self.name in self.specials:
            return True
        return False

    def tick(self, walls: WallList, timedelta: float  = TIMESTEP):
        if self.is_special():
            return
        # density of air
        rho = m.thermodyn.gas_rho(p=PRESSURE, T=self.temp,
                                  Kelvin=False, hPa=False)
        # calculate fluxes thrpugh all wall elements
        w_f = self.get_fluxes(walls)
        # external energy budget
        P_flux = np.nansum(list(w_f.values()))
        P_vent = 0. # not implemented
        P_rad = 0. # not implemented
        P_external = P_rad + P_flux + P_vent
        # calculate heating power needed to maintain target temperature
        if np.isnan(self.target_power):
            # if heatings is temperature regulated:
            # pwer to compensate heat loss by fluxes
            self.power = -P_external
            # power needed to heat up
            if self.temp < self.target_temp:
                self.power += ((self.target_temp - self.temp) * cp * rho
                               / timedelta)
            else:
                self.power = 0.
            # limit power to capabilities of heating
            if self.power > self.maxpower:
                self.power = self.maxpower
            elif self.power < 0.:
                self.power = 0.
        else:
            # if heating is power-regulated
            self.power = self.maxpower * self.target_power
        P_heat = self.power
        dQ = (P_heat + P_vent + P_flux + P_vent) * timedelta
        dT = dQ / (m.constants.cp * rho * self.volume + self.add_c)
        self.temp = self.temp + dT
        return self.temp

class RoomList(dict[Room]):

    def __init__(self, walls):
        dict.__init__(self)

    def append(self, room):
       self[room.name] = room

    def init_walls(self,walls):
        for x in self.values():
            x.init_walls(walls)

    def tick(self, walls, timedelta: float = TIMESTEP):
        for x in self.values():
            x.tick(walls, timedelta)


class Building():
    name = str()
    walls = WallList()
    rooms = RoomList(walls=walls)
    hvac = {}
    init = False
    output = None

    def __init__(self, name, t_out, t_soil):
        self.name = name
        self.rooms.append(Room('outside', t_start=t_out))
        self.rooms.append(Room('soil', t_start=t_soil))

    @classmethod
    def from_yaml(cls, name, d):
        t_out = d.get('t_out', np.nan)
        t_soil = d.get('t_soil', np.nan)
        obj = Building(name, t_out, t_soil)
        for k,v in d['walls'].items():
            args = {'name': k}
            for x,y in inspect.signature(Wall.__init__).parameters.items():
                if x in ['self', 'name']: continue
                # mandatory args (== no default value)
                if x not in v and y.default == inspect.Parameter.empty:
                    raise ValueError(f'{y.name} not declared in wall {k}')
                args[x] = v.get(x,y.default)
            obj.walls.append(Wall(**args))
        for k, v in d['rooms'].items():
            args = {'name': k}
            for x,y in inspect.signature(Room.__init__).parameters.items():
                if x in ['self', 'name']: continue
                # mandatory args (== no default value)
                if x not in v and y.default == inspect.Parameter.empty:
                    raise ValueError(f'{y.name} not declared in wall {k}')
                args[x] = v.get(x,y.default)
            obj.rooms.append(Room(**args))
        obj.hvac = d['hvac']
        return obj

    def __eq__(self, other):
        if not isinstance(other, Building):
            # don't attempt to compare against unrelated types
            return NotImplemented
        return (self.name == other.name and
                self.walls == other.walls and
                self.rooms == other.rooms and
                self.hvac == other.hvac and
                self.output == other.output
                )

    def get_rooms(self):
        return [x.name for x in self.rooms.values() if not x.is_special()]

    def init_walls(self):
        rnames = self.rooms.keys()
        if 'outside' not in rnames or 'soil' not in rnames:
            raise ValueError('special rooms `soil` and `outside` missing')
        self.rooms.init_walls(self.walls)

    def tick(self, timedelta: float = TIMESTEP):
        if not self.init:
            self.init_walls()
        self.walls.tick(self.rooms,timedelta)
        self.rooms.tick(self.walls,timedelta)



def building_model_timeseries(bldg: Building, ts: pd.Series):

    t_out=float(ts.values[0])

    room_names = bldg.get_rooms()
    nrooms = len(room_names)
    columns = (['seconds','power'] +
               [y % x
                for x in room_names
                for y in ['tmp_%s', 'pwr_%s']
                ]
               )
    res = pd.DataFrame(np.nan, index=ts.index, columns=columns)


    dtick = pd.Timedelta(TIMESTEP, unit='s') # seconds
    pointer = ts.index[0]
    oldpointer = pointer
    # iterate over times (execept last one)
    for i in tqdm(range(ts.size - 1 )):
        dtime = (ts.index[i+1] - ts.index[i]).total_seconds()
        nticks = int(dtime / dtick.total_seconds()) + 1
        powers = np.empty((nticks, nrooms))
        temps = np.empty((nticks, nrooms))
        # for tick in range(nticks):
        tick = 0
        bldg.rooms['outside'].temp = ts[ts.index[i]]
        while pointer + dtick < ts.index[i + 1]:
            bldg.tick(timedelta=dtick.total_seconds())
            temps[tick, :] = [bldg.rooms[x].temp for x in room_names]
            powers[tick, :] = [bldg.rooms[x].power for x in room_names]
            pointer += dtick
            tick += 1
        room_temps = temps.mean(axis=0)
        mean_powers = powers.mean(axis=0)
        ix = ts.index[i]
        for i,x in enumerate(room_names):
            res.loc[ix,'tmp_%s' % x] = room_temps[i]
            res.loc[ix,'pwr_%s' % x] = mean_powers[i]
        res.loc[ix, 'power'] = mean_powers.sum()
        res.loc[ix, 'seconds'] = (pointer - oldpointer).total_seconds()

        oldpointer = pointer

    res.loc[res.index[-1], :] = res.loc[res.index[-2], :]
#    print (trec)
#    print (prec)

    # fig, ax = plt.subplots()
    # cols = ['blue', 'orange', 'green', 'red', 'brown', 'pink']
    # t = [x*dt for x in range(ticks)]
    # ax.plot(t, trec, color=cols[0] ,label='T')
    # sx = ax.twinx()
    # sx.plot(t, prec, '--', color=cols[1], label = 'P')
    # fig.legend()
    # fig.show()

    # fig, ax = plt.subplots(2,2, squeeze=True)
    # for i,dd in enumerate(dds):
    #     nx,nt = ttt[dd].shape
    #     t = [x * dt for x in range(nx)]
    #     x = [dd * x for x in range(nt)]
    #     ax.flatten()[i].imshow(ttt[dd],aspect='auto')
    # fig.show()
    return res

def main(args):
    name = args.get('building', 'default')
    filename = args.get('file', 'heating.yaml')
    csv_name = args['extracted_weather']
    if os.path.exists(csv_name):
        logger.info('reading weather data from: %s' % csv_name)
        # read position fom comment line
        with open(csv_name, 'r') as f:
            lat, lon, ele, nam = f.readline(
                ).strip('# \n').split(maxsplit=4)
        # read observation data
        obs = pd.read_csv(csv_name, comment='#', index_col=0,
                          parse_dates=True, na_values='-999')

    else:
        raise IOError('weather data not found: %s' % csv_name)


    dt = obs.index.diff().median()
    t_out = obs['t2m'].interpolate('linear').bfill().ffill()
    t_out = t_out.apply(m.temperature._to_C)

    with open(filename, 'r') as f:
        dictionary = yaml.safe_load(f)
    for k,v in dictionary['buildings'].items():
        if k == name:
            bldg = Building.from_yaml(k,v)
            break
    else:
        raise ValueError('no building named %s' % name)
    model_out = building_model_timeseries(bldg=bldg, ts=t_out)
    model_out.to_csv("heating_model_out.csv", quoting=csv.QUOTE_NONE,
               float_format="%12.5f")
    energy = model_out['power'] * model_out['seconds'] # J
    emission_factors={
        'xx': 2100.E-9,  # g/J
        'nox': 50.E-9,  # g/J
        'pm-u': 20.E-9,  # g/J
        'odor': 6*168000.E-9,  # GE/J
        'wood_kg': 1/4.04E6, # kg/J
        'kWh': 1/(3600000), # kWh
    }
    res = pd.DataFrame({'energy':energy})
    for k,v in emission_factors.items():
        res[k] = res['energy'] * v
    print(res)
    res.to_csv("heating.csv", quoting=csv.QUOTE_NONE,
               float_format="%12.5f")
    print(res.sum(axis=0))


# ----------------------------------------------------

def add_options(subparsers: argparse.ArgumentParser) -> None:
    pars_htg = subparsers.add_parser(
        name='heating',
        aliases=[],
        help='simulate a building with heating'
    )
    default = {'building': 'default',
               'heating-file': 'heating.yaml',
               'extracted_weather': 'extracted_weather.csv',
               # 'source': 'CERRA',
               # 'year': 2003,
               'output': 'heating.csv',
               }
    pars_htg.add_argument('-f', '--heating-file',
                          help='building/heating description file. ' +
                               '[%s]' % default['heating-file'],
                          default=default['heating-file'])
    pars_htg.add_argument('-b', '--building',
                          help='name of the building to simulate. ' +
                               '[%s]' % default['building'],
                          default=default['building'])
    pars_htg.add_argument('-x', '--extracted-weather',
                          help='name of the file containing the '
                               'weather data ' +
                               '[%s].' % default['extracted_weather'],
                          default=default['extracted_weather'])

    pars_htg.add_argument('-o', '--output', nargs=1,
                          help='name for the output file. ' +
                               '[%s]' % default["output"],
                          default=default["output"])

    return pars_htg


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
        'output': 99999
    }
    main(args)

#out,err = capture.done()
