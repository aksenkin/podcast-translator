#!/bin/bash
#
# Queue Processor Cron Job Wrapper
# This script is executed by OpenClaw cron job to process videos from queue
#

set -e

# Change to script directory
cd /home/clawd/.openclaw/workspace/skills/podcast-translator

# Log start
echo "=== Queue Processor Cron Job Started: $(date) ===" >> /tmp/queue-processor-cron.log

# Run queue processor
python3 queue_processor.py --max-videos 2 >> /tmp/queue-processor-cron.log 2>&1

# Log completion
echo "=== Queue Processor Cron Job Completed: $(date) ===" >> /tmp/queue-processor-cron.log
echo "" >> /tmp/queue-processor-cron.log
