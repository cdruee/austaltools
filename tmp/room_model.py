from tqdm import tqdm
import numpy as np
import matplotlib.pyplot as plt

import meteolib as m

cp = m.constants.cp
WALL_SLAB = 0.02  # m
TIMESTEP = 1  # s
PRESSURE = 101325  # Pa


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
    thickness = .24   # m
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
    heat_capacty = 900.  # J/kgK (concrete)
    heat_conduct = 2.4   # w/mK (concrete)
    density = 2400           # kg/m³
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
        if self.name == 'front':
            pass
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
        if self.name == 'front':
            print (rooms[self.room_w].temp, self.t_slab,rooms[self.room_c].temp )
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
        if name  in self.specials:
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

    def tick(self, walls: WallList, timedelta: float  = TIMESTEP):
        if self.name  in self.specials:
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

class RoomList(dict):

    def __init__(self, walls):
        dict.__init__(self)
        self.walls = walls

    def append(self, room):
       self[room.name] = room

    def init_walls(self):
        for x in self.values():
            x.init_walls(walls=self.walls)

    def tick(self, walls, timedelta: float = TIMESTEP):
        for x in self.values():
            x.tick(walls, timedelta)


class Building():
    name = str()
    walls = WallList()
    rooms = RoomList(walls=walls)
    init = False

    def __init__(self, name, t_out, t_soil):
        self.name = name
        self.rooms.append(Room('outside', t_start=t_out))
        self.rooms.append(Room('soil', t_start=t_soil))

    def init_walls(self):
        rnames = self.rooms.keys()
        if 'outside' not in rnames or 'soil' not in rnames:
            raise ValueError('special rooms `soil` and `outside` missing')
        self.rooms.walls = self.walls
        self.rooms.init_walls()

    def tick(self, timedelta: float = TIMESTEP):
        if not self.init:
            self.init_walls()
        self.walls.tick(self.rooms,timedelta)
        self.rooms.tick(self.walls,timedelta)


def make_buidling(t_out=0):
    bldg = Building('house', t_out=t_out, t_soil=6.)

    bldg.rooms.append(Room('room', width=5., lenght=5., height=2.5,
                           t_set=20, t_start=t_out, maxpower=13000.))

    bldg.walls.append(Wall('front', 0.30, 'room', 'outside',
                           l=5., h=2.5, t_start=t_out))
    bldg.walls.append(Wall('left', 0.30, 'room', 'outside',
                           l=5., h=2.5, t_start=t_out))
    bldg.walls.append(Wall('right', 0.30, 'room', 'outside',
                           l=5., h=2.5, t_start=t_out))
    bldg.walls.append(Wall('back', 0.30, 'room', 'outside',
                           l=5., h=2.5, t_start=t_out))
    bldg.walls.append(Wall('floor', 0.05, 'room', 'soil',
                           c=1500., k=0.15, rho=600.,
                           l=5., h=5., t_start=t_out)) # wood

    bldg.walls.append(Wall('ceilg', 0.20, 'room', 'outside',
                           c=1500., k=0.15, rho=600.,
                           l=5., h=5., t_start=t_out)) # wood
    return bldg



def main():
    t_in = 20
    t_out = 0
    building = make_buidling(t_out=t_out)

    dt = 5
    time = 360000
    ticks = int(time / dt)
    trec = list()
    prec = list()
    for tick in range(ticks):
        building.tick()
        trec.append(building.rooms['room'].temp)
        prec.append(building.rooms['room'].power)
        #prec.append(building.walls['front'].f_flux[0])
    print (trec)
    print (prec)

    fig, ax = plt.subplots()
    cols = ['blue', 'orange', 'green', 'red', 'brown', 'pink']
    t = [x*dt for x in range(ticks)]
    ax.plot(t, trec, color=cols[0] ,label='T')
    sx = ax.twinx()
    sx.plot(t, prec, '--', color=cols[1], label = 'P')
    fig.legend()
    fig.show()
    # fig, ax = plt.subplots(2,2, squeeze=True)
    # for i,dd in enumerate(dds):
    #     nx,nt = ttt[dd].shape
    #     t = [x * dt for x in range(nx)]
    #     x = [dd * x for x in range(nt)]
    #     ax.flatten()[i].imshow(ttt[dd],aspect='auto')
    # fig.show()

if __name__ == '__main__':
    main()