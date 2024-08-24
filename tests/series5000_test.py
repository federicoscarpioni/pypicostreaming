'''
This is a test for the Picoscope class. 
'''

from pypicostreaming.series5000 import PicoScope5000

# Measurment paramters
capture_size = 10000
samples_total = 90
sampling_time = 1000
sampling_time_scale = 'PS5000_MS'

# Connect i nstrument and perform the acquisiton
pico = PicoScope5000()
pico.set_pico(capture_size, samples_total, sampling_time, sampling_time_scale, is_debug = True)
pico.set_channel('PS5000_CHANNEL_A', 'PS5000_200MV')
pico.run_streaming_non_blocking(autoStop=0)

#%%
pico.stop()
pico.disconnect()

#%%
import matplotlib.pyplot as plt
# pico.convert_all_channels()
x = [pico.channels['A'].signal.get() for _ in range(pico.channels['A'].signal.qsize())]
plt.figure()
plt.plot(x)
