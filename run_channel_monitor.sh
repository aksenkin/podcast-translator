#!/bin/bash
#
# YouTube Channel Monitor Cron Job Wrapper
# This script is executed by OpenClaw cron job to check YouTube channels for new videos
#

set -e

# Change to script directory
cd /home/clawd/.openclaw/workspace/skills/podcast-translator

# Log start
echo "=== YouTube Channel Monitor Cron Job Started: $(date) ===" >> /tmp/channel-monitor-cron.log

# Run channel monitor
python3 channel_monitor.py --videos-per-channel 3 --json-output >> /tmp/channel-monitor-cron.log 2>&1

# Log completion
echo "=== YouTube Channel Monitor Cron Job Completed: $(date) ===" >> /tmp/channel-monitor-cron.log
echo "" >> /tmp/channel-monitor-cron.log
