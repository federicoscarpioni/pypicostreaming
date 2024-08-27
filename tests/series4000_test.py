'''
This is a test for the Picoscope class. It collect data on channel A for 
50 seconds at 0.1 seconds time step.
'''

from pypicostreaming.series4000.series4000 import PicoScope4000

# Measurment paramters
capture_size = 20
samples_total = 60
sampling_time = 100
sampling_time_scale = 'PS4000_MS'

# Connect i nstrument and perform the acquisiton
pico2 = PicoScope4000()
pico2.set_pico(capture_size, samples_total, sampling_time, sampling_time_scale, is_debug = True)
pico2.set_channel('PS4000_CHANNEL_A', 'PS4000_200MV')
pico2.run_streaming_non_blocking(autoStop=1)

#%%
pico2.stop()
pico2.disconnect()


