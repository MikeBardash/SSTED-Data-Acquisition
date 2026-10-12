# get_remote_data.py
# just take readings from the pi
# M. Bardash

from cmath import sin
import time
import math
import requests
from datetime import datetime
import random

class MockSignalSource:
    def __init__(self):
        self.start_time = time.perf_counter()
        self.long_period = 1200.00
        self.short_period = 30.00

    def get_voltage(self):
        # Simulate a voltage reading by returning a random value between 0 and 5 volts
        slow_envelope = 1 + math.sin(2 * 3.14159 * (time.perf_counter() - self.start_time) / self.long_period)
        fast_envelope = 1 + math.sin(2 * 3.14159 * (time.perf_counter() - self.start_time) / self.short_period)
        voltage = 6 - ( slow_envelope * fast_envelope + random.uniform(0, 0.3) )
        return voltage

mock_volts = None

class RemoteVoltage():
    def __init__(self, url="http://raspberrypi:10001/detector_voltage", test=False ):        
        # URL for the detector voltage service
        self.url = url
        self.test = test
        self.session = requests.Session()

    # define the method that makes the ReST request - this is causing a problem with exceptions
    # so we've moved everything here
    def get_remote_voltage(self):
        while( True ):
            try:
                #If this is a test then just return a mock random voltage between 0 and 5
                if self.test:
                    global mock_volts
                    if mock_volts is None:
                        mock_volts = MockSignalSource()
                    time.sleep(0.2)
                    return mock_volts.get_voltage()
                
                #Get a voltage via a ReST call
                response = self.session.get( self.url )
                voltage = response.text
                response.close()
                return float(voltage)
            except Exception as except_instance:
                print( "In exception - ", except_instance )
                time.sleep(2)

if __name__ == '__main__':
    voltage = RemoteVoltage()
    while True:
        print( "Time: ", datetime.now(), "    Voltage: ", voltage.get_remote_voltage() )
