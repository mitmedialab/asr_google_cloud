# asr_google_cloud

Get audio from either a local microphone or over ROS, send the audio to Google
Speech API for processing, receive the results back, and publish the ASR
results to another ROS topic.

## Setup and dependencies

### Authentication

You will need to set yourself up as an authenticated user. If you don't, it
won't work.

If you are a PRG group member, please talk with current group members about
getting our Google Cloud API key file.

Then, set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable with the
path to your key file. You can put this line in your shell config file.

```
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials_file.json
```

There are several examples of how to set up authentication in the [Google Cloud
Python example
code](https://github.com/GoogleCloudPlatform/python-docs-samples/tree/master/speech/cloud-client).
In particular, you can use the Google Cloud SDK when running locally.

### Install the dependencies
1. Use python virtual environment or conda environment to install dependencies listed below

However, note that pip may not be able to successfully install portaudio, which
is a dependency of pyaudio. See details below.

#### Dependency details

The dependencies are listed in the `Pipfile`:

- google-cloud-speech (tested with version 0.29.0)
    - Depends on six version 1.10.0 or higher
- six (tested with version 1.10.0)
- PyAudio (tested with version 0.2.11)
    - Open and read from the local microphone.
    - Depends on portaudio. Note that sometimes pip has issues finding the
      portaudio.h file if you don't install this manually. On Ubuntu 14.04, you
      may need to install portaudio19-dev instead of libportaudio for it to
      compile successfully. You also may need to install it globally with `sudo
      apt-get portaudio19-dev` instead of using `pip install poraudio`. There
      are more details on the [PyAudio installation instructions
      page](https://people.csail.mit.edu/hubert/pyaudio/#downloads).
    - MIT license

In addition, these scripts were developed and tested with:

- Python 2.7.6
- Ubuntu 14.04 LTS 32-bit
- ROS Indigo

If you run into path issues, you may need to create a path file to tell python
where to look for some stuff. For example, if ROS is not installed with pipenv,
you may need to create a file called "ros.pth" with the paths to ROS libraries
in it:

```
/home/username/projects/ros_catkin_ws/devel/lib/python2.7/dist-packages
/opt/ros/indigo/lib/python2.7/dist-packages
```

Put this file in
`~/.local/share/virtualenvs/name_of_your_venv/lib/python2.7/site-packages`.


### If you need to mess with authentication or other Google Cloud settings

- Download the latest [Google Cloud
  SDK](https://cloud.google.com/sdk/docs/quickstart-linux) tarball.
- Follow the installation instructions provided on that page (i.e., extract the
  files from the tarball and optionally run the install script, which adds
  stuff to your PATH so you don't have to provide the full path when executing
  scripts).
- Follow the other instructions Google provides for changing settings or
  running stuff locally.

Version 170.0.1 was used for development
([32-bit](https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-sdk-170.0.1-linux-x86.tar.gz),
[64-bit](https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-sdk-170.0.1-linux-x86_64.tar.gz).

## Usage

To continuously transcribe audio from r1d1\_action (e.g., from Tega App) from
an Android device using AndroidAudio messages, and get ASR results back, run:

```sh
$ python ros_asr.py
```
To run the `src/ros_asr.py` script from anywhere, you can use the
`run_ros_asr.sh` script. You may need to modify the script to use the filepath
to wherever you checked out this repository.

To stream audio from your local microphone to Google and get ASR results back,
run:

```sh
$ python local_mic_asr.py
```

## Further reading

### Google Cloud Speech API Samples

For further Google Cloud Speech API Samples, consult the documentation at
[Google Cloud Speech API](http://cloud.google.com/speech) and sample code at
[GoogleCloudPlatform/google-cloud-python](https://github.com/GoogleCloudPlatform/google-cloud-python).

## Bugs and issues

Please report all bugs and issues on the [asr_google_cloud github issues
page](https://github.com/mitmedialab/asr_google_cloud/issues).
