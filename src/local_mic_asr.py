#!/usr/bin/python
"""
Jacqueline Kory Westlund
August 2017

This code is adapted from the Google Cloud Platform python examples, which say:
Copyright 2017 Google Inc. All Rights Reserved.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License.  You may obtain a copy of the
License at
     http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, either express or implied.  See the License for the
specific language governing permissions and limitations under the License.


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
import pyaudio  # Get audio from local microphone.
from six.moves import queue  # Thread-safe queue for buffering audio data.
from google.cloud import speech as google_speech
from google.cloud.speech import enums as google_enums
from google.cloud.speech import types as google_types


class LocalMicStream(object):
    """ Open an audio stream from a local microphone as a generator that gives
    us chunks of audio data.
    """
    def __init__(self, sample_rate, buffer_size):
        # Keep the provided sample rate and buffer size for setting up our
        # audio stream later.
        self._sample_rate = sample_rate
        self._buffer_size = buffer_size
        # Thread-safe buffer of audio data.
        self._buffer = queue.Queue()
        # The audio stream starts out closed.
        self.closed = True

    def __enter__(self):
        """ Set up the audio stream. """
        # Initialize pyaudio.
        self._pyaud = pyaudio.PyAudio()

        # Open stream. The Google Cloud Speech API only supports 1-channel
        # (i.e. mono) audio, so we don't make that a tunable parameter. We
        # collect audio from the stream into a buffer asynchronously with a
        # callback.
        self._stream = self._pyaud.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self._sample_rate,
            input=True,
            frames_per_buffer=self._buffer_size,
            stream_callback=self._fill_buffer)
        # The stream is now open.
        self.closed = False
        return self

    def __exit__(self, type_, value, traceback):
        """ Make sure we stop and close the audio stream when we exit. """
        self._stream.stop_stream()
        self._stream.close()
        # Set the closed flag so the generator will stop looping.
        self.closed = True
        # Tell the generator to terminate by adding None to the buffer.
        self._buffer.put(None)
        # Terminate pyaudio too.
        self._pyaud.terminate()

    def _fill_buffer(self, data, frames, time, status_flags):
        """ Collect audio data from the stream and put it in our buffer. """
        self._buffer.put(data)
        return None, pyaudio.paContinue

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


def handle_responses(responses):
    """ Iterate through any responses received. """
    for response in responses:
        if not response.results:
            continue
        print response


def main():
    """ Run Google ASR with the local microphone stream. """

    parser = argparse.ArgumentParser(
        description=""" Use the Google Cloud Speech API to get Google ASR
        results for audio streamed from the local microphone. """)
    parser.add_argument("-r, --sample_rate", type=int, nargs='?',
                        dest="sample_rate", action='store', default=16000,
                        help="""Sample rate at which audio will be streamed.
                        Defaults to 16000.""")
    parser.add_argument("-b, --buffer_size", type=int, nargs='?',
                        dest="buffer_size", action='store', default=1600,
                        help="""Buffer size (also called chunk size) for audio
                        being collected. Defaults to 1600 (i.e., one tenth of
                        the default sample rate, or 100ms).""")
    # Get arguments.
    args = parser.parse_args()
    print "Got arguments: {}".format(args)

    # Set up client to talk to Google.
    language_code = 'en-US'
    client = google_speech.SpeechClient()
    # The audio encoding arg curently specifies raw 16-bit signed LE samples.
    config = google_types.RecognitionConfig(
        encoding=google_enums.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=args.sample_rate,
        language_code=language_code)
    # TODO add as arg above: speech_context={"phrases": ["words", "here"]}
    streaming_config = google_types.StreamingRecognitionConfig(
        config=config, interim_results=True)

    # Start streaming audio to Google.
    with LocalMicStream(args.sample_rate, args.buffer_size) as stream:
        audio_stream_generator = stream.audio_generator()
        requests = (google_types.StreamingRecognizeRequest(
            audio_content=content) for content in audio_stream_generator)

        # Get responses from Google.
        responses = client.streaming_recognize(streaming_config, requests)

        # Use the ASR responses.
        handle_responses(responses)


if __name__ == '__main__':
    main()
