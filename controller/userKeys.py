#!/usr/bin/python3
#
#

###############################################################################
#### Test der Benutzertasten des Displays                                  ####
###############################################################################
import RPi.GPIO as GPIO
import time

class Userkeys:
    KEY_01 = 12
    KEY_02 = 16
    KEY_03 = 18
    TOUCH_PANEL = 7

    def __init__(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.KEY_01, GPIO.IN, pull_up_down = GPIO.PUD_UP)
        GPIO.setup(self.KEY_02, GPIO.IN, pull_up_down = GPIO.PUD_UP)
        GPIO.setup(self.KEY_03, GPIO.IN, pull_up_down = GPIO.PUD_UP)
        #GPIO.setup(self.TOUCH_PANEL, GPIO.OUT)
        #GPIO.output( self.TOUCH_PANEL, 0)

    def __del__(self):
        GPIO.cleanup()
    
    def getKeyStat(self):
        k1 = 0
        k2 = 0
        k3 = 0
        if GPIO.input(self.KEY_01) == 0:
            k1 = 1
        if GPIO.input(self.KEY_02) == 0:
            k2 = 1
        if GPIO.input(self.KEY_03) == 0:
            k3 = 1
        return k1 + ( k2 << 1 ) + ( k3 << 2 )

def main():
    myKeys = Userkeys()
    while True:
        keys = myKeys.getKeyStat()
        k1 = keys & 0x01
        k2 = (keys >> 1) & 0x01
        k3 = (keys >> 2) & 0x01
        print( "Key 1: %d, Key 2: %d, Key 3: %d" %(k1, k2, k3) )
        time.sleep( .2)

if __name__ == "__main__":
    main()
