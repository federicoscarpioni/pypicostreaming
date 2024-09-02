'''
This is a test for the Picoscope class. 
'''

from pypicostreaming.series5000.series5000 import Picoscope5000a

# Measurment paramters
capture_size = 10000
samples_total = 5000000
sampling_time = 20
sampling_time_scale = 'PS5000A_US'

# Connect i nstrument and perform the acquisiton
pico = Picoscope5000a('PS5000A_DR_14BIT')
saving_path = 'E:/Experimental_data/Federico/2024/LRE-Reference_electrode_for_lithium/PCLRE011_3e/2408301238_PCLRE011_CP_100uA_10min_DEIS_3e_corrected_pico'
pico.set_pico(capture_size, samples_total, sampling_time, sampling_time_scale, saving_path)
pico.set_channel('PS5000A_CHANNEL_A', 'PS5000A_500MV')
pico.set_channel('PS5000A_CHANNEL_B', 'PS5000A_2V', 0.01)
pico.set_channel('PS5000A_CHANNEL_C', 'PS5000A_500MV')
pico.run_streaming_non_blocking(autoStop= False)

#%%
pico.stop()
pico.disconnect()

