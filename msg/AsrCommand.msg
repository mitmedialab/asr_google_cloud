# Message for telling the ASR node to start or stop streaming audio to Google
# for processing.

# Standard ROS header.
Header header

# Command. Use the constants defined below.
int8 command

# Commands. The ASR node can publish results (transcript plus confidence value)
# for three kinds of things:
# (1) the final result (i.e., the final result with the highest confidence),
# (2) interim results that are not final, with a stability measure indicating
#     how likely it is that the result will change, and
# (3) alternative results, which are other phrases that might be what you said,
#     but aren't as good a guess as the top alternative
# Thus, you can tell the ASR node to start or stop sending any of these.
int8 START_ALL = 0
int8 START_FINAL = 1
int8 START_ALTERNATIVES = 2
int8 START_INTERIM = 3
int8 STOP_ALL = 4
int8 STOP_FINAL = 5
int8 STOP_ALTERNATIVES = 6
int8 STOP_INTERIM = 7
