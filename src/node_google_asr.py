#!/usr/bin/python
# Copyright (C) 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Sample that streams audio to the Google Cloud Speech API via GRPC."""

from __future__ import division

import contextlib
import re
import signal
import sys
import threading
import time
import binascii
import httplib2
import oauth2client

from google.cloud import credentials
from google.cloud.speech.v1beta1 import cloud_speech_pb2 as cloud_speech
from google.rpc import code_pb2
from grpc.beta import implementations
from grpc.framework.interfaces.face import face
import pyaudio
from six.moves import queue

import rospy
from std_msgs.msg import String
from r1d1_msgs.msg import AndroidAudio
from asr_google_cloud.msg import AsrResult

# Audio recording parameters
RATE = 16000
#CHUNK = 2560#int(RATE / 10)  # 100ms

# The Speech API has a streaming limit of 60 seconds of audio*, so keep the
# connection alive for that long, plus some more to give the API time to figure
# out the transcription.
# * https://g.co/cloud/speech/limits#content
DEADLINE = 60
DEADLINE_SECS = DEADLINE * 3 + 5
SPEECH_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'

CONTINUOUS_REQUEST = True

init_time = 0
pub_asr_result = rospy.Publisher('asr_result', AsrResult, queue_size = 10)
pub_audio_request = rospy.Publisher('audio_request', String, queue_size = 10)
sub_asr_start = ''
is_publish = True
publish_alternatives = False
publish_interim = False

def onNewAsrStart(data):
    global is_publish, publish_alternatives, publish_interim
    print data.data

    if "stop" in data.data:
        is_publish = False
        msg = AsrResult()
        msg.header.stamp = rospy.Time.now()
        msg.transcription = "df#$%sdfg#12"
        msg.confidence = 100.0
        pub_asr_result.publish(msg)

        # stop:interim:alternative
        if "interim" in data.data:
            print "stop interim"
            publish_interim = False

        if "alternative" in data.data:
            print "stop alternatives"
            publish_alternatives = False

    elif "start" in data.data:
        is_publish = True

        # start:interim:alternative
        if "interim" in data.data:
            print "start interim"
            publish_interim = True

        if "alternative" in data.data:
            print "start alternatives"
            publish_alternatives = True


def make_channel(host, port):
    """Creates an SSL channel with auth credentials from the environment."""
    # In order to make an https call, use an ssl channel with defaults
    ssl_channel = implementations.ssl_channel_credentials(None, None, None)

    # Grab application default credentials from the environment
    creds = credentials.get_credentials().create_scoped([SPEECH_SCOPE])
    # Add a plugin to inject the creds into the header
    auth_header = (
        'Authorization',
        'Bearer ' + creds.get_access_token().access_token)
    auth_plugin = implementations.metadata_call_credentials(
        lambda _, cb: cb([auth_header], None),
        name='google_creds')

    # compose the two together for both ssl and google auth
    composite_channel = implementations.composite_channel_credentials(
        ssl_channel, auth_plugin)

    return implementations.secure_channel(host, port, composite_channel)


def _audio_data_generator(buff):
    """A generator that yields all available data in the given buffer.

    Args:
        buff - a Queue object, where each element is a chunk of data.
    Yields:
        A chunk of data that is the aggregate of all chunks of data in `buff`.
        The function will block until at least one data chunk is available.
    """
    while True:
        # Use a blocking get() to ensure there's at least one chunk of data
        chunk = buff.get()
        if not chunk:
            # A falsey value indicates the stream is closed.
            break
        data = [chunk]
        #print data
        
        # Now consume whatever other data's still buffered.
        while True:
            try:
                data.append(buff.get(block=False))
            except queue.Empty:
                break
        yield b''.join(data)


def _fill_buffer(audio_stream, args):
    """Continuously collect data from the audio stream, into the buffer."""

    buff = args
    buff.put(binascii.unhexlify(audio_stream.data))

# [START audio_stream]
@contextlib.contextmanager
def record_audio(rate):
    """Opens a recording stream in a context manager."""
    # Create a thread-safe buffer of audio data
    buff = queue.Queue()

    # Spin up a separate thread to buffer audio data from the android microphone
    # This is necessary so that the input device's buffer doesn't overflow
    # while the calling thread makes network requests, etc.

    sub_audio = rospy.Subscriber('android_audio', AndroidAudio, _fill_buffer, buff)

    yield _audio_data_generator(buff)

def request_stream(data_stream, rate, interim_results=True):
    """Yields `StreamingRecognizeRequest`s constructed from a recording audio
    stream.

    Args:
        data_stream: A generator that yields raw audio data to send.
        rate: The sampling rate in hertz.
        interim_results: Whether to return intermediate results, before the
            transcription is finalized.
    """
    # The initial request must contain metadata about the stream, so the
    # server knows how to interpret it.
    recognition_config = cloud_speech.RecognitionConfig(
        # There are a bunch of config options you can specify. See
        # https://goo.gl/KPZn97 for the full list.
        encoding='LINEAR16',  # raw 16-bit signed LE samples
        sample_rate=rate,  # the rate in hertz
        # See http://g.co/cloud/speech/docs/languages
        # for a list of supported languages.
        language_code='en-US',  # a BCP-47 language tag
        #speech_context={"phrases":["Tega", "Huawei", "Haewon", "demo", "Ishaan", "Mirko", "Sooyoung", "Jinjoo", "Hooli", "tree", "turtle", "yeah", "yup"]},
        speech_context={"phrases":["the end", "Tyga", "the end Tyga", "Tyga the end", "that's the end of the story", "Tyga that's the end of the story"]},
        max_alternatives=4
    )
    streaming_config = cloud_speech.StreamingRecognitionConfig(
        interim_results=interim_results,
        config=recognition_config,
    )

    yield cloud_speech.StreamingRecognizeRequest(
        streaming_config=streaming_config)

    for data in data_stream:

        if (time.time() - init_time) > 0.9*DEADLINE:
            print("Restarting before time out")
            break
        #else:
        #    print(time.time() - init_time)
        # Subsequent requests can all just have the content
        yield cloud_speech.StreamingRecognizeRequest(audio_content=data)


def listen_print_loop(recognize_stream):
    num_chars_printed = 0
    for resp in recognize_stream:
        if resp.error.code != code_pb2.OK:
            raise RuntimeError('Server error: ' + resp.error.message)
            break

        if not is_publish:
            print('Exiting..')
            break

        if not resp.results:
            continue

        # Display the transcriptions & their alternatives
        #for result in resp.results:
        #    print(result.alternatives)
        
        # Display the top transcription
        result = resp.results[0]
        transcript = result.alternatives[0].transcript

        # Display interim results, but with a carriage return at the end of the
        # line, so subsequent lines will overwrite them.
        if not result.is_final:
            if publish_interim:
                # If the previous result was longer than this one, we need to print
                # some extra spaces to overwrite the previous result
                overwrite_chars = ' ' * max(0, num_chars_printed - len(transcript))

                sys.stdout.write(transcript + overwrite_chars + '\r')
                sys.stdout.flush()
                num_chars_printed = len(transcript)

                msg = AsrResult()
                msg.header.stamp = rospy.Time.now()
                msg.transcription = transcript + overwrite_chars
                msg.confidence = 0
                pub_asr_result.publish(msg)

        else:
            msg = AsrResult()
            msg.header.stamp = rospy.Time.now()

            if publish_alternatives:
                trans_list = []
                for i in xrange(len(result.alternatives)):
                    trans_list.append(str(result.alternatives[i].transcript))
                print trans_list
                transcript = ': '.join(trans_list)

            msg.transcription = str(transcript)
            msg.confidence = result.alternatives[0].confidence
            pub_asr_result.publish(msg)

            print(transcript)
            print(result.alternatives[0].confidence)
        
            if (time.time() - init_time) > 0.85*DEADLINE:
                print("Restarting at the end of speech")
                break
            #else:
            #    print(time.time() - init_time)

            # Exit recognition if any of the transcribed phrases could be
            # one of our keywords.
            #if re.search(r'\b(Tega|taylor|tiger|Taylor)\b', transcript, re.I):
            #    print('Exiting..')
                #break

            num_chars_printed = 0


def start():
    global init_time

    try:
        with cloud_speech.beta_create_Speech_stub(
                make_channel('speech.googleapis.com', 443)) as service:
            # For streaming audio from the microphone, there are three threads.
            # First, a thread that collects audio data as it comes in
            with record_audio(RATE) as buffered_audio_data:
                # Second, a thread that sends requests with that data
                requests = request_stream(buffered_audio_data, RATE)
                # Third, a thread that listens for transcription responses
                recognize_stream = service.StreamingRecognize(
                    requests, DEADLINE_SECS)

                init_time = time.time()

                # Exit things cleanly on interrupt
                signal.signal(signal.SIGINT, lambda *_: recognize_stream.cancel())

                # Now, put the transcription responses to use.
                try:
                    listen_print_loop(recognize_stream)

                    recognize_stream.cancel()

                    while not is_publish:
                        time.sleep(0.5)

                    if CONTINUOUS_REQUEST:
                        #respun
                        start()
                except face.CancellationError as e:
                    print "\n{0}\n".format(e)
                    # This happens because of the interrupt handler
                    pass
    except httplib2.ServerNotFoundError as e:
        sys.stdout.write("\033[1;31m")
        print "\nServer unreachable: {0}\n".format(e)
        exit()
    except oauth2client.client.ApplicationDefaultCredentialsError as e:
        sys.stdout.write("\033[1;31m")
        print "\nCheck credentials: {0}\n".format(e)
        exit()
    except Exception as e:
        print "\n{0}\n".format(e)
        #time.sleep(1)
        start()


def main():
    node = rospy.init_node('google_asr')
    sub_asr_start = rospy.Subscriber('asr_start', String, onNewAsrStart)
    pub_audio_request.publish("start")
    start()

if __name__ == '__main__':
    main()
