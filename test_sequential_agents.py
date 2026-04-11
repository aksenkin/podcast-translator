#!/usr/bin/env python3
"""
Test sequential subagent processing with chat notifications.
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# URLs to test (from failed queue)
TEST_URLS = [
    "https://www.youtube.com/watch?v=fs_Y3gvj7lk",
    "https://www.youtube.com/watch?v=Jov9Mn2Q2s8",
    "https://www.youtube.com/watch?v=bkzMuF7bKqY",
]

def send_chat_notification(url, status, message):
    """Send notification to chat about processing status."""
    emoji = "🎯" if status == "start" else "✅" if status == "complete" else "❌"

    telegram_msg = f"{emoji} **Subagent {status.upper()}**\\n\\n🔗 URL: {url}\\n📝 {message}\\n🕐 {datetime.now().strftime('%H:%M:%S')}"

    try:
        import os
        env = os.environ.copy()
        env["PATH"] = "/home/clawd/.nvm/versions/node/v22.22.0/bin:" + env.get("PATH", "")

        result = subprocess.run(
            ["openclaw", "agent", "--agent", "claude", "--local",
             "--deliver", "--reply-channel", "telegram",
             "--message", telegram_msg],
            capture_output=True,
            text=True,
            timeout=60,
            env=env
        )

        if result.returncode == 0:
            print(f"   📤 Chat notification sent: {status}")
        else:
            print(f"   ⚠️  Chat notification failed (non-critical)")
    except Exception as e:
        print(f"   ⚠️  Could not send notification: {e}")

def spawn_subagent(url, index):
    """Spawn a subagent to process the URL."""
    print(f"\n{'='*60}")
    print(f"🚀 Spawning subagent {index + 1}/{len(TEST_URLS)}")
    print(f"🔗 URL: {url}")
    print(f"{'='*60}\n")

    # Send start notification
    send_chat_notification(url, "start", f"Subagent {index + 1} starting processing")

    # Prepare task for subagent
    task = f"""## Sequential Agent Test - Task {index + 1}

⚠️ CRITICAL: Do NOT install any software.

### Your Mission
You are subagent #{index + 1} in a sequential processing chain.
Your assigned URL: {url}

### Step 1: Acknowledge assignment
echo "STATUS: Subagent {index + 1} acknowledged URL: {url}"
echo "HEARTBEAT: Agent is alive and working..."

### Step 2: Simulate processing (15 seconds)
echo "STATUS: Processing URL..."
sleep 15
echo "SUCCESS: Processing completed"

### Step 3: Create completion manifest
MANIFEST_FILE="/tmp/agent_{index + 1}_manifest.txt"
cat > "$MANIFEST_FILE" << EOF
===OPENCLAW_OUTPUTS_COMPLETE===
agent_number:{index + 1}
url:{url}
status:processing_complete
timestamp:$(date)
duration:15_seconds
===OPENCLAW_OUTPUTS_END===
EOF

echo "===MANIFEST:$MANIFEST_FILE==="

### Step 4: Send completion report to chat
echo "STATUS: Sending completion report to chat..."

openclaw agent --agent claude --local --deliver --reply-channel telegram --message "🎉 **Subagent {index + 1} COMPLETE**

✅ Successfully processed: {url}
🏷️ Agent: #{index + 1}/{len(TEST_URLS)}
⏱️ Processing time: 15 seconds
📁 Manifest: $MANIFEST_FILE
🕐 Completed: $(date)

Sequential test progressing normally!" 2>/dev/null || echo "WARNING: Chat delivery failed (non-critical)"

### Step 5: Final report
echo "SUCCESS: Subagent {index + 1} completed successfully"
echo "REPORT: Agent {index + 1} finished processing {url} - sequential test step complete"
"""

    try:
        import os
        env = os.environ.copy()
        env["PATH"] = "/home/clawd/.nvm/versions/node/v22.22.0/bin:" + env.get("PATH", "")

        result = subprocess.run(
            ["openclaw", "agent", "--agent", "claude", "--local",
             "--message", task,
             "--timeout", "7200"],
            capture_output=True,
            text=True,
            timeout=7300,
            cwd="/home/clawd/.openclaw/workspace/skills/podcast-translator",
            env=env
        )

        success = result.returncode == 0

        if success:
            print(f"✅ Subagent {index + 1} completed successfully")
            send_chat_notification(url, "complete", f"Subagent {index + 1} finished processing")
        else:
            print(f"❌ Subagent {index + 1} failed")
            send_chat_notification(url, "failed", f"Subagent {index + 1} failed: {result.stderr[:100]}")

        return {
            "success": success,
            "url": url,
            "agent": index + 1,
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    except subprocess.TimeoutExpired:
        print(f"❌ Subagent {index + 1} timeout")
        send_chat_notification(url, "failed", "Subagent timeout after 2 hours")
        return {"success": False, "url": url, "error": "timeout"}
    except Exception as e:
        print(f"❌ Subagent {index + 1} error: {e}")
        send_chat_notification(url, "failed", f"Exception: {str(e)}")
        return {"success": False, "url": url, "error": str(e)}

def main():
    """Run sequential subagent test."""
    print("🚀 SEQUENTIAL SUBAGENT TEST")
    print(f"📋 Testing {len(TEST_URLS)} URLs")
    print(f"⏰ Started at: {datetime.now().strftime('%H:%M:%S')}\n")

    results = []

    for i, url in enumerate(TEST_URLS):
        print(f"\n🔄 Processing URL {i + 1}/{len(TEST_URLS)}")
        result = spawn_subagent(url, i)
        results.append(result)

        # Wait a bit between agents
        if i < len(TEST_URLS) - 1:
            print(f"\n⏳ Waiting 5 seconds before next agent...")
            import time
            time.sleep(5)

    # Final summary
    print(f"\n{'='*60}")
    print(f"📊 SEQUENTIAL TEST SUMMARY")
    print(f"{'='*60}")

    success_count = sum(1 for r in results if r['success'])
    fail_count = len(results) - success_count

    print(f"✅ Successful: {success_count}/{len(results)}")
    print(f"❌ Failed: {fail_count}/{len(results)}")

    for i, result in enumerate(results):
        status = "✅" if result['success'] else "❌"
        print(f"   {status} Agent {i + 1}: {result['url']}")

    # Send final summary to chat
    summary_msg = f"📊 **Sequential Test Complete**\\n\\n✅ Successful: {success_count}/{len(results)}\\n❌ Failed: {fail_count}\\n⏰ Finished: {datetime.now().strftime('%H:%M:%S')}\\n\\nAll agents processed their URLs sequentially!"

    try:
        import os
        env = os.environ.copy()
        env["PATH"] = "/home/clawd/.nvm/versions/node/v22.22.0/bin:" + env.get("PATH", "")

        subprocess.run(
            ["openclaw", "agent", "--agent", "claude", "--local",
             "--deliver", "--reply-channel", "telegram",
             "--message", summary_msg],
            capture_output=True,
            text=True,
            timeout=60,
            env=env
        )
    except:
        print("⚠️  Could not send final summary to chat")

    return results

if __name__ == "__main__":
    results = main()
    sys.exit(0 if all(r['success'] for r in results) else 1)
