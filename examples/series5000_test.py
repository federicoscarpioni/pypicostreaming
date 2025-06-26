'''
This is a test for the Picoscope class. 
'''

from pypicostreaming import Picoscope5000a

# Measurment paramters
capture_size = 100000
samples_total = 100000
sampling_time = 1
sampling_time_scale = 'PS5000A_MS'

# Connect i nstrument and perform the acquisiton
pico = Picoscope5000a('PS5000A_DR_14BIT')
saving_path = 'E:/Experimental_data/Federico/2024/python_software_test/2501091240_test_pico_direct_awg'
pico.set_pico(capture_size, samples_total, sampling_time, sampling_time_scale, saving_path)
pico.set_channel('PS5000A_CHANNEL_A', 'PS5000A_500MV')
# pico.set_channel('PS5000A_CHANNEL_B', 'PS5000A_2V', 0.01)
# pico.set_channel('PS5000A_CHANNEL_C', 'PS5000A_500MV')
pico.run_streaming_non_blocking(autoStop= True)

#%%
pico.stop()
pico.disconnect()
