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
from typing import List

import fluidsynth
import rtmidi
from sf2utils.sf2parse import Sf2File


class ChannelSetting:

    def __init__(self, midi_channel: int, bank: int, program: int):
        self.midi_channel = midi_channel
        self.bank = bank
        self.program = program


class SamplerBox:

    def __init__(self, midi_channel: int, channel_settings: List[ChannelSetting], gain: float, samples_dir: str,
                 fluid_synth_settings):
        self.midi_channel = midi_channel

        self.fluid_synth = fluidsynth.Synth(gain=gain)
        for key, value in fluid_synth_settings.items():
            self.fluid_synth.setting(key, value)
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

        self.setup_midi_device_watcher()

        for channel_setting in channel_settings:
            self.load_preset(channel_setting.midi_channel, channel_setting.bank, channel_setting.program)

    def load_preset(self, channel: int, bank: int, program: int):
        self.bank = bank
        self.program = program
        self.fluid_synth.bank_select(channel, bank)
        self.fluid_synth.program_change(channel, program)
        logger.info(
            f"Channel={channel}: loading bank={bank} programm={program} channelInfo={self.fluid_synth.channel_info(channel)}")

    def forward_to_fluid_synth(self, message):
        messagetype = message[0] >> 4
        messagechannel = (message[0] & 15)
        note = message[1] if len(message) > 1 else None
        velocity = message[2] if len(message) > 2 else None
        logger.debug(
            f"Received MIDI message: type={messagetype} channel={messagechannel} note={note} velocity={velocity}")

        if messagetype == 0x9:  # Note on
            logger.debug(f"Forwarding NOTE ON to fluidsynth.")
            self.fluid_synth.noteon(messagechannel, note, velocity)
        elif messagetype == 0x8 or (messagetype == 9 and velocity == 0):  # Note off
            logger.debug(f"Forwarding NOTE OFF to fluidsynth.")
            self.fluid_synth.noteoff(messagechannel, note)
        elif messagetype == 0xC:  # Program change
            logger.debug(f"Forwarding Program Change to fluidsynth.")
            self.program = note
            self.fluid_synth.program_change(messagechannel, note)
        elif messagetype == 0xB:  # CC
            logger.debug(f"Forwarding CC to fluidsynth.")
            self.fluid_synth.cc(messagechannel, note, velocity)
            self.fluid_synth.cc(0, note, velocity)

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
    samplerbox_config_parser = configparser.ConfigParser({
        "SAMPLES_DIR": os.getcwd(),
        "LOG_LEVEL": "INFO",
        "GAIN": "1.0"
    })
    samplerbox_config_parser.read('config.ini')

    logging.basicConfig(stream=sys.stdout, level=samplerbox_config_parser["samplerbox"]["LOG_LEVEL"])
    logger = logging.getLogger(name="SamplerBox")

    gain = samplerbox_config_parser["samplerbox"]["GAIN"]

    samples_dir = samplerbox_config_parser["samplerbox"]["SAMPLES_DIR"]

    channel_settings: list[ChannelSetting] = []
    for midi_channel in range(0, 15):
        section_name = "channel" + str(midi_channel)
        if samplerbox_config_parser.has_section(section_name):
            bank = int(samplerbox_config_parser[section_name]["bank"])
            program = int(samplerbox_config_parser[section_name]["program"])
            channel_settings.append(ChannelSetting(midi_channel, bank, program))

    fluisynth_settings: dict[str, int | float | str] = {}

    # NOTE: We're accessing the private `_sections` attribute of ConfigParser here
    # because the public `.items()` method merges in default values from the defaults dict,
    # which causes unrelated default keys (e.g., "SAMPLES_DIR", "GAIN") to appear in
    # unrelated sections like "fluidSynthSettingsInt". This leads to parsing errors when
    # trying to cast those values to int or float. By using `_sections`, we get only the
    # explicitly defined keys from the INI file, without default value pollution.
    # raw=True does not seem to work
    for key, value in samplerbox_config_parser._sections["fluidSynthSettingsInt"].items():
        fluisynth_settings[key] = int(value)

    for key, value in samplerbox_config_parser._sections["fluidSynthSettingsFloat"].items():
        fluisynth_settings[key] = float(value)

    for key, value in samplerbox_config_parser._sections["fluidSynthSettingsString"].items():
        fluisynth_settings[key] = value

    samplerbox = SamplerBox(midi_channel, channel_settings, float(gain), samples_dir, fluisynth_settings)

    while True:
        sleep(5)
