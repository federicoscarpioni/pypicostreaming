'''
This is a test for the Picoscope class. It collect data on channel A for 
50 seconds at 0.1 seconds time step.
'''

from pypicostreaming import PicoScope4000

# Measurment paramters
capture_size = 20
samples_total = 1000
sampling_time = 100
sampling_time_scale = 'PS4000_MS'

# Connect i nstrument and perform the acquisiton
pico4000 = PicoScope4000()
pico4000.set_pico(capture_size, samples_total, sampling_time, sampling_time_scale, is_debug = True)
saving_path = 'E:/Experimental_data/Federico/2024/python_software_test/2408271741_test_full_dummy_3electrodes_pico_connected_sine_wave'
pico4000.set_channel('PS4000_CHANNEL_A', 'PS4000_50MV', saving_path)
pico4000.set_channel('PS4000_CHANNEL_B', 'PS4000_50MV', saving_path, 0.1)
pico4000.run_streaming_non_blocking(autoStop=1)

#%%
pico4000.stop()
pico4000.disconnect()


