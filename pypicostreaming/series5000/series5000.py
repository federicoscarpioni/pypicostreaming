# -*- coding: utf-8 -*-

import ctypes
import time
from datetime import datetime
import numpy as np
from picosdk.ps5000a import ps5000a as ps
from picosdk.functions import adc2mV, assert_pico_ok
from dataclasses import dataclass
from threading import Thread
from pathlib import Path
from typing import TextIO

@dataclass
class PicoChannel :
    name         : str
    vrange       : str
    buffer_small : int
    buffer_total : int
    status       : str
    saving_file  : TextIO
    irange       : int = None # Different only for measuring current over a resistor, must be a value in A


class Picoscope5000a():
    def __init__(self, serial, resolution):
        '''
        If serial is None, the driver will connect to the first connected device.
        
        Resolution must be one of the following:
        'PS5000A_DR_8BIT',
        'PS5000A_DR_12BIT',
        'PS5000A_DR_14BIT',
        'PS5000A_DR_15BIT',
        'PS5000A_DR_16BIT'}
        '''
        # Connect the instrument
        self.serial = serial
        self.resolution = resolution
        self.handle = ctypes.c_int16()
        self.status = {}
        self.connect()
    
    
    def connect(self):
        self.status["openunit"] = ps.ps5000aOpenUnit(ctypes.byref(self.handle),
                                                    self.serial,
                                                    ps.PS5000A_DEVICE_RESOLUTION[self.resolution])
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
        'PS5000A_FS': femtoseconds
        'PS5000A_PS': picoseconds
        'PS5000A_NS': nanoseconds
        'PS5000A_US': microseconds
        'PS5000A_MS': milliseconds
        'PS5000A_S' : seconds
        '''
        # Measurement parameters
        self.capture_size = capture_size
        self.samples_total = samples_total # Total must be an integer number of capture_size
        self.number_captures = int(self.samples_total/self.capture_size)
        self.sampling_time = ctypes.c_int32(sampling_time)
        self.time_unit = ps.PS5000A_TIME_UNITS[time_unit]
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
        if self.is_debug: print(f'Number of samples copied in the buffer: {noOfSamples}')
        for ch in self.channels.values():
            ch.buffer_total[self.nextSample:destEnd] = ch.buffer_small[startIndex:sourceEnd]
            if self.is_debug : 
                print('Channel'+ch.name[-1]+ ' small buffer:')
                print (ch.buffer_small)
        if self.is_debug: print('Copied small buffers to big buffers')
        self.nextSample += noOfSamples
        # if autoStop: 
        #     self.autoStopOuter = True
    
    
    def run_streaming_non_blocking(self, autoStop = True):
        ''' 
        Start the streaming of sampled signals from picoscope internal memory.
        '''
        self.time_start = datetime.now()
        self.status["runStreaming"] = ps.ps5000aRunStreaming(self.handle,
                                                            ctypes.byref(self.sampling_time),
                                                            self.time_unit,
                                                            0, # maxPreTriggerSamples
                                                            self.samples_total,
                                                            autoStop, 
                                                            1, # downsampleRatio
                                                            ps.PS5000A_RATIO_MODE['PS5000A_RATIO_MODE_NONE'],
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
        self.status["runStreaming"] = ps.ps5000aRunStreaming(self.handle,
                                                            ctypes.byref(self.sampling_time),
                                                            self.time_unit,
                                                            0, # maxPreTriggerSamples
                                                            self.samples_total,
                                                            autoStop, 
                                                            1, # downsampleRatio
                                                            ps.PS5000A_RATIO_MODE['PS5000A_RATIO_MODE_NONE'],
                                                            self.capture_size)
        assert_pico_ok(self.status["runStreaming"])
        print("> Pico msg: Acquisition started!")
        self.cFuncPtr = ps.StreamingReadyType(self.streaming_callback)
        self.get_data_loop()


    def _store_lates_data(self):
        for ch in self.channels.values():
            latest_data = self.convert2volts(ch.buffer_total, ch.vrange) # !!! This apporach is not ideal beacuse doubles tha ammount of RAM allocated
            # Convert to current (A) if the case 
            if ch.irange is not None: latest_data = np.muliply(ch.buffer_total, ch.irange)   
            ch.saving_file.write(latest_data)
            ch.saving_file.write('\n')

    def _close_saving_files(self):
        for ch in self.channels.values():
            ch.saving_file.close()
    
    def get_data_loop(self):
        '''
        Run the streaming from picoscope in a dedicated thread
        '''
        while self.autoStopOuter:
            self.wasCalledBack = False
            self.status["getStreamingLastestValues"] = ps.ps5000aGetStreamingLatestValues(self.handle, 
                                                                                          self.cFuncPtr, 
                                                                                          None) 
            self._store_lates_data()
            # !!! Here I can put the process part for online data elaboration
            if not self.wasCalledBack:
                # If we weren't called back by the driver, this means no data is ready. Sleep for a short while before trying
                # again.
                time.sleep(0.1)
        else:
            self._close_saving_files()
            print('> Pico msg: Acquisition completed!')
        # return self.channels
    
    def available_device(self):
        return ps.ps5000aEnumerateUnits() # i don't understand how it works
    
    
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
            ch.buffer_total = self.convert2volts(ch.buffer_total, ch.vrange) # !!! This apporach is not ideal beacuse doubles tha ammount of RAM allocated
            # Convert to current (A) if the case 
            if ch.irange is not None: ch.buffer_total = np.muliply(ch.buffer_total, ch.irange)

    
    def stop(self):
        '''
        Stop the picoscope.

        '''
        self.status["stop"] = ps.ps5000aStop(self.handle)
        assert_pico_ok(self.status["stop"])
        print("> Pico msg: pico stopped!")
    
    
    def disconnect(self):
        '''
        Disconnect the instrument.
        '''
        self.status["close"] = ps.ps5000aCloseUnit(self.handle)
        assert_pico_ok(self.status["close"])
        print("> Pico msg: Device disconnected.")
    
    
    
    def set_channel(self, channel, vrange, saving_path, IRange = None): 
        '''
        Set channel of the connetted picoscope.
        Parameters:
        channel : str
            Name of the channel to set
            The allowable values are:
                PS5000A_CHANNEL_A – analog channel A
                PS5000A_CHANNEL_B – analog channel B
                PS5000A_CHANNEL_C – analog channel C (4-channel scopes only)
                PS5000A_CHANNEL_D – analog channel D (4-channel scopes only)
                PS5000A_EXTERNAL – external trigger input (not on MSOs)
                PS5000A_TRIGGER_AUX – reserved
                PS5000A_DIGITAL_PORT0 – digital channels 0–7 (MSOs only)
                PS5000A_DIGITAL_PORT1 – digital channels 8–15 (MSOs only)
                PS5000A_DIGITAL_PORT2 – reserved
                PS5000A_DIGITAL_PORT3 – reserved
                PS5000A_PULSE_WIDTH_SOURCE – pulse width qualifier*
        
        vrange : str
            Table of available ranges:
                
            idx range(str)      voltage range
            0   PS5000A_10MV     ±10 mV
            1   PS5000A_20MV     ±20 mV
            2   PS5000A_50MV     ±50 mV
            3   PS5000A_100MV    ±100 mV
            4   PS5000A_200MV    ±200 mV
            5   PS5000A_500MV    ±500 mV
            6   PS5000A_1V       ±1 V
            7   PS5000A_2V       ±2 V
            8   PS5000A_5V       ±5 V
            9   PS5000A_10V      ±10 V
            10  PS5000A_20V      ±20 V
            11  PS5000A_50V      ±50 V
    
            
        index of the channelInputRanges list which contains values in mV
        channelInputRanges = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000]
        '''
        
        saving_dir = saving_path+'/pico_aquisition'
        Path(saving_dir).mkdir(parents=True, exist_ok=True)
        saving_file = open(saving_dir + f'/channel{channel[-1]}.txt', 'w')
        
        self.channels[channel[-1]] = PicoChannel(channel, 
                                                 ps.PS5000A_RANGE[vrange],
                                                 np.zeros(shape=self.capture_size, dtype=np.int16), # ADC is 16 bit 
                                                 np.zeros(shape=self.capture_size*self.number_captures, dtype=np.int16),
                                                 {},
                                                 saving_file,
                                                 IRange)
        # Give an alias to the object for an easier reference
        ch = self.channels[channel[-1]]
        channelEnabled = True
        analogueOffset = 0.0
        ch.status["set_channel"] = ps.ps5000aSetChannel(self.handle,
                                                        ps.PS5000A_CHANNEL[ch.name],
                                                        channelEnabled,
                                                        ps.PS5000A_COUPLING['PS5000A_DC'],
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
        ch.status["setDataBuffers"] = ps.ps5000aSetDataBuffer(self.handle,
                                                              ps.PS5000A_CHANNEL[ch.name],
                                                              ch.buffer_small.ctypes.data_as(
                                                                  ctypes.POINTER(ctypes.c_int16)),
                                                              self.capture_size,
                                                              segmentIndex, 
                                                              ps.PS5000A_RATIO_MODE['PS5000A_RATIO_MODE_NONE'])
        assert_pico_ok(ch.status["setDataBuffers"])
        
        
