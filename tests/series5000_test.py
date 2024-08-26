'''
This is a test for the Picoscope class. 
'''

from pypicostreaming.series5000.series5000 import Picoscope5000a

# Measurment paramters
capture_size = 10000
samples_total = 90
sampling_time = 10000
sampling_time_scale = 'PS5000A_MS'

# Connect i nstrument and perform the acquisiton
pico = Picoscope5000a(None, 'PS5000A_DR_14BIT')
pico.set_pico(capture_size, samples_total, sampling_time, sampling_time_scale)
saving_path = 'E:/Experimental_data/Federico/2024/python_software_test/2408261406_testing_pico_saving'
pico.set_channel('PS5000A_CHANNEL_A', 'PS5000A_200MV',saving_path)
pico.run_streaming_blocking(autoStop= False)

#%%
pico.stop()
pico.disconnect()

#%%
import matplotlib.pyplot as plt
# pico.convert_all_channels()
x = [pico.channels['A'].signal.get() for _ in range(pico.channels['A'].signal.qsize())]
plt.figure()
plt.plot(x)
