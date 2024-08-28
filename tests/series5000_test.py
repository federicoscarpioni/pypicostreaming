'''
This is a test for the Picoscope class. 
'''

from pypicostreaming.series5000.series5000 import Picoscope5000a

# Measurment paramters
capture_size = 20
samples_total = 1000
sampling_time = 100
sampling_time_scale = 'PS5000A_MS'

# Connect i nstrument and perform the acquisiton
pico = Picoscope5000a('PS5000A_DR_14BIT')
saving_path = 'E:/Experimental_data/Federico/2024/python_software_test/2408281137_test_CP_full_dummy_3electrodes_pico_connected_sine_wave_smaller_IRange'
pico.set_pico(capture_size, samples_total, sampling_time, sampling_time_scale, saving_path)
pico.set_channel('PS5000A_CHANNEL_A', 'PS5000A_200MV')
pico.set_channel('PS5000A_CHANNEL_B', 'PS5000A_200MV', 0.0001)
pico.set_channel('PS5000A_CHANNEL_C', 'PS5000A_500MV')
pico.run_streaming_non_blocking(autoStop= True)

#%%
pico.stop()
pico.disconnect()

