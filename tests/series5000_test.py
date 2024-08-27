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
pico.set_pico(capture_size, samples_total, sampling_time, sampling_time_scale)
saving_path = 'E:/Experimental_data/Federico/2024/python_software_test/2408271809_test_full_dummy_3electrodes_pico_connected_sine_wave'
pico.set_channel('PS5000A_CHANNEL_A', 'PS5000A_50MV', saving_path)
pico.set_channel('PS5000A_CHANNEL_B', 'PS5000A_10MV', saving_path, 0.01)
pico.set_channel('PS5000A_CHANNEL_C', 'PS5000A_100MV', saving_path)
pico.run_streaming_non_blocking(autoStop= True)

#%%
pico.stop()
pico.disconnect()

