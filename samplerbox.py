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


import fluidsynth
import rtmidi
import threading
import time

from config import *

preset = 0

fs = fluidsynth.Synth(gain=1.0)
fs.setting('audio.driver', 'pulseaudio')
fs.start()

sfid1 = fs.sfload("synths.sf2")
fs.program_select(0, sfid1, 0, 0)


class MidiInputHandler(object):
    def __init__(self, port):
        self.port = port
        self._wallclock = time.time()

    def __call__(self, event, data=None):
        message, deltatime = event
        global preset
        messagetype = message[0] >> 4
        messagechannel = (message[0] & 15)
        note = message[1] if len(message) > 1 else None
        velocity = message[2] if len(message) > 2 else None
        print(f"type: {messagetype} channel: {messagechannel} note: {note} velocity: {velocity}")

        if MIDI_CHANNEL is not None and messagechannel != MIDI_CHANNEL:
            return

        if messagetype == 9:  # Note on
            fs.noteon(0, note, velocity)
        elif messagetype == 8 or (messagetype == 9 and velocity == 0):  # Note off
            fs.noteoff(0, note)
        elif messagetype == 12:  # Program change
            preset = note
            fs.program_change(0, note, velocity)
        elif messagetype == 11:  # CC
            fs.cc(0, note, velocity)


#########################################
# BUTTONS THREAD (RASPBERRY PI GPIO)
#
#########################################

if USE_BUTTONS:
    import RPi.GPIO as GPIO

    lastbuttontime = 0


    def Buttons():
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(18, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        global preset, lastbuttontime
        while True:
            now = time.time()
            if not GPIO.input(18) and (now - lastbuttontime) > 0.2:
                lastbuttontime = now
                preset -= 1
                if preset < 0:
                    preset = 127
                fs.program_select(0, sfid, 0, preset)
            elif not GPIO.input(17) and (now - lastbuttontime) > 0.2:
                lastbuttontime = now
                preset += 1
                if preset > 127:
                    preset = 0
                fs.program_select(0, sfid, 0, preset)
            time.sleep(0.020)


    ButtonsThread = threading.Thread(target=Buttons)
    ButtonsThread.daemon = True
    ButtonsThread.start()

#########################################
# 7-SEGMENT DISPLAY
#
#########################################

if USE_I2C_7SEGMENTDISPLAY:  # requires: 1) i2c-dev in /etc/modules and 2) dtparam=i2c_arm=on in /boot/config.txt
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

if USE_SERIALPORT_MIDI:
    import serial

    ser = serial.Serial(SERIALPORT_PORT, baudrate=SERIALPORT_BAUDRATE)


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
            MidiCallback(message, None)


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
            midiin.set_callback(MidiInputHandler(name))
            registeredMidiInputs[name] = midiin
            print(f"Registered MIDI port #{port} device: {name}")

    # close old midi devices
    toRemove = []
    for name, midiin in registeredMidiInputs.items():
        if name not in ports:
            midiin.close_port()
            toRemove.append(name)

    for name in toRemove:
        del registeredMidiInputs[name]
        print(f"Unregistered MIDI device: {name}")

    time.sleep(2)
