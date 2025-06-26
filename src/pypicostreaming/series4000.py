import ctypes
import time
import json
from datetime import datetime
import numpy as np
from npbuffer import NumpyCircularBuffer
from picosdk.ps4000 import ps4000 as ps
from picosdk.functions import assert_pico_ok
from dataclasses import dataclass
from threading import Thread
from pathlib import Path

@dataclass
class PicoChannel :
    name         : str
    vrange       : str
    buffer_small : int
    buffer_total : NumpyCircularBuffer
    status       : str
    conv_factor  : int = None
    signal_name  : str = None


class Picoscope4000():
    def __init__(self):
        '''
        Connect the instrument (connects always to the erlriest plugged to the 
        computer that is not already in use).
        '''
        self.handle = ctypes.c_int16()
        self.status = {}
        self.connect()
    
    
    def connect(self):
        self.status["openunit"] = ps.ps4000OpenUnit(ctypes.byref(self.handle))
        assert_pico_ok(self.status["openunit"]) 
    

    def time_unit_in_seconds(self, sampling_time, time_unit):
        time_convertion_factors = [1e-15, 1e-12, 1e-9, 1e-6, 1e-3, 1]
        return sampling_time * time_convertion_factors[time_unit]

    
    def set_pico(self, 
                 capture_size, 
                 samples_total, 
                 sampling_time, 
                 time_unit,
                 is_debug = False):
        '''
        Set parameters valid for the acquisition on all channels and variables
        for the data saving on allocated memory and autostop.
        Call this function again to start a new acquisition withouth the need 
        to disconnect and reconnect the device (i.e. keeping the same class
        istance)
        
        Available time units:
        'PS4000_FS': femtoseconds
        'PS4000_PS': picoseconds
        'PS4000_NS': nanoseconds
        'PS4000_US': microseconds
        'PS4000_MS': milliseconds
        'PS4000_S' : seconds
        '''
        # Measurement parameters
        self.capture_size = capture_size
        self.samples_total = samples_total # Total must be an integer number of capture_size
        self.number_captures = int(self.samples_total/self.capture_size)
        self.sampling_time = ctypes.c_int32(sampling_time)
        self.time_unit = ps.PS4000_TIME_UNITS[time_unit]
        self.time_step = self.time_unit_in_seconds(sampling_time, self.time_unit)
        self.is_debug = is_debug
        # Software parameters
        self.channels = {} # Dictionary containing all the information of set up channels
        self.nextSample = 0
        self.autoStopOuter = False
        self.wasCalledBack = False
        self.max_adc = ctypes.c_int16(32767) # 16bit convertion
        self.channelInputRanges = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000]

        self.saving_dir = saving_path+'/pico_aquisition'
        Path(self.saving_dir).mkdir(parents=True, exist_ok=True)  


    def _online_computation(self):
        """
        Here can be put code for make computation on new data. Ideally operataion
        can be included in child classes expanding this one that will be called
        inside the callback after retriving new data from the instrument.
        """
        pass


    def streaming_callback(self, 
                           handle, 
                           noOfSamples, 
                           startIndex, 
                           overflow, 
                           triggerAt, 
                           triggered, 
                           autoStop, 
                           param):
        '''
        The callback function called by the Picoscope driver. Slightly modified
        from the example to include the class attributes.
        '''
        self.wasCalledBack = True
        sourceEnd = startIndex + noOfSamples
        for ch in self.channels.values():
            ch.buffer_total.push(ch.buffer_small[startIndex:sourceEnd])
        self._online_computation()
        self.nextSample += noOfSamples
        if autoStop: 
            self.autoStopOuter = True
            
    
    def run_streaming_non_blocking(self, autoStop = True):
        ''' 
        Start the streaming of sampled signals from picoscope internal memory.
        '''
        self.save_metadata(autoStop)
        self.status["runStreaming"] = ps.ps4000RunStreaming(self.handle,
                                                            ctypes.byref(self.sampling_time),
                                                            self.time_unit,
                                                            0, # maxPreTriggerSamples
                                                            self.samples_total,
                                                            autoStop, 
                                                            1, # downsampleRatio
                                                            self.capture_size)
        assert_pico_ok(self.status["runStreaming"])
        print("> Pico msg: Acquisition started!")
        self.cFuncPtr = ps.StreamingReadyType(self.streaming_callback)
        get_data_thread = Thread( target=(self.get_data_loop) )
        get_data_thread.start()
        
    
    def run_streaming_blocking(self, autoStop = True):
        ''' 
        Start the streaming of sampled signals from picoscope internal memory.
        '''
        self.save_metadata(autoStop)
        self.status["runStreaming"] = ps.ps4000RunStreaming(self.handle,
                                                            ctypes.byref(self.sampling_time),
                                                            self.time_unit,
                                                            0, # maxPreTriggerSamples
                                                            self.samples_total,
                                                            autoStop, 
                                                            1, # downsampleRatio
                                                            self.capture_size)
        assert_pico_ok(self.status["runStreaming"])
        print("> Pico msg: Acquisition started!")
        self.cFuncPtr = ps.StreamingReadyType(self.streaming_callback)
        self.get_data_loop()
        
    
    def get_data_loop(self):
        '''
        Run the streaming from picoscope in a dedicated thread
        '''
        while not self.autoStopOuter:
            self.wasCalledBack = False
            self.status["getStreamingLastestValues"] = ps.ps4000GetStreamingLatestValues(self.handle, 
                                                                                          self.cFuncPtr, 
                                                                                          None)
            if not self.wasCalledBack:
                # If we weren't called back by the driver, this means no data is ready. Sleep for a short while before trying
                # again.
                time.sleep(0.001)
        else:
            print('> Pico msg: Acquisition completed!')
    
    def available_device(self):
        return ps.ps4000EnumerateUnits() 
    
    
    def convert_ADC_numbers(self, data, vrange, conv_factor = None):
        ''' 
        Convert the data from the ADC into physical values.
        '''
        # !!! Here there is a minus only beacause the potentiosat has negative values
        # !!! Correct this for general use case
        numbers = np.multiply(-data, (self.channelInputRanges[vrange]/self.max_adc.value/1000), dtype = 'float32')
        if conv_factor != None:
            numbers = np.multiply(numbers, conv_factor)
        return numbers
    
    
    def convert2volts(self, signal, vrange):
        '''
        Convert data from integer of the ADC to values in voltage
        '''
        return np.multiply(-signal, (self.channelInputRanges[vrange]/self.max_adc.value/1000), dtype = 'float32')
        
    
    def convert_channel(self, channel):
         signal = self.convert2volts(channel.buffer_total.empty(),
                                             channel.vrange)
         # Convert to current (A) if the case
         if channel.conv_factor is not None:
            signal = np.multiply(signal, channel.conv_factor)
         return signal

    def get_all_signals(self):
        '''
        Convert data from all the channel to voltage values and to current if
        specified in the channel definition.
        '''
        signal_list = []
        for ch in self.channels.values():
            signal_list.append(self.convert_channel(ch))
        return tuple(signal_list)
    
    def save_signal(self, channel, subfolder_name = None):
        if subfolder_name is None :
            saving_file_path = self.saving_dir
        else:
            saving_file_path = self.saving_dir + subfolder_name
            Path(saving_file_path).mkdir(parents=True, exist_ok=True)
        file_name = saving_file_path + f'/channel{channel.name[-1]}.npy'
        np.save(file_name, channel.buffer_total)

    def save_signals(self, subfolder_name=None):
        for ch in self.channels.values():
            self.save_signal(ch, subfolder_name)


    def save_intermediate_signals(self, subfolder_name):
        '''
        Save part of the buffer. Typically used when autostop is False or one doesn't know the lenght of the signal to sample
        '''
        for ch in self.channels.values():
            signal = self.convert2volts(ch.buffer_total.empty(),
                                    ch.vrange)
            # Convert to current (A) if the case
            if ch.conv_factor is not None:
                signal = np.multiply(signal, ch.conv_factor)
            if subfolder_name is None:
                saving_file_path = self.saving_dir
            else:
                saving_file_path = self.saving_dir + subfolder_name
                Path(saving_file_path).mkdir(parents=True, exist_ok=True)
            file_name = saving_file_path + f'/channel{ch.name[-1]}.npy'
            np.save(file_name, signal)
            print(f'File saved {ch.name}')
        self.reset_buffer()


    def reset_buffer(self):
        self.nextSample = 0
    

    def stop(self):
        self.status["stop"] = ps.ps4000Stop(self.handle)
        assert_pico_ok(self.status["stop"])
        self.autoStopOuter = True
        print("> Pico msg: pico stopped!")
    
    
    def disconnect(self):
        self.status["close"] = ps.ps4000CloseUnit(self.handle)
        assert_pico_ok(self.status["close"])
        print("> Pico msg: Device disconnected.")
    
    
    def set_channel(self, channel, vrange, signal_name = None, conv_factor = None): 
        '''
        Set channel of the connetted picoscope.
        Parameters:
        channel : str
            Name of the channel to set
            The allowable values are:
                PS4000A_CHANNEL_A … PS4000A_CHANNEL_B (PicoScope 4224A)
                PS4000A_CHANNEL_A … PS4000A_CHANNEL_D (PicoScope 4424A and 4444)
                PS4000A_CHANNEL_A … PS4000A_CHANNEL_H (PicoScope 4824A and 4824)
        
        vrange : str
            Table of available ranges:
                
            idx range(str)      voltage range
            0   PS4000_10MV     ±10 mV
            1   PS4000_20MV     ±20 mV
            2   PS4000_50MV     ±50 mV
            3   PS4000_100MV    ±100 mV
            4   PS4000_200MV    ±200 mV
            5   PS4000_500MV    ±500 mV
            6   PS4000_1V       ±1 V
            7   PS4000_2V       ±2 V
            8   PS4000_5V       ±5 V
            9   PS4000_10V      ±10 V
            10  PS4000_20V      ±20 V
            11  PS4000_50V      ±50 V
            12  PS4000_100V     ±100 V
            
        index of the channelInputRanges list which contains values in mV
        channelInputRanges = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000]
        '''


        self.channels[channel[-1]] = PicoChannel(channel, 
                                                 ps.PS4000_RANGE[vrange],
                                                 np.zeros(shape=self.capture_size, dtype=np.int16), # ADC is 16 bit 
                                                 np.zeros(shape=self.capture_size*self.number_captures, dtype=np.int16),
                                                 {},
                                                 conv_factor,
                                                 signal_name)
        # Give an alias to the object for an easier reference
        ch = self.channels[channel[-1]]
        ch.status["set_channel"] = ps.ps4000SetChannel(self.handle,
                                                       ps.PS4000_CHANNEL[ch.name],
                                                       True,  # In the example, 1 is used
                                                       1,
                                                       ch.vrange)
        assert_pico_ok(ch.status["set_channel"])

        '''Allocate a buffer in the memory for store the complete sampled
        signal and gives the pointer of the buffer to the driver
        buffer_total must be Numpy array
        '''
        ch.status["setDataBuffers"] = ps.ps4000SetDataBuffers(self.handle,  # !!! Perché la funzione con la s???
                                                              ps.PS4000_CHANNEL[ch.name],
                                                              ch.buffer_small.ctypes.data_as(
                                                                  ctypes.POINTER(ctypes.c_int16)),
                                                              None,
                                                              self.capture_size)
        assert_pico_ok(ch.status["setDataBuffers"])
        
    
    def empty_buffers(self):
        for ch in self.channels.values():
            ch.buffer_total.empty()
    

    def bandwith_limiter(self, channel, enabled = 1):
        self.status["setBandwidthFilter"] = ps.ps4000SetBwFilter(self.handle,
                                                                 ps.PS4000_CHANNEL[channel],
                                                                 enabled)
        assert_pico_ok(self.status["setBandwidthFilter"])
    
    
    def save_metadata(self, autoStop):
        metadata_dict = {
            'Starting time' : datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            'Device serial': self.serial,
            'Resolution': self.resolution,
            'Circular buffer size (Sa)': self.samples_total,
            'Driver buffer size (Sa)' : self.capture_size,
            'Sampling time (s)': self.time_step,
            'Auto stop' : autoStop,
        }
        cahnnels_metadata = dict()
        for ch in self.channels.values():
            channel_info = {
                'Voltage range' : ch.vrange,
                'Converting factor' : ch.conv_factor,
                'Signal name' : ch.signal_name,
            }
            cahnnels_metadata.update(
                {ch.name : channel_info}
            )
        metadata_dict.update(cahnnels_metadata)
        with open(self.saving_dir +'/metadata_pico.json', 'w') as fp:
            json.dump(metadata_dict, fp)
