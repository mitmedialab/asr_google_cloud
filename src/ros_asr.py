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
import rospy  # Get audio data over ROS and publish results.
from r1d1_msgs.msg import AndroidAudio
from std_msgs.msg import Header
from asr_google_cloud.msg import AsrResult
from asr_google_cloud.msg import AsrCommand
import struct
import signal  # Catching SIGINT signal.
import time  # For sleep.


class RosAudioStream(object):
    """ Open an audio stream over ROS as a generator that gives us chunks of
    audio data.
    """
    def __init__(self):
        # Thread-safe buffer of audio data.
        self._buffer = queue.Queue()
        # The audio stream starts out closed.
        self.closed = True
        # We will collect audio data over ROS.
        self._sub_audio = None

    def __enter__(self):
        """ Set up the audio stream. """
        # We collect audio from the stream into a buffer asynchronously with a
        # callback.
        # Use r1d1_msgs/AndroidAudio to get incoming audio stream from the
        # robot's microphone or a standalone android microphone app.
        self._sub_audio = rospy.Subscriber('android_audio', AndroidAudio,
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
        # Unsubscribe from the AndroidAudio messages.
        self._sub_audio.unregister()

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

            # If we shouldn't send data to Google, just return. This is after
            # the buffer has been emptied.
            if not send_data:
                return
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
    publish_final_tmp = publish_final
    is_final = False
    for response in responses:
        if not response.results:
            continue
        # Send results over ROS.
        msg = AsrResult()
        msg.header = Header()
        msg.header.stamp = rospy.Time.now()
        # TODO publish_final, publish_interim, publish_alternatives

        # If we should publish final results..
        if response.results[0].is_final:
            is_final = True
            print("Got final result:\n{}".format(response))
            # TODO publish alternatives
            if publish_alternatives:
                print("TODO publish alternatives")
            msg.transcription = str(response.results[0].alternatives[0].
                                    transcript)
            msg.confidence = response.results[0].alternatives[0].confidence
            pub_asr_result.publish(msg)
            print("*** SENT RESULT ***")
            # Restart streaming to Google so we don't hit the audio limit.
            return
        # If we should publish interim results...
        elif publish_interim:
            # TODO
            print("TODO publish interim results")

    # If we cannot find a response with is_final == true, then output whatever
    # ASR captures to ROS, assuming we got at least one response.
    if not is_final and len(responses) > 0:
        if not responses[0].results:
            print("No results! Can't output anything.")
            return
        msg = AsrResult()
        msg.header = Header()
        msg.header.stamp = rospy.Time.now()
        msg.transcription = str(responses[0].results[0].alternatives[0].
                                transcript)
        msg.confidence = 0.0
        pub_asr_result.publish(msg)


def run_asr(sample_rate):
    """ Stream audio to Google and get results back. """
    while True:
        # If no results streaming is enabled, don't bother streaming audio to
        # Google for processing.
        while not send_data:
            time.sleep(0.05)

        # Set up client to talk to Google.
        language_code = 'en-US'
        client = google_speech.SpeechClient()
        # TODO set sample rate etc from AndroidAudio messages.
        # Audio encoding arg curently specifies raw 16-bit signed LE samples.
        config = google_speech.RecognitionConfig(
            encoding=google_speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            language_code=language_code)
        # TODO add as arg above: speech_context={"phrases": ["words", "here"]}
        streaming_config = google_speech.StreamingRecognitionConfig(
            config=config, interim_results=True)

        # Start streaming audio to Google.
        # TODO update stream with buffer coming over ROS...
        with RosAudioStream() as stream:
            audio_stream_generator = stream.audio_generator()
            requests = (google_speech.StreamingRecognizeRequest(
                audio_content=content) for content in audio_stream_generator)

            # Get responses from Google.
            try:
                responses = client.streaming_recognize(streaming_config,
                                                       requests)
                # Use the ASR responses.
                handle_responses(responses)
            except SystemExit:
                raise
            except Exception as e:
                print(e)
                # A request can only have about ~60s of audio in it; after
                # that, we get an error. So we restart.
                print("Hit audio limit. Restarting...")
                continue


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
    """ Run Google ASR with the audio over ROS. """
    parser = argparse.ArgumentParser(
        description=""" Use the Google Cloud Speech API to get Google ASR
        results for audio streamed over ROS. """)
    parser.add_argument("-r, --sample_rate", type=int, nargs='?',
                        dest="sample_rate", action='store', default=44100,
                        help="""Sample rate at which audio will be streamed.
                        Defaults to 44100.""")
    # Get arguments.
    args = parser.parse_args()
    print("Got arguments: {}".format(args))
    global sample_rate
    sample_rate = args.sample_rate

    # ROS node setup:
    # TODO If running on a network where DNS does not resolve local hostnames,
    # get the public IP address of this machine and export to the environment
    # variable $ROS_IP to set the public address of this node, so the user
    # doesn't have to remember to do this before starting the node.
    rospy.init_node('google_asr_node', anonymous=False)

    # Publish ASR results as asr_google_cloud/AsrResult messages.
    global pub_asr_result
    pub_asr_result = rospy.Publisher('asr_result', AsrResult, queue_size=10)

    # Subscribe to basic commands to tell this node to start or stop processing
    # audio and streaming to Google, as well as what results to publish.
    global sub_asr_command
    sub_asr_command = rospy.Subscriber('asr_command', AsrCommand,
                                       on_asr_command)

    # Only start ASR when we receive a start message and start getting audio.
    # We have to wait to get audio so we know what audio stream parameters to
    # use (we can assume, e.g., that the sample rate will be 44100 but we could
    # be wrong).
    # TODO do this later
    #global need_to_start
    #need_to_start = True

    # Set up signal handler to catch SIGINT (e.g., ctrl-c).
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Set up reasonable defaults for now.
    global publish_interim
    publish_interim = False
    global publish_alternatives
    publish_alternatives = False
    global publish_final
    publish_final = True
    global send_data
    send_data = True
    run_asr(sample_rate)


def signal_handler(sig, frame):
    """ Handle signals caught. """
    if sig == signal.SIGINT or sig == signal.SIGTERM:
        pub_asr_result.unregister()
        sub_asr_command.unregister()
        print("Told to exit! Exiting.")
        exit("Interrupted by user.")


if __name__ == '__main__':
    main()
