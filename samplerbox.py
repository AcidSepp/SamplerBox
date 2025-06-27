#
#  SamplerBox
#
#  author:    Joseph Ernest (twitter: @JosephErnest, mail: contact@samplerbox.org)
#  url:       http://www.samplerbox.org/
#  license:   Creative Commons ShareAlike 3.0 (http://creativecommons.org/licenses/by-sa/3.0/)
#
#  samplerbox.py: Main file (now requiring at least Python 3.7)
#

import configparser
import logging
import os
import sys
import threading
import time
from pathlib import Path
from time import sleep

import fluidsynth
import rtmidi
from sf2utils.sf2parse import Sf2File

class SamplerBox:

    def __init__(self, midi_channel: int, bank: int, program: int, gain: float, samples_dir: str):
        self.bank = bank
        self.program = program
        self.midi_channel = midi_channel

        self.fluid_synth = fluidsynth.Synth(gain=gain)
        self.fluid_synth.setting('audio.driver', 'pulseaudio')
        self.fluid_synth.setting('audio.periods', 2)
        self.fluid_synth.setting('audio.period-size', 64)
        self.fluid_synth.start()

        directory = Path(samples_dir)
        sf2_files = [f for f in directory.glob("*.sf2") if f.is_file()]

        for sf2_file in sf2_files:
            self.fluid_synth.sfload(sf2_file.name)
            logger.info(f"Loading soundfont from file: {sf2_file.name}")
            with open(sf2_file, 'rb') as sf2_file_opened:
                sf2 = Sf2File(sf2_file_opened)
                for preset in sf2.presets:
                    if preset.name == "EOP":
                        break
                    logger.info(f"- Bank {preset.bank}, Program {preset.preset}: {preset.name}")

        self.load_preset(bank, program)
        self.setup_midi_device_watcher()

    def load_preset(self, bank: int, program: int):
        self.bank = bank
        self.program = program
        self.fluid_synth.bank_select(0, bank)
        self.fluid_synth.program_change(0, program)
        logger.info(f"Loading bank={bank} programm={program} channelInfo={self.fluid_synth.channel_info(0)}")


    def forward_to_fluid_synth(self, message):
        messagetype = message[0] >> 4
        messagechannel = (message[0] & 15)
        note = message[1] if len(message) > 1 else None
        velocity = message[2] if len(message) > 2 else None
        logger.debug(f"Received MIDI message: type={messagetype} channel={messagechannel} note={note} velocity={velocity}")

        if self.midi_channel != -1 and messagechannel != self.midi_channel:
            logger.debug(
                f"Not forwarding to fluidsynth because the channel={messagechannel} does not the configured channel={self.midi_channel}")
            return

        if messagetype == 0x9:  # Note on
            logger.debug(f"Forwarding NOTE ON to fluidsynth.")
            self.fluid_synth.noteon(0, note, velocity)
        elif messagetype == 0x8 or (messagetype == 9 and velocity == 0):  # Note off
            logger.debug(f"Forwarding NOTE OFF to fluidsynth.")
            self.fluid_synth.noteoff(0, note)
        elif messagetype == 0xC:  # Program change
            logger.debug(f"Forwarding Program Change to fluidsynth.")
            self.program = note
            self.fluid_synth.program_change(0, note, velocity)
        elif messagetype == 0xB:  # CC
            logger.debug(f"Forwarding CC to fluidsynth.")
            self.fluid_synth.cc(0, note, velocity)

    def setup_GPIO_buttons(self):
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
                    self.fluid_synth.program_change(0, program)
                elif not GPIO.input(17) and (now - lastbuttontime) > 0.2:
                    lastbuttontime = now
                    program += 1
                    if program > 127:
                        program = 0
                    self.fluid_synth.program_change(0, program)
                time.sleep(0.020)

        buttons_thread = threading.Thread(target=Buttons)
        buttons_thread.daemon = True
        buttons_thread.start()

    def setup_GPIO_serial_MIDI(self, baud_rate: int, serial_port: int):
        import serial

        ser = serial.Serial(serial_port, baudrate=baud_rate)

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
                self.forward_to_fluid_synth(message)

        midi_thread = threading.Thread(target=MidiSerialCallback)
        midi_thread.daemon = True
        midi_thread.start()

    def setup_midi_device_watcher(self):
        registered_midi_inputs = {}
        inputs_watcher = rtmidi.MidiIn()

        def watcher():
            while True:
                ports = inputs_watcher.get_ports()

                # add new midi devices
                for port, name in enumerate(ports):
                    if name not in registered_midi_inputs:
                        midiin = rtmidi.MidiIn()
                        midiin.open_port(port)
                        midiin.set_callback(MidiInputHandler(self))
                        registered_midi_inputs[name] = midiin
                        logger.info(f"Registered MIDI port #{port} device: {name}")

                # close old midi devices
                toRemove = []
                for name, midiin in registered_midi_inputs.items():
                    if name not in ports:
                        midiin.close_port()
                        toRemove.append(name)

                for name in toRemove:
                    del registered_midi_inputs[name]
                    logger.info(f"Unregistered MIDI device: {name}")

                time.sleep(2)

        thread = threading.Thread(target=watcher)
        thread.daemon = True
        thread.start()

class MidiInputHandler:

    def __init__(self, sampler_box: SamplerBox) -> None:
        self.sampler_box = sampler_box

    def __call__(self, event, data=None):
        message, deltatime = event
        self.sampler_box.forward_to_fluid_synth(message)

if __name__ == '__main__':
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

    midi_channel = int(configparser["samplerbox"]["MIDI_CHANNEL"])

    gain = configparser["samplerbox"]["GAIN"]

    samples_dir = configparser["samplerbox"]["SAMPLES_DIR"]

    samplerbox = SamplerBox(midi_channel, bank, program, float(gain), samples_dir)

    if configparser["samplerbox"]["USE_SERIALPORT_MIDI"] == "True":
        serial_port = int(configparser["samplerbox"]["SERIALPORT_PORT"])
        baud_rate = int(configparser["samplerbox"]["SERIALPORT_BAUDRATE"])
        samplerbox.setup_GPIO_serial_MIDI(serial_port, baud_rate)

    if configparser["samplerbox"]["USE_BUTTONS"] == "True":
        samplerbox.setup_GPIO_buttons()

    while True:
        sleep(5)
