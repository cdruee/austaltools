from matplotlib import pyplot as plt
from matplotlib import dates as mdates
import os
import pandas as pd

start = "2003-04-10 00:00:00"
stopp = "2003-04-24 00:00:00"

wf = pd.read_csv(
    "../austaltools/heating_walls_history.csv",
    index_col='time',
    parse_dates=True
)
wp = wf.filter(regex="temp.*_back").loc[
    (wf.index <= pd.to_datetime(stopp)) &
    (wf.index >= pd.to_datetime(start))
]

rf = pd.read_csv(
    "../austaltools/heating_rooms_history.csv",
    index_col='time',
    parse_dates=True
)
rp = rf.filter(regex=".*").loc[
    (rf.index <= pd.to_datetime(stopp)) &
    (rf.index >= pd.to_datetime(start))
]


fig,ax=plt.subplots(figsize=(8,6))
#ax.invert_xaxis()
a2 = ax.twinx()
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.'))
ax.contourf(wp.index,
            [i * 0.04 for i in range(len(wp.columns))],
            wp.T,
            cmap="cool")
c=ax.contour(wp.index,
             [i * 0.04 for i in range(len(wp.columns))],
             wp.T,colors="white")
ax.clabel(c,inline=1)
a2.plot(rp.index,rp['pwr_room'], color='darkgreen')
a2.set_ylim([0,13000])
plt.show()
fig.savefig(__file__.replace('.py','.png'), dpi=180)
