from setuptools import setup

setup(
    name='ffmpeg-nmlz',
    version='0.0.1',
    packages=['ffmpeg_nmlz'],
    url='',
    license='MIT',
    author='ipid',
    author_email='ipid@users.noreply.github.com',
    description='',
    entry_points={
        'console_scripts': [
            'nmlz=ffmpeg_nmlz.main:main',
        ],
    }
)
