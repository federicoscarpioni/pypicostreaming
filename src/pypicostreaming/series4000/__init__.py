# -*- coding: utf-8 -*-

import ctypes
import time
from datetime import datetime
import numpy as np
from np_rw_buffer import RingBuffer
from picosdk.ps4000 import ps4000 as ps
from picosdk.functions import adc2mV, assert_pico_ok
from dataclasses import dataclass
from threading import Thread
from pathlib import Path
from typing import TextIO
from collections import deque, namedtuple

@dataclass
class PicoChannel :
    name         : str
    vrange       : str
    buffer_small : int
    buffer_total : int
    status       : str
    irange       : int = None # Different only for measuring current over a resistor, must be a value in A


class Picoscope4000():
    def __init__(self):
        # Connect the instrument
        self.handle = ctypes.c_int16()
        self.status = {}
        self.connect()

    
    
    def connect(self):
        self.status["openunit"] = ps.ps4000OpenUnit(ctypes.byref(self.handle),
                                                    self.serial,
                                                    ps.PS4000_DEVICE_RESOLUTION[self.resolution])
        assert_pico_ok(self.status["openunit"]) # !!! It is not celar to me how and why of this function
        
    

    def time_unit_in_seconds(self, sampling_time, time_unit):
        time_convertion_factors = [1e-15, 1e-12, 1e-9, 1e-6, 1e-3, 1]
        return sampling_time * time_convertion_factors[time_unit]
    
    def _save_device_metadata(self, saving_dir):
        with open(saving_dir+'/device_metadata.txt', 'w') as f:
            f.write('PICO  DEVICE METADATA FILE\n'
                    f'Device handle id : {self.handle}\n')
        # !!! Add the call to ps4000GetUnitInfo for the details on the device     
    
    def set_pico(self, 
                 capture_size, 
                 samples_total, 
                 sampling_time, 
                 time_unit,
                 saving_path,
                 method = 'save_all_samples',
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
        self.method = method
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
        self._save_device_metadata(self.saving_dir)

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
        destEnd = self.nextSample + noOfSamples
        sourceEnd = startIndex + noOfSamples
        for ch in self.channels.values():
            # old
            # ch.buffer_total[self.nextSample:destEnd] = ch.buffer_small[startIndex:sourceEnd]
            # new
            ch.buffer_total.write(ch.buffer_small[startIndex:sourceEnd])
        self._online_computation()
        self.nextSample += noOfSamples
        if autoStop: 
            self.autoStopOuter = True
    
    def _save_measurement_metadata(self, saving_dir):
        with open (saving_dir+'/measurement_metadata.txt', 'w') as f:
            f.write('PICO MEASUREMENT METADATA FILE\n\n'
                    f'Starting of the measurement: {self.time_start}\n'
                    f'Capture size: {self.capture_size} Samples\n'
                    f'Samples total: {self.samples_total}\n'
                    f'Number captures: {self.number_captures}\n'
                    f'Sampling time: {self.time_step} s \n')
    
    def run_streaming_non_blocking(self, autoStop = True):
        ''' 
        Start the streaming of sampled signals from picoscope internal memory.
        '''
        now = datetime.now()
        self.time_start = now.strftime("%d/%m/%Y %H:%M:%S")
        self._save_measurement_metadata(self.saving_dir)
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
            print('> Pico msg: Acquisition completed!')
            
    
    def available_device(self):
        return ps.ps4000EnumerateUnits() # i don't understand how it works
    
    def convert_ADC_numbers (self, data, vrange, irange = None):
        ''' 
        Convert the data from the ADC into physical values.
        '''
        # !!! Here there is a minus only beacause the potentiosat has negative values
        # !!! Correct this for general
        numbers = np.multiply(-data, (self.channelInputRanges[vrange]/self.max_adc.value/1000), dtype = 'float32')
        if irange != None:
            numbers = np.multiply(numbers, irange)
        return numbers

    def convert2volts(self, signal, vrange):
        '''
        Convert data from integer of the ADC to values in voltage
        '''
        return np.multiply(-signal, (self.channelInputRanges[vrange]/self.max_adc.value/1000), dtype = 'float32')

    def convert_channel(self, channel):
         signal = self.convert2volts(channel.buffer_total,
                                             channel.vrange)
         # Convert to current (A) if the case
         if channel.irange is not None:
            signal = np.multiply(signal, channel.irange)
         return signal

    def convert_all_channels(self):
        '''
        Convert data from all the channel to voltage values and to current if
        specified in the channel definition.
        '''
        for ch in self.channels.values():
            ch.buffer_total = self.convert_channel(ch) # !!! This apporach is not ideal beacuse doubles tha ammount of RAM allocated

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
            signal = self.convert2volts(ch.buffer_total[0:self.nextSample],
                                    ch.vrange)
            # Convert to current (A) if the case
            if ch.irange is not None:
                signal = np.multiply(signal, ch.irange)
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
        '''
        Stop the picoscope.

        '''
        self.status["stop"] = ps.ps4000Stop(self.handle)
        assert_pico_ok(self.status["stop"])
        self.autoStopOuter = True
        print("> Pico msg: pico stopped!")
    
    
    def disconnect(self):
        '''
        Disconnect the instrument.
        '''
        self.status["close"] = ps.ps4000CloseUnit(self.handle)
        assert_pico_ok(self.status["close"])
        print("> Pico msg: Device disconnected.")
    


    def _save_channel_metadata(self, channel, saving_dir):
        with open(saving_dir+f'/metadata_channel{channel.name[-1]}.txt', 'w') as f:
            f.write(f'Name : {channel.name}\n'
                    f'Voltage range : {channel.vrange}\n'
                    f'Allocated driver buffer: {channel.buffer_small.size} Points\n'
                    f'Allocated software buffer : {self.samples_total} Points\n'
                    f'IRange : {channel.irange}\n'
                    f'Capture size: {self.capture_size} Points\n'
                    f'Samples total : {self.samples_total} Points\n'
                    f'Number captures : {self.number_captures} \n'
                    f'Sampling time : {self.sampling_time}\n'
                    f'Time unit : {self.time_unit}\n'
                    f'Device handle id : {self.handle}\n')
    
    def set_channel(self, channel, vrange, irange = None): 
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
                                                 RingBuffer((self.capture_size*self.number_captures,1), dtype=np.int16),
                                                 {},
                                                 irange)
        # Give an alias to the object for an easier reference
        ch = self.channels[channel[-1]]
        channelEnabled = True
        analogueOffset = 0.0
        ch.status["set_channel"] = ps.ps4000SetChannel(self.handle,
                                                        ps.PS4000_CHANNEL[ch.name],
                                                        channelEnabled,
                                                        ps.PS4000_COUPLING['PS4000_DC'],
                                                        ch.vrange,
                                                        analogueOffset)
        assert_pico_ok(ch.status["set_channel"])

        '''
        Register data buffer with driver.
        Allocate a buffer in the memory for store the complete sampled
        signal and gives the pointer of the buffer to the driver
        buffer_total must be Numpy array
        '''
        segmentIndex = 0 # the number of the memory segment to be used. The picoscope memory can be divided in segments and acquire different signals
        ch.status["setDataBuffers"] = ps.ps4000SetDataBuffer(self.handle,
                                                              ps.PS4000_CHANNEL[ch.name],
                                                              ch.buffer_small.ctypes.data_as(
                                                                  ctypes.POINTER(ctypes.c_int16)),
                                                              self.capture_size,
                                                              segmentIndex, 
                                                              ps.PS4000_RATIO_MODE['PS4000_RATIO_MODE_NONE'])
        assert_pico_ok(ch.status["setDataBuffers"])
        
        self._save_channel_metadata(ch, self.saving_dir)
