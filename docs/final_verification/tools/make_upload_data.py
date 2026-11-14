"""Synthetic but realistic hourly meter file for the upload test: 4 residential blocks + lift, pump, street lights; 16 months; 15-minute noise-free hourly kWh."""
import numpy as np, pandas as pd
rng=np.random.default_rng(7)
idx=pd.date_range("2023-01-01 00:00","2024-04-30 23:00",freq="h")
hod=idx.hour.values; dow=idx.dayofweek.values; doy=idx.dayofyear.values
def block(base,amp_morn,amp_eve,scale):
    daily=base+amp_morn*np.exp(-((hod-7.5)/1.8)**2)+amp_eve*np.exp(-((hod-20)/2.6)**2)
    weekly=1+0.08*(dow>=5); season=1+0.18*np.cos(2*np.pi*(doy-200)/365)
    return scale*daily*weekly*season*rng.normal(1,0.04,len(idx))
cols={f"Block_{c}":np.round(block(30,22,48,s),2) for c,s in zip("ABCD",(1.0,1.25,0.8,1.1))}
cols["Lift_A"]=np.round(3+4*np.exp(-((hod-8)/2)**2)+4*np.exp(-((hod-19)/2.5)**2)+rng.normal(0,.2,len(idx)).clip(-.5,.5),2)
cols["Pump_1"]=np.round(np.where((hod>=5)&(hod<=7)|(hod>=18)&(hod<=19),5.5,0.3)+rng.normal(0,.1,len(idx)),2)
cols["Streetlights"]=np.round(np.where((hod>=18)|(hod<=5),6.0,0.0)+np.where((hod>=18)|(hod<=5),rng.normal(0,.1,len(idx)),0),2)
df=pd.DataFrame(cols,index=idx); df.index.name="timestamp"
# realistic faults: a few missing readings and one stuck stretch (the cleaner must drop these, not fill them)
df.iloc[[500,501,502,4000],0]=np.nan
df.iloc[7000:7060,1]=df.iloc[7000,1]
df.round(2).to_csv("/home/claude/pro/run/upload_test/readings.csv")
pd.DataFrame({"meter_id":list(cols),"building":["Block A","Block B","Block C","Block D","","",""],"kind":["building"]*4+["facility"]*3,
  "facility_category":["","","","","lift","pump","streetlight"],"floor_area_sqm":[8200,10100,6500,8900,"","",""]}).to_csv("/home/claude/pro/run/upload_test/mapping.csv",index=False)
print(df.shape, df.index.min(), df.index.max())
