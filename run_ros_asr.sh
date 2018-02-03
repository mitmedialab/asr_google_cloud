#!/bin/sh
# Jacqueline Kory Westlund
# January 2018
cd "$(rospack find asr_google_cloud)"
pipenv run python src/ros_asr.py
