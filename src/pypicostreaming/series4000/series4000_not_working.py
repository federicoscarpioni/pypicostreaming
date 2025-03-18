import ctypes
import time
from datetime import datetime
import numpy as np
from picosdk.ps4000 import ps4000 as ps
from picosdk.functions import  assert_pico_ok
from dataclasses import dataclass
import queue
from threading import Thread

@dataclass 
class PicoChannel :
    name            : str
    vrange          : str
    buffer_small    : int
    maximum_samples : int
    status          : str
    irange          : int = None # Different only for measuring current over a resistor, must be a value in A

class PicoScope4000():
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
        endIndex = startIndex + noOfSamples
        if self.is_debug: print(f'Number of new samples in the buffer: {noOfSamples}')
        for ch in self.channels.values():
            print(ch.buffer_small[startIndex:endIndex])
            #ch.signal.put(ch.buffer_small[startIndex:startIndex + noOfSamples])
        self.nextSample += noOfSamples

    
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
        while self.autoStopOuter:
            self.wasCalledBack = False
            self.status["getStreamingLastestValues"] = ps.ps4000GetStreamingLatestValues(self.handle, 
                                                                                          self.cFuncPtr, 
                                                                                          None)
            if not self.wasCalledBack:
                # If we weren't called back by the driver, this means no data is ready. Sleep for a short while before trying
                # again.
                time.sleep(1)
        else:
            print('> Pico msg: Acquisition completed!')
        
    
    def available_device(self):
        return ps.ps4000EnumerateUnits() # i don't understand how it works
    
    
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
            ch.signal = self.convert2volts(ch.signal, ch.vrange)
            # Convert to current (A) if the case 
            if ch.irange is not None: ch.signal = np.muliply(ch.signal, ch.irange)

    
    def stop(self):
        '''
        Stop the picoscope.

        '''
        self.status["stop"] = ps.ps4000Stop(self.handle)
        assert_pico_ok(self.status["stop"])
        print("> Pico msg: pico stopped!")
    
    
    def disconnect(self):
        '''
        Disconnect the instrument.
        '''
        self.status["close"] = ps.ps4000CloseUnit(self.handle)
        assert_pico_ok(self.status["close"])
        print("> Pico msg: Device disconnected.")
    
    
    
    def set_channel(self, channel, vrange): 
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
                                                 {})
        # Give an alias to the object for an easier reference
        ch = self.channels[channel[-1]]
        ch.signal = queue.Queue()
        ch.status["set_channel"] = ps.ps4000SetChannel(self.handle,
                                                       ps.PS4000_CHANNEL[ch.name],
                                                       True,  # In the example, 1 is used
                                                       1,
                                                       ch.vrange)
        assert_pico_ok(ch.status["set_channel"])

        '''Allocate a buffer in the memory for storing the sampled
        signal and gives the pointer of the buffer to the driver
        '''
        ch.status["setDataBuffers"] = ps.ps4000SetDataBuffer(self.handle,  
                                                            ps.PS4000_CHANNEL[ch.name],
                                                            ch.buffer_small.ctypes.data_as(
                                                                ctypes.POINTER(ctypes.c_int16)),
                                                            self.capture_size)
        assert_pico_ok(ch.status["setDataBuffers"])
    
    
    

    def bandwith_limiter(self, channel, enabled = 1):
        self.status["setBandwidthFilter"] = ps.ps4000SetBwFilter(self.handle,
                                                                 ps.PS4000_CHANNEL[channel],
                                                                 enabled)
        assert_pico_ok(self.status["setBandwidthFilter"])
    
