#!/usr/bin/env python
"""
Hae Won Park
April 2019

The MIT License (MIT)

Copyright (c) 2019 Personal Robots Group

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Google Cloud Speech API sample application using the streaming API.

NOTE: This module requires the additional dependency `pyaudio`. To install
using pip:

    pip install pyaudio

Example usage:
    python transcribe_streaming_indefinite.py
"""

# [START speech_transcribe_infinite_streaming]
from __future__ import division

import requests
import json
import time
import re
import sys

# from google.cloud import speech
import assemblyai as aai

import pyaudio
from six.moves import queue

# ROS setup
import rospy  # Get audio data over ROS and publish results.
from std_msgs.msg import Header
from asr_google_cloud.msg import AsrResult
from asr_google_cloud.msg import AsrCommand
from asr_google_cloud.msg import Words

from passwords import ASSEMBLYAI_API_KEY

# Audio recording parameters
STREAMING_LIMIT = 55000
SAMPLE_RATE = 16000
CHUNK_SIZE = int(SAMPLE_RATE / 10)  # 100ms


def get_current_time():
    return int(round(time.time() * 1000))


def duration_to_secs(duration):
    return duration.seconds + (duration.nanos / float(1e9))


class ResumableMicrophoneStream:
    """Opens a recording stream as a generator yielding the audio chunks."""
    def __init__(self, rate, chunk_size):
        self._rate = rate
        self._chunk_size = chunk_size
        self._num_channels = 1
        self._max_replay_secs = 5

        # Create a thread-safe buffer of audio data
        self._buff = queue.Queue()
        self.closed = True
        self.start_time = get_current_time()

        # 2 bytes in 16 bit samples
        self._bytes_per_sample = 2 * self._num_channels
        self._bytes_per_second = self._rate * self._bytes_per_sample

        self._bytes_per_chunk = (self._chunk_size * self._bytes_per_sample)
        self._chunks_per_second = (
                self._bytes_per_second // self._bytes_per_chunk)

    def __enter__(self):
        self.closed = False

        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=self._num_channels,
            rate=self._rate,
            input=True,
            frames_per_buffer=self._chunk_size,
            # Run the audio stream asynchronously to fill the buffer object.
            # This is necessary so that the input device's buffer doesn't
            # overflow while the calling thread makes network requests, etc.
            stream_callback=self._fill_buffer,
        )

        return self

    def __exit__(self, type, value, traceback):
        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        # Signal the generator to terminate so that the client's
        # streaming_recognize method will not block the process termination.
        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(self, in_data, *args, **kwargs):
        """Continuously collect data from the audio stream, into the buffer."""
        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def generator(self):
        while not self.closed:
            if get_current_time() - self.start_time > STREAMING_LIMIT:
                self.start_time = get_current_time()
                break
            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]

            # Now consume whatever other data's still buffered.
            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break

            if not send_data:
                return

            yield b''.join(data)


def listen_print_loop(responses, stream):
    """Iterates through server responses and prints them.

    The responses passed is a generator that will block until a response
    is provided by the server.

    Each response may contain multiple results, and each result may contain
    multiple alternatives; for details, see https://goo.gl/tjCPAU.  Here we
    print only the transcription for the top alternative of the top result.

    In this case, responses are provided for interim results as well. If the
    response is an interim one, print a line feed at the end of it, to allow
    the next result to overwrite it, until the response is a final one. For the
    final one, print a newline to preserve the finalized transcription.
    """
    responses = (r for r in responses if (
            r.results and r.results[0].alternatives))

    num_chars_printed = 0
    for response in responses:
        if not response.results:
            continue

        # Send results over ROS.
        msg = AsrResult()
        msg.header = Header()
        msg.header.stamp = rospy.Time.now()

        # The `results` list is consecutive. For streaming, we only care about
        # the first result being considered, since once it's `is_final`, it
        # moves on to considering the next utterance.
        result = response.results[0]
        if not result.alternatives:
            continue

        # Display the transcription of the top alternative.
        top_alternative = result.alternatives[0]
        transcript = top_alternative.transcript

        # Display interim results, but with a carriage return at the end of the
        # line, so subsequent lines will overwrite them.
        #
        # If the previous result was longer than this one, we need to print
        # some extra spaces to overwrite the previous result
        overwrite_chars = ' ' * (num_chars_printed - len(transcript))

        if not result.is_final:
            sys.stdout.write(transcript + overwrite_chars + '\r')
            sys.stdout.flush()

            num_chars_printed = len(transcript)
        else:
            print(transcript + overwrite_chars)

            # print("Got final result:\n{}".format(response))
            # TODO publish alternatives
            if publish_alternatives:
                print("TODO publish alternatives")
            msg.transcription = str(response.results[0].alternatives[0].
                                    transcript)
            msg.confidence = response.results[0].alternatives[0].confidence

            for i in range(len(response.results[0].alternatives[0].words)):
                w = Words()
                w.word = response.results[0].alternatives[0].words[i].word
                w.start_time = response.results[0].alternatives[0].words[i].start_time.seconds + \
                               float(response.results[0].alternatives[0].words[i].start_time.microseconds) * 1e-6
                w.end_time = response.results[0].alternatives[0].words[i].end_time.seconds + \
                             float(response.results[0].alternatives[0].words[i].end_time.microseconds) * 1e-6

                msg.words_list.append(w)

            pub_asr_result.publish(msg)
            print("*** SENT RESULT ***")

            # Exit recognition if any of the transcribed phrases could be
            # one of our keywords.
            # if re.search(r'\b(exit|quit)\b', transcript, re.I):
            #     print('Exiting..')
            #     stream.closed = True
            #     break

            num_chars_printed = 0

def on_asr_command(data):
    """ Receive and process a command message telling this node to start or
    stop streaming audio to Google.
    """
    print("Received ASR command: {}".format(data.command))
    print("ASR COMMAND RECEIVED **********************")
    global publish_final, publish_interim, publish_alternatives, send_data
    # Should we stop streaming data to Google for processing or stop sending
    # any kind of results back? If no results streaming is enabled, we won't
    # send anything to Google.
    if (data.command == AsrCommand.STOP_ALL or
            data.command == AsrCommand.STOP_FINAL):
        # Stop streaming final results.
        publish_final = False
    if (data.command == AsrCommand.STOP_ALL or
            data.command == AsrCommand.STOP_ALTERNATIVES):
        # Stop streaming alternative results.
        publish_alternatives = False
    if (data.command == AsrCommand.STOP_ALL or
            data.command == AsrCommand.STOP_INTERIM):
        # Stop streaming interim results.
        publish_interim = False

    # Or should we start streaming data to Google for processing or start
    # sending a particular kind of results?
    if (data.command == AsrCommand.START_ALL or
            data.command == AsrCommand.START_FINAL):
        # Start streaming final results.
        publish_final = True
    if (data.command == AsrCommand.START_ALL or
            data.command == AsrCommand.START_ALTERNATIVES):
        # Start streaming alternative results.
        publish_alternatives = True
    if (data.command == AsrCommand.START_ALL or
            data.command == AsrCommand.START_INTERIM):
        # Start streaming interim results.
        publish_interim = True

    # If we should now be publishing results, start ASR.
    if publish_final or publish_alternatives or publish_interim:
        send_data = True
    else:
        send_data = False

def main():

    rospy.init_node('google_asr_node', anonymous=False)

    # Publish ASR results as asr_google_cloud/AsrResult messages.
    global pub_asr_result
    pub_asr_result = rospy.Publisher('asr_result', AsrResult, queue_size=10)

    # Subscribe to basic commands to tell this node to start or stop processing
    # audio and streaming to Google, as well as what results to publish.
    global sub_asr_command
    sub_asr_command = rospy.Subscriber('asr_command', AsrCommand, on_asr_command)

    global publish_interim
    publish_interim = False
    global publish_alternatives
    publish_alternatives = False
    global publish_final
    publish_final = False
    global send_data
    send_data = True

    mic_manager = ResumableMicrophoneStream(SAMPLE_RATE, CHUNK_SIZE)
    
    base_url = "https://api.assemblyai.com/v2/transcript"

    headers = {
        "authorization": ASSEMBLYAI_API_KEY
    }

    #print('Say "Quit" or "Exit" to terminate the program.')

    with mic_manager as stream:
        while not stream.closed:
            audio_generator = stream.generator()
            
            with open("temp.wav", mode='bx') as f:
                f.write(content for content in audio_generator)
                
            with open("temp.wav" , "rb") as f:
                response = requests.post(base_url + "/upload",
                                        headers=headers,
                                        data=f)
            upload_url = response.json()["upload_url"]
            
            data = {"audio_url": upload_url}
            response = requests.post(base_url, json=data, headers=headers)

            transcript_id = response.json()['id']
            polling_endpoint = f"{base_url}/{transcript_id}"

            while True:
                transcription_result = requests.get(polling_endpoint, headers=headers).json()

                if transcription_result['status'] == 'completed':
                    break
                elif transcription_result['status'] == 'error':
                    raise RuntimeError(f"Transcription failed: {transcription_result['error']}")
                else:
                    time.sleep(2)

            print(transcription_result)
            # Now, put the transcription responses to use.
            # listen_print_loop(transcript, stream)


if __name__ == '__main__':
    main()
# [END speech_transcribe_infinite_streaming]
