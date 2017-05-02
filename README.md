# asr_google_cloud
This package holds source codes for subscribing to a microphone feed (or just using the PyAudio) and publishing ASR result over ROS


## Prerequisites

### Install Google Cloud SDK

Download SDK source file [Google Cloud SDK](https://cloud.google.com/sdk/docs/quickstart-linux) and follow the installation instruction.

(The current code was tested with google-cloud-sdk-133.0.0-linux-x86_64.tar.gz)

### System Setup

If you're using bash environment, add the followings in your .bashrc (for Linux)

* Set variable path to the your google cloud api key (the attached api key file is linked to billing with PRG P-Card)
  ```  
  export GOOGLE_APPLICATION_CREDENTIALS="/path-to-your-catkin-src-folder/asr_google_cloud/project-24924eb028d1.json"
  ```  
  If you do not do this, the REST api will return a 403. The streaming sample will just sort of hang silently.

### Install the dependencies

* Install grpc requirements:

    ```sh
    $ sudo apt-get install portaudio19-dev python-all-dev
    $ sudo pip install -r google_grpc_requirements.txt
    ```
    
    `node_pyaudio_google_asr.py` uses the [PyAudio][pyaudio] library to stream audio from your
    computer's microphone.  PyAudio depends on [PortAudio][portaudio], which may
    need to be compiled when you install PyAudio. If you run into compilation
    issues that mention PortAudio, you may have to [install some
    dependencies][pyaudio-install].

[pyaudio]: https://people.csail.mit.edu/hubert/pyaudio/
[portaudio]: http://www.portaudio.com/
[pyaudio-install]: https://people.csail.mit.edu/hubert/pyaudio/#downloads

## Run the code

Both codes will run in a continuous loop, printing the data and metadata it receives from the Speech API, which includes alternative transcriptions of what it hears, and a confidence score. 

Note that it does not yet support python 3, as the upstream `grpcio` library's support is [not yet complete](https://github.com/grpc/grpc/issues/282).

* To run `node_pyaudio_google_asr.py`:

    ```sh
    $ python node_pyaudio_google_asr.py
    ```
  
    This code listens to your computer's microphone input and publishes ASR result to `/asr_result` .
    

* To run `node_google_asr.py`:

    ```sh
    $ python node_google_asr.py
    ```
  
    This code subscribes to `/android_audio` (or any other source) and publishes ASR result to `/asr_result` . 
    Use this code with [Android_microphone_ROS](https://github.com/personal-robots/android_microphone_ros).
  
  
## Google Cloud Speech API Samples

For further Google Cloud Speech API Samples in streaming mode (via its gRPC API) and in non-streaming mode (via its REST
API), consult the documentation at [Google Cloud Speech API](http://cloud.google.com/speech) and sample codes at [GoogleCloudPlatform/google-cloud-python](https://github.com/GoogleCloudPlatform/google-cloud-python.git).
