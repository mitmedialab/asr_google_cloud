# asr_google_cloud

Get audio from either a local microphone or over ROS, send the audio to Google
Speech API for processing, receive the results back, and publish the ASR
results to another ROS topic.

## Setup and dependencies

### Install Google Cloud SDK

- Download the latest [Google Cloud
  SDK](https://cloud.google.com/sdk/docs/quickstart-linux) tarball.
- Follow the installation instructions provided on that page (i.e., extract the
  files from the tarball and optionally run the install script, which adds
  stuff to your PATH so you don't have to provide the full path when executing
  scripts).

Version 170.0.1 was used for development
([32-bit](https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-sdk-170.0.1-linux-x86.tar.gz),
[64-bit](https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-sdk-170.0.1-linux-x86_64.tar.gz).

### System Setup

If you're using bash, add the following in your .bashrc (for Linux):

* Set variable path to the your google cloud api key (the attached api key file
  is linked to billing with PRG P-Card)

```
export GOOGLE_APPLICATION_CREDENTIALS="/path-to-your-catkin-src-folder/asr_google_cloud/project-24924eb028d1.json"
```

If you do not do this, the REST api will return a 403. The streaming sample
will just sort of hang silently.

### Install the dependencies

* Install grpc requirements:

    ```sh
    $ sudo apt-get install portaudio19-dev python-all-dev
    $ sudo pip install -r google_grpc_requirements.txt
    ```

`node_pyaudio_google_asr.py` uses the [PyAudio][pyaudio] library to stream
audio from your computer's microphone. PyAudio depends on
[PortAudio][portaudio], which may need to be compiled when you install PyAudio.
If you run into compilation issues that mention PortAudio, you may have to
[install some dependencies][pyaudio-install].

[pyaudio]: https://people.csail.mit.edu/hubert/pyaudio/
[portaudio]: http://www.portaudio.com/
[pyaudio-install]: https://people.csail.mit.edu/hubert/pyaudio/#downloads

## Usage

Both codes will run in a continuous loop, printing the data and metadata it
receives from the Speech API, which includes alternative transcriptions of what
it hears, and a confidence score.

Note that it does not yet support python 3, as the upstream `grpcio` library's
support is [not yet complete](https://github.com/grpc/grpc/issues/282).

* To run `node_pyaudio_google_asr.py`:

    ```sh
    $ python node_pyaudio_google_asr.py
    ```

This code listens to your computer's microphone input and publishes ASR result
to `/asr_result` .


* To run `node_google_asr.py`:

    ```sh
    $ python node_google_asr.py
    ```

This code subscribes to `/android_audio` (or any other source) and publishes
ASR result to `/asr_result`.  Use this code with
[Android_microphone_ROS](https://github.com/mitmedialab/android_microphone_ros).


## Google Cloud Speech API Samples

For further Google Cloud Speech API Samples in streaming mode (via its gRPC
API) and in non-streaming mode (via its REST API), consult the documentation at
[Google Cloud Speech API](http://cloud.google.com/speech) and sample codes at
[GoogleCloudPlatform/google-cloud-python](https://github.com/GoogleCloudPlatform/google-cloud-python.git).
