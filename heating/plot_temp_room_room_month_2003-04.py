from matplotlib import pyplot as plt
from matplotlib import dates as mdates
import os
import pandas as pd

start = "2003-04-01 00:00:00"
stopp = "2003-04-15 00:00:00"

# wf = pd.read_csv(
#     "../austaltools/heating_walls_history.csv",
#     index_col='time',
#     parse_dates=True
# )
# wp = wf.filter(regex="temp.*_back").loc[
#     (wf.index <= pd.to_datetime(stopp)) &
#     (wf.index >= pd.to_datetime(start))
# ]

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
ax.plot(rp.index,
        rp['tmp_outside'],
        color="blue")
ax.plot(rp.index,
        rp['tmp_room'],
        color="orange")
a2.plot(rp.index,
        rp['pwr_room'],
        color="green")
a2.set_ylim([0,13000])
plt.show()
fig.savefig(__file__.replace('.py','.png'), dpi=180)
