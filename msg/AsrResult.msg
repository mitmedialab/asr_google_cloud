# Message for sending automatic speech recognition results.

# Standard ROS header.
Header header

# The top ASR result.
string  transcription

# The reported confidence level that this result is correct.
float64 confidence

# List of words in the transcribtion with start and end timestamp.
Words[] words_list
