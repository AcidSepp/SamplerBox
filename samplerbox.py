#
#  SamplerBox
#
#  author:    Joseph Ernest (twitter: @JosephErnest, mail: contact@samplerbox.org)
#  url:       http://www.samplerbox.org/
#  license:   Creative Commons ShareAlike 3.0 (http://creativecommons.org/licenses/by-sa/3.0/)
#
#  samplerbox.py: Main file (now requiring at least Python 3.7)
#

#########################################
# IMPORT
# MODULES
#########################################

import configparser
import fluidsynth
import logging
import os
import rtmidi
import sys
import threading
import time
from pathlib import Path

configparser = configparser.ConfigParser({
    "SAMPLES_DIR": os.getcwd(),
    "USE_BUTTONS": "False",
    "USE_I2C_7SEGMENTDISPLAY": "False",
    "USE_SERIALPORT_MIDI": "False",
    "USE_SYSTEMLED": "False",
    "SERIALPORT_PORT": "/dev/ttyAMA0",
    "SERIALPORT_BAUDRATE": "31250",
    "MIDI_CHANNEL": "-1",
    "SOUNDFONT": "None",  # "./KawaiStereoGrand.sf2"
    "BANK": "0",
    "PROGRAM": "0",
    "LOG_LEVEL": "INFO",
    "GAIN": "1.0"
})

configparser.read('config.ini')

logging.basicConfig(stream=sys.stdout, level=configparser["samplerbox"]["LOG_LEVEL"])
logger = logging.getLogger(name="SamplerBox")

program = int(configparser["samplerbox"]["PROGRAM"])
bank = int(configparser["samplerbox"]["BANK"])

fs = fluidsynth.Synth(gain=float(configparser["samplerbox"]["GAIN"]))
fs.setting('audio.driver', 'pulseaudio')
fs.setting('audio.periods', '2')
fs.setting('audio.period-size', '64')
fs.start()

directory = Path(configparser["samplerbox"]["SAMPLES_DIR"])
sf2_files = [f.name for f in directory.glob("*.sf2") if f.is_file()]

for filename in sf2_files:
    sfid = fs.sfload(filename)
    logger.info(f"Loading soundfont from file: {filename}")

fs.bank_select(0, bank)
fs.program_change(0, program)
logger.info(f"Loading bank={bank} programm={program}")

MIDI_CHANNEL = int(configparser["samplerbox"]["MIDI_CHANNEL"])

def forwaredToFluidSynt(message):
    global program
    messagetype = message[0] >> 4
    messagechannel = (message[0] & 15)
    note = message[1] if len(message) > 1 else None
    velocity = message[2] if len(message) > 2 else None
    logger.debug(f"Received MIDI message: type={messagetype} channel={messagechannel} note={note} velocity={velocity}")

    if MIDI_CHANNEL != -1 and messagechannel != MIDI_CHANNEL:
        logger.debug(f"Not forwarding to fluidsynth because the channel={messagechannel} does not the configured channel={MIDI_CHANNEL}")
        return

    if messagetype == 0x9:  # Note on
        logger.debug(f"Forwarding NOTE ON to fluidsynth.")
        fs.noteon(0, note, velocity)
    elif messagetype == 0x8 or (messagetype == 9 and velocity == 0):  # Note off
        logger.debug(f"Forwarding NOTE OFF to fluidsynth.")
        fs.noteoff(0, note)
    elif messagetype == 0xC:  # Program change
        logger.debug(f"Forwarding Program Change to fluidsynth.")
        program = note
        fs.program_change(0, note, velocity)
    elif messagetype == 0xB:  # CC
        logger.debug(f"Forwarding CC to fluidsynth.")
        fs.cc(0, note, velocity)

class MidiInputHandler:
    def __call__(self, event, data=None):
        message, deltatime = event
        forwaredToFluidSynt(message)


#########################################
# BUTTONS THREAD (RASPBERRY PI GPIO)
#
#########################################

if configparser["samplerbox"]["USE_BUTTONS"] == "True":
    import RPi.GPIO as GPIO

    lastbuttontime = 0


    def Buttons():
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(18, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        global program, lastbuttontime
        while True:
            now = time.time()
            if not GPIO.input(18) and (now - lastbuttontime) > 0.2:
                lastbuttontime = now
                program -= 1
                if program < 0:
                    program = 127
                fs.program_change(0, program)
            elif not GPIO.input(17) and (now - lastbuttontime) > 0.2:
                lastbuttontime = now
                program += 1
                if program > 127:
                    program = 0
                fs.program_change(0, program)
            time.sleep(0.020)


    ButtonsThread = threading.Thread(target=Buttons)
    ButtonsThread.daemon = True
    ButtonsThread.start()

#########################################
# 7-SEGMENT DISPLAY
#
#########################################

if configparser["samplerbox"][
    "USE_I2C_7SEGMENTDISPLAY"] == "True":  # requires: 1) i2c-dev in /etc/modules and 2) dtparam=i2c_arm=on in /boot/config.txt
    import smbus

    bus = smbus.SMBus(1)  # using I2C


    def display(s):
        for k in '\x76\x79\x00' + s:  # position cursor at 0
            try:
                bus.write_byte(0x71, ord(k))
            except:
                try:
                    bus.write_byte(0x71, ord(k))
                except:
                    pass
            time.sleep(0.002)


    display('----')
    time.sleep(0.5)
else:
    def display(s):
        pass

#########################################
# MIDI IN via SERIAL PORT
#
#########################################

if configparser["samplerbox"]["USE_SERIALPORT_MIDI"] == "True":
    import serial

    serialPort = int(configparser["samplerbox"]["SERIALPORT_PORT"])
    baudRate = int(configparser["samplerbox"]["SERIALPORT_BAUDRATE"])

    ser = serial.Serial(serialPort, baudrate=baudRate)


    def MidiSerialCallback():
        message = [0, 0, 0]
        while True:
            i = 0
            while i < 3:
                data = ord(ser.read(1))  # read a byte
                if data >> 7 != 0:
                    i = 0  # status byte!   this is the beginning of a midi message: http://www.midi.org/techspecs/midimessages.php
                message[i] = data
                i += 1
                if i == 2 and message[0] >> 4 == 12:  # program change: don't wait for a third byte: it has only 2 bytes
                    message[2] = 0
                    i = 3
            forwaredToFluidSynt(message)


    MidiThread = threading.Thread(target=MidiSerialCallback)
    MidiThread.daemon = True
    MidiThread.start()

########################################
# MIDI DEVICES DETECTION
# MAIN LOOP
########################################

registeredMidiInputs = {}

inputsWatcher = rtmidi.MidiIn()

while True:
    ports = inputsWatcher.get_ports()

    # add new midi devices
    for port, name in enumerate(ports):
        if name not in registeredMidiInputs:
            midiin = rtmidi.MidiIn()
            midiin.open_port(port)
            midiin.set_callback(MidiInputHandler())
            registeredMidiInputs[name] = midiin
            logger.info(f"Registered MIDI port #{port} device: {name}")

    # close old midi devices
    toRemove = []
    for name, midiin in registeredMidiInputs.items():
        if name not in ports:
            midiin.close_port()
            toRemove.append(name)

    for name in toRemove:
        del registeredMidiInputs[name]
        logger.info(f"Unregistered MIDI device: {name}")

    time.sleep(2)
