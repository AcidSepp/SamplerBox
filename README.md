# SamplerBox

SamplerBox is an **open-source DIY audio sampler project** based on RaspberryPi.

Website: [www.samplerbox.org](https://www.samplerbox.org)

[![](https://gget.it/flurexml/1.jpg)](https://www.youtube.com/watch?v=yz7GZ8YOjTw)

# Install

SamplerBox works with the RaspberryPi's built-in soundcard, but it is recommended to use a USB DAC (PCM2704 USB DAC for
less than 10€ on eBay is fine) for better sound quality.

+ download SamplerBox:

```sh
git clone https://github.com/acidsepp/SamplerBox.git
cd SamplerBox
```

+ Setup Python 3.13.4:

```sh
pyenv install 3.13.4
pyenv local 3.13.4
```

+ setup venv

~~~sh
python3 -m venv .venv
source .venv/bin/activate
~~~

+ install

```sh
pip install -e .  
```

+ run

```sh
python3 samplerbox.py
```

Play some notes on the connected MIDI keyboard, you'll hear some sound!

# About

- Author : Joseph Ernest (twitter: [@JosephErnest](https:/twitter.com/JosephErnest)
- Author : AcidSepp

# Sponsors and consulting

I am available for Python, Data science, ML, Automation **consulting**. Please contact me on https://afewthingz.com for
freelancing requests.

Do you want to support the development of my open-source projects? Please contact me!

I am currently sponsored by [CodeSigningStore.com](https://codesigningstore.com). Thank you to them for providing a
DigiCert Code Signing Certificate and supporting open source software.

# License

[Creative Commons BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)
