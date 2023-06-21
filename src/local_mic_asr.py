from __future__ import division

import json
import time
import re
import sys
import base64
import websockets
import asyncio
from signal import SIGINT, SIGTERM

from google.cloud import speech
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

URL = f"wss://api.assemblyai.com/v2/realtime/ws?sample_rate={SAMPLE_RATE}"

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
        self._input_device_index = 0
        
        for i in range(self._audio_interface.get_device_count()):
            device_info = self._audio_interface.get_device_info_by_index(i)
            try:
                if "USB audio CODEC" in device_info.get('name'):
                    self._input_device_index = i
                    break
            except:
                pass
        
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=self._num_channels,
            rate=self._rate,
            input=True,
            frames_per_buffer=self._chunk_size,
            input_device_index=self._input_device_index
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

async def send_receive(recorder: ResumableMicrophoneStream):
    async with websockets.connect(
        URL,
        extra_headers=(("Authorization", ASSEMBLYAI_API_KEY),),
        ping_interval=5,
        ping_timeout=20
    ) as _ws:
        await asyncio.sleep(0.1)
        print("Receiving SessionBegins ...")
        session_begins = await _ws.recv()
        print(session_begins)
        print("Sending messages ...")
        async def send():
            while True:
                # print("running send")
                if send_data:
                    try:
                        data = recorder._audio_stream.read(recorder._chunk_size, exception_on_overflow=False)
                        data = base64.b64encode(data).decode("utf-8")
                        json_data = json.dumps({"audio_data":str(data)})
                        await _ws.send(json_data)
                    except websockets.exceptions.ConnectionClosedError as e:
                        # print(e)
                        assert e.code == 4008
                        break
                    except Exception as e:
                        # print(e)
                        assert False, "Not a websocket 4008 error"
                    await asyncio.sleep(0.01)
        
        async def receive():
            while True:
                try:
                    result_str = await _ws.recv()
                    result = json.loads(result_str)
                    if (result['message_type']=="FinalTranscript" and result['text']):
                        print("FINAL: ", result['text'])
                        msg = AsrResult()
                        msg.header = Header()
                        msg.header.stamp = rospy.Time.now()
                        msg.transcription = result['text']
                        msg.confidence = result['confidence']
                        for i in result['words']:
                            w = Words()
                            w.word = i['text']
                            w.start_time = i['start']
                            w.end_time = i['end']
                            msg.words_list.append(w)
                        pub_asr_result.publish(msg)
                        # rospy.loginfo(msg)
                    elif (result['message_type']=='SessionBegins'):
                        print(result)
                    elif (result['message_type']=='PartialTranscript' and result['text']):
                        msg = AsrResult()
                        msg.header = Header()
                        msg.header.stamp = rospy.Time.now()
                        msg.transcription = result['text']
                        msg.confidence = result['confidence']
                        for i in result['words']:
                            w = Words()
                            w.word = i['text']
                            w.start_time = i['start']
                            w.end_time = i['end']
                            msg.words_list.append(w)
                        pub_asr_result.publish(msg)
                        print("**", result['text']) # for debugging
                        pass
                except websockets.exceptions.ConnectionClosedError as e:
                    # print(e)
                    assert e.code == 4008
                    break
                except Exception as e:
                    # print(e)
                    assert False, "Not a websocket 4008 error"
        
        send_result, receive_result = await asyncio.gather(send(), receive())

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
    send_data = False
    
    mic_manager = ResumableMicrophoneStream(SAMPLE_RATE, CHUNK_SIZE)

    while True:
        if True:
            if mic_manager.closed:
                mic_manager.__enter__()
            curr_loop = asyncio.get_event_loop()
            main_task = asyncio.ensure_future(send_receive(mic_manager))
            for signal in [SIGINT, SIGTERM]:
                curr_loop.add_signal_handler(signal, main_task.cancel)
            try:
                curr_loop.run_until_complete(main_task)
            except Exception as e:
                mic_manager.__exit__(0, 0, 0)
                print(e)
    # '''

if __name__ == '__main__':
    main()