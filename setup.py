from setuptools import setup, Extension
import numpy

setup(ext_modules=[Extension(name="samplerbox_audio", sources=["samplerbox_audio.pyx"])], include_dirs=[numpy.get_include()])
