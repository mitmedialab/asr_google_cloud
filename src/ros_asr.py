#!/usr/bin/python
"""
Jacqueline Kory Westlund
September 2017

The MIT License (MIT)

Copyright (c) 2017 Personal Robots Group

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
"""

import argparse  # Get command-line arguments.
from six.moves import queue  # Thread-safe queue for buffering audio data.
from google.cloud import speech as google_speech
from google.cloud.speech import enums as google_enums
from google.cloud.speech import types as google_types
import rospy  # Get audio data over ROS and publish results.
from r1d1_msgs.msg import AndroidAudio
from std_msgs.msg import Header
from asr_google_cloud.msg import AsrResult
import binascii
import struct


class RosAudioStream(object):
    """ Open an audio stream over ROS as a generator that gives us chunks of
    audio data.
    """
    def __init__(self, sample_rate, buffer_size):
        # Thread-safe buffer of audio data.
        self._buffer = queue.Queue()
        # The audio stream starts out closed.
        self.closed = True

    def __enter__(self):
        """ Set up the audio stream. """
        # We collect audio from the stream into a buffer asynchronously with a
        # callback.
        # Use r1d1_msgs/AndroidAudio to get incoming audio stream from the
        # robot's microphone or a standalone android microphone app.
        sub_audio = rospy.Subscriber('android_audio', AndroidAudio,
                                     self.on_android_audio_msg)
        # The stream is now open. # TODO is it open now or at rospy.spin?
        self.closed = False
        return self

    def __exit__(self, type_, value, traceback):
        """ Make sure we stop and close the audio stream when we exit. """
        # Set the closed flag so the generator will stop looping.
        self.closed = True
        # Tell the generator to terminate by adding None to the buffer.
        self._buffer.put(None)

    def audio_generator(self):
        """ Get data from the buffer when requested. """
        while not self.closed:
            # Block on get() until there's data. That way, we get at least one
            # chunk of data each time.
            data_chunk = self._buffer.get()
            # Stop iterating if we just got a None in the buffer (our signal
            # that we're at the end of the audio stream).
            if data_chunk is None:
                return
            # Make a list of data chunks. We'll add more chunks later.
            data = [data_chunk]

            # Consume any additional data from the buffer.
            while True:
                try:
                    # Get more audio. In this case, we don't need to block
                    # because we know we have at least some data.
                    data_chunk = self._buffer.get(block=False)
                    # Again, if we get None, we got our signal that we're at
                    # the end of the stream, so stop collecting audio.
                    if data_chunk is None:
                        return
                    # Otherwise, collect the audio into our data list.
                    data.append(data_chunk)
                # Stop collecting data if the queue is empty.
                except queue.Empty:
                    break

            # Return all the audio data collected so far as a byte array.
            yield b"".join(data)

    def on_android_audio_msg(self, data):
        """ When we get an AndroidAudio message, collect the audio into a
        buffer for later processing.
        """
        # Collect audio into a buffer. TODO check format of audio for buffer
        stuff = struct.pack("<%uh" % len(data.samples), *data.samples)
        self._buffer.put(stuff)

        # Save the sample rate, sample width, and number of channels so we can
        # update the ASR configuration if they have changed.
        # TODO samplerate = data.sample_rate
        # The Google Cloud Speech API only supports 1-channel
        # (i.e. mono) audio, so we don't make that a tunable parameter.
        # TODO n_channels = data.nchannels
        # TODO sample_size = data.sample_width


def handle_responses(responses):
    """ Iterate through any responses received. """
    for response in responses:
        if not response.results:
            print "no responses"
            continue
        print response
        # Send top result over ROS.
        if response.results[0].is_final:
            msg = AsrResult()
            msg.header = Header()
            msg.header.stamp = rospy.Time.now()
            msg.transcription = str(response.results[0].alternatives[0].transcript)
            msg.confidence = response.results[0].alternatives[0].confidence
            global pub_asr_result
            pub_asr_result.publish(msg)
    print "..."


def main():
    """ Run Google ASR with the audio over ROS. """

    parser = argparse.ArgumentParser(
        description=""" Use the Google Cloud Speech API to get Google ASR
        results for audio streamed over ROS. """)
    parser.add_argument("-r, --sample_rate", type=int, nargs='?',
                        dest="sample_rate", action='store', default=44100,
                        help="""Sample rate at which audio will be streamed.
                        Defaults to 16000.""")
    parser.add_argument("-b, --buffer_size", type=int, nargs='?',
                        dest="buffer_size", action='store', default=4400,
                        help="""Buffer size (also called chunk size) for audio
                        being collected. Defaults to 1600 (i.e., one tenth of
                        the default sample rate, or 100ms).""")
    # Get arguments.
    args = parser.parse_args()
    print "Got arguments: {}".format(args)

    # ROS node setup:
    # TODO If running on a network where DNS does not resolve local hostnames,
    # get the public IP address of this machine and export to the environment
    # variable $ROS_IP to set the public address of this node, so the user
    # doesn't have to remember to do this before starting the node.
    ros_node = rospy.init_node('google_asr_node', anonymous=False)

    # Publish ASR results as asr_google_cloud/AsrResult messages.
    global pub_asr_result
    pub_asr_result = rospy.Publisher('asr_result', AsrResult, queue_size=10)

    # Set up client to talk to Google.
    language_code = 'en-US'
    client = google_speech.SpeechClient()
    # TODO set sample rate etc based on what we get from AndroidAudio messages.
    # The audio encoding arg curently specifies raw 16-bit signed LE samples.
    config = google_types.RecognitionConfig(
        encoding=google_enums.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=args.sample_rate,
        language_code=language_code)
    # TODO add as arg above: speech_context={"phrases": ["words", "here"]}
    streaming_config = google_types.StreamingRecognitionConfig(
        config=config, interim_results=True)

    # Start streaming audio to Google.
    # TODO update stream with buffer coming over ROS...
    with RosAudioStream(args.sample_rate, args.buffer_size) as stream:
        audio_stream_generator = stream.audio_generator()
        requests = (google_types.StreamingRecognizeRequest(
            audio_content=content) for content in audio_stream_generator)

        # Get responses from Google.
        responses = client.streaming_recognize(streaming_config, requests)
        print "*****"

        # Use the ASR responses.
        handle_responses(responses)

    try:
        rospy.spin()
    except KeyboardInterrupt:
        print "Shutting down"


if __name__ == '__main__':
    main()
