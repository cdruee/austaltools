from tqdm import tqdm
import numpy as np
import matplotlib.pyplot as plt



class Wall:
    thickness = .24 #m
    slab = float()  # m
    n = int() # 1
    t = list()
    d = list()   # m
    c = 900.   # J/K (concrete)
    k = 2.4   # w/mK (concrete)
    rho = 2400  # kg/m³
    def __init__(self, thick, t_in, t_out, slab):
        self.thickness = thick
        self.slab = slab
        nslab = int(thick / slab)
        d_out = (thick - slab * nslab) / 2
        self.d = [d_out] + nslab * [slab] + [d_out]
        self.n = nslab + 2
        self.t = [t_in] + (self.n - 1) * [t_out]

    def tick(self, dt):
        nflux = self.n - 1
        d = self.d
        flux = []
        for i in range(nflux):
            if i == 0 :
                dx = d[0] + d[1] / 2.
            elif i == nflux -1 :
                dx = d[nflux-1] / 2. + d[nflux ]
            else:
                dx = d[nflux-1] / 2. + d[nflux ] / 2.
            dth = self.t[i] - self.t[i + 1]
            flux.append(self.k * dth / dx)
        for i in range(nflux - 1):
            diff = (flux[i] - flux[i + 1])
            dtdt = diff / (self.rho * d[i+1] * self.c)
            self.t[i+1] += dtdt
        return flux[0],flux[-1]

def main():
    t_in = 20
    t_out = 0
    dt = 5
    time = 864000
    ticks = int(time / dt)
    fluxi = {}
    fluxo = {}
    ttt = {}
    dds = [0.0025, 0.01, 0.04, 0.08]
    for dd in tqdm(dds):
        wall = Wall(1, t_in, t_out, dd)
        tt = np.full((wall.n,ticks),np.nan)
        fli = np.full(ticks,np.nan)
        flo = np.full(ticks,np.nan)
        for i in range(ticks):
            fli[i],flo[i] = wall.tick(dt)
            tt[:,i] = wall.t
        fluxi[dd] = fli
        fluxo[dd] = flo
        ttt[dd] = tt
    fig, ax = plt.subplots()
    cols = ['blue', 'orange', 'green', 'red', 'brown', 'pink']
    for i,l in enumerate(fluxi.keys()):
        t = [x*dt for x in range(ticks)]
        ax.set_ylim(0,500)
        ax.plot(t, fluxi[l], color=cols[i] ,label=l)
        ax.plot(t, fluxo[l], '--', color=cols[i])
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