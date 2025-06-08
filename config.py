#########################################
# LOCAL
# CONFIG
#########################################

import logging

SAMPLES_DIR = "."                       # The root directory containing the sample-sets. Example: "/media/" to look for samples on a USB stick / SD card
USE_BUTTONS = False                     # Set to True to use momentary buttons (connected to RaspberryPi's GPIO pins) to change preset
USE_I2C_7SEGMENTDISPLAY = False         # Set to True to use a 7-segment display via I2C
USE_SERIALPORT_MIDI = False             # Set to True to enable MIDI IN via SerialPort (e.g. RaspberryPi's GPIO UART pins)
USE_SYSTEMLED = False                   # Flashing LED after successful boot, only works on RPi/Linux
SERIALPORT_PORT = '/dev/ttyAMA0'
SERIALPORT_BAUDRATE = 31250

# Set MIDI Channel to listen. The numbering starts with '0'.
# Set to 'None' to listen to all MIDI channels.
MIDI_CHANNEL = 0
SOUNDFONT = None # "./KawaiStereoGrand.sf2"

DEFAULT_BANK = 0x0
DEFAULT_PROGRAM = 0x0
LOG_LEVEL = logging.DEBUG