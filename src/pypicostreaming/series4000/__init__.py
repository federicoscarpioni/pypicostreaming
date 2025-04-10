# -*- coding: utf-8 -*-

import ctypes
import time
from datetime import datetime
import numpy as np
from picosdk.ps4000 import ps4000 as ps
from picosdk.functions import adc2mV, assert_pico_ok
from dataclasses import dataclass
from threading import Thread
from typing import TextIO
from pathlib import Path

@dataclass
class PicoChannel :
    name         : str
    vrange       : str
    buffer_small : int
    buffer_total : int
    status       : str
    saving_file  : TextIO
    irange       : int = None # Different only for measuring current over a resistor, must be a value in A

class Picoscope4000():
    def __init__(self):
        # Connect the instrument
        self.handle = ctypes.c_int16()
        self.status = {}
        self.connect()
    
    
    def connect(self):
        self.status["openunit"] = ps.ps4000OpenUnit(ctypes.byref(self.handle))
        assert_pico_ok(self.status["openunit"]) # !!! It is not celar to me how and why of this function
        
    

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
        self.dt_in_seconds = self.time_unit_in_seconds(sampling_time, self.time_unit)
        self.is_debug = is_debug
        # Software parameters
        self.channels = {} # Dictionary containing all the information of set up channels
        self.nextSample = 0
        self.autoStopOuter = False
        self.wasCalledBack = False
        self.max_adc = ctypes.c_int16(32767) # 16bit convertion
        self.channelInputRanges = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000]



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
        destEnd = self.nextSample + noOfSamples
        sourceEnd = startIndex + noOfSamples
        for ch in self.channels.values():
            ch.buffer_total[self.nextSample:destEnd] = ch.buffer_small[startIndex:sourceEnd]
            np.savetxt(ch.saving_file, 
                       self.convert_ADC_numbers(ch.buffer_total[self.nextSample:destEnd],ch.vrange, ch.irange),
                       delimiter = '\t')
        self.nextSample += noOfSamples
        if autoStop: 
            self.autoStopOuter = True
            
    
    def run_streaming_non_blocking(self, autoStop = False):
        ''' 
        Start the streaming of sampled signals from picoscope internal memory.
        '''
        self.time_start = datetime.now()
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
        self.time_start = datetime.now()
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
            self._close_saving_files()
            print('> Pico msg: Acquisition completed!')
    
    def available_device(self):
        return ps.ps4000EnumerateUnits() # i don't understand how it works
    
    
    def convert_ADC_numbers (self, data, vrange, irange = None):
        ''' 
        Convert the data from the ADC into physical values.
        '''
        numbers = np.multiply(-data, (self.channelInputRanges[vrange]/self.max_adc.value/1000), dtype = 'float32')
        if irange != None:
            numbers = np.multiply(numbers, irange)
        return numbers
    
    
    def convert2volts(self, signal, vrange):
        '''
        Convert data from integer of the ADC to values in voltage
        '''
        return np.multiply(-signal, (self.channelInputRanges[vrange]/self.max_adc.value/1000), dtype = 'float32')
        


    
    def convert_all_channels(self):
        '''
        Convert data from all the channel to voltage values and to current if
        specified in the channel definition.
        '''
        for ch in self.channels.values():
            ch.buffer_total = self.convert2volts(ch.buffer_total, ch.vrange)
            # Convert to current (A) if the case 
            if ch.irange is not None: ch.buffer_total = np.multiply(ch.buffer_total, ch.irange)

    
    def stop(self):
        '''
        Stop the picoscope.

        '''
        self.status["stop"] = ps.ps4000Stop(self.handle)
        assert_pico_ok(self.status["stop"])
        self.autoStopOuter = True
        self._close_saving_files
        print("> Pico msg: pico stopped!")
    
    
    def disconnect(self):
        '''
        Disconnect the instrument.
        '''
        self.status["close"] = ps.ps4000CloseUnit(self.handle)
        assert_pico_ok(self.status["close"])
        print("> Pico msg: Device disconnected.")
    
    # def _store_latest_data(self, file, data):
    #     for ch in self.channels.values():
    #         latest_data = self.convert2volts(ch.buffer_total[ch.latest_writing_position:ch.newest_data_position], ch.vrange) # !!! This apporach is not ideal beacuse doubles tha ammount of RAM allocated
    #         # Convert to current (A) if the case 
    #         if ch.irange is not None: latest_data = np.muliply(ch.buffer_total, ch.irange)   
    #         np.savetxt(ch.saving_file, latest_data, delimiter = '\t')
    #         # ch.saving_file.write('\n')
    #         ch.latest_writing_position = ch.newest_data_position
    
    def _close_saving_files(self):
        for ch in self.channels.values():
            ch.saving_file.close()
    
    def _save_channel_metadata(self, channel, saving_dir):
        with open(saving_dir+f'/metadata_channel{channel.name[-1]}.txt', 'w') as f:
            f.write(f'Name : {channel.name}\n'
                    f'Voltage range : {channel.vrange}\n'
                    f'Allocated driver buffer: {channel.buffer_small.size} Points\n'
                    f'Allocated software buffer : {channel.buffer_total.size} Points\n'
                    f'IRange : {channel.irange}\n'
                    f'Capture size: {self.capture_size} Points\n'
                    f'Samples total : {self.samples_total} Points\n'
                    f'Number captures : {self.number_captures} \n'
                    f'Sampling time : {self.sampling_time}\n'
                    f'Time unit : {self.time_unit}\n'
                    f'Device handle id : {self.handle}\n')

    
    def set_channel(self, channel, vrange, saving_path, irange = None): 
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
        # Create file for saving 
        saving_dir = saving_path+'/pico_aquisition'
        Path(saving_dir).mkdir(parents=True, exist_ok=True)
        saving_file = open(saving_dir + f'/channel{channel[-1]}.txt', 'w')
        # Create header for the file
        if irange == None:
            saving_file.write('Voltage/V\n')
        else:
            saving_file.write('Current/A\n')

        self.channels[channel[-1]] = PicoChannel(channel, 
                                                 ps.PS4000_RANGE[vrange],
                                                 np.zeros(shape=self.capture_size, dtype=np.int16), # ADC is 16 bit 
                                                 np.zeros(shape=self.capture_size*self.number_captures, dtype=np.int16),
                                                 {},
                                                 saving_file,
                                                 irange)
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
        
        self._save_channel_metadata(ch, saving_dir)
    
    
    

    def bandwith_limiter(self, channel, enabled = 1):
        self.status["setBandwidthFilter"] = ps.ps4000SetBwFilter(self.handle,
                                                                 ps.PS4000_CHANNEL[channel],
                                                                 enabled)
        assert_pico_ok(self.status["setBandwidthFilter"])
    
    
    def reinitialize_channels(self):
        '''
        Re-initilize current used channels for a new acquisition. 
        '''
        self.nextSample = 0
        self.autoStopOuter = False
        self.wasCalledBack = False
        for ch in self.channels.values():
            # # Re-initilize data of each channel
            # ch = PicoChannel(ch.name,
            #                   ch.vrange,
            #                   ch.buffer_small,  # give the old allocated array to not waste time on reallocating a lot of memory
            #                   ch.buffer_total,
            #                   {})
            # # Point the small buffer position to the driver
            # ps.ps4000SetDataBuffers(self.handle,  # !!! Perché la funzione con la s???
            #                         ps.PS4000_CHANNEL[ch.name],
            #                         ch.buffer_small.ctypes.data_as(
            #                             ctypes.POINTER(ctypes.c_int16)),
            #                         None,
            #                         self.capture_size)
            
            # New idea
            ch.buffer_total[0:] = 0
