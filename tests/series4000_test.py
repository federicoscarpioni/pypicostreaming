'''
This is a test for the Picoscope class. It collect data on channel A for 
50 seconds at 0.1 seconds time step.
'''

from pypicostreaming.series4000 import PicoScope4000

# Measurment paramters
capture_size = 10000
samples_total = 90
sampling_time = 1000
sampling_time_scale = 'PS4000_MS'

# Connect i nstrument and perform the acquisiton
pico = PicoScope4000()
pico.set_pico(capture_size, samples_total, sampling_time, sampling_time_scale, is_debug = True)
pico.set_channel('PS4000_CHANNEL_A', 'PS4000_200MV')
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
