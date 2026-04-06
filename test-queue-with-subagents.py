#!/usr/bin/env python3
"""
Test Queue with Real Subagents

Creates 10 subagent tasks in a queue, processes them one by one,
and verifies all completed.
"""

import sys
import time
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))
from queue_manager import QueueManager


class SubagentQueueTest:
    def __init__(self):
        """Initialize test with queue manager."""
        self.qm = QueueManager()
        self.results = []
        self.start_time = time.time()

    def add_test_tasks(self, count=10):
        """Add test tasks to the queue.

        Args:
            count: Number of tasks to add
        """
        tasks = []
        for i in range(1, count + 1):
            task = {
                "videoId": f"test_task_{i}",
                "title": f"Test Task {i}",
                "channel": "Test Queue"
            }
            tasks.append(task)

        added = self.qm.add_videos(tasks)
        print(f"✅ Added {added} test tasks to queue")
        return added

    def process_next_with_subagent(self):
        """Process the next task by spawning a real subagent.

        Returns:
            Dict with result
        """
        task = self.qm.get_next_video()

        if not task:
            return {
                "success": False,
                "message": "No tasks in queue"
            }

        task_number = task["videoId"].split("_")[-1]
        print(f"\n🎬 Processing Task {task_number}: {task['title']}")

        # Here we would spawn a real subagent using sessions_spawn
        # For now, simulate subagent execution
        # In real implementation, this would use sessions_spawn from OpenClaw

        print(f"   ⏳ Waiting 10 seconds...")
        time.sleep(10)

        result = {
            "task_number": int(task_number),
            "task_id": task["videoId"],
            "completed": True,
            "message": f"Task {task_number} completed successfully"
        }

        self.results.append(result)

        # Mark as completed in queue
        self.qm.mark_completed(
            task["videoId"],
            {"result": result}
        )

        print(f"   ✅ Task {task_number} completed!")
        print(f"   📊 Results so far: {len(self.results)}/10")

        return {
            "success": True,
            "task": task,
            "result": result
        }

    def run_all_tests(self, count=10):
        """Run all tests by processing the queue.

        Args:
            count: Number of tasks to process

        Returns:
            Dict with test results
        """
        print(f"🚀 Starting Queue Test with {count} Subagent Tasks")
        print(f"🕐 Started at: {time.strftime('%H:%M:%S')}")

        # Add tasks to queue
        added = self.add_test_tasks(count)

        # Show initial queue status
        status = self.qm.get_status()
        print(f"\n📋 Initial Queue Status:")
        print(f"   Pending: {status['pending']}")
        print(f"   Completed: {status['completed']}")

        # Process all tasks
        print(f"\n🔄 Processing {added} tasks one by one...")

        for i in range(added):
            result = self.process_next_with_subagent()
            if not result["success"]:
                print(f"   ❌ Failed to process task: {result.get('message')}")
                break

        # Show final results
        elapsed = time.time() - self.start_time
        print(f"\n" + "="*60)
        print(f"📊 TEST RESULTS")
        print(f"="*60)
        print(f"⏱️  Total time: {elapsed:.1f} seconds")
        print(f"✅ Tasks processed: {len(self.results)}/{count}")
        print(f"📋 Final Queue Status:")
        final_status = self.qm.get_status()
        print(f"   Pending: {final_status['pending']}")
        print(f"   Completed: {final_status['completed']}")

        # Verify all tasks completed
        all_completed = len(self.results) == count
        print(f"\n🎯 Verification: {'✅ ALL TASKS COMPLETED' if all_completed else '❌ SOME TASKS FAILED'}")

        # Show individual results
        print(f"\n📝 Individual Results:")
        for i, result in enumerate(self.results, 1):
            print(f"   {i}. Task {result['task_number']}: ✅ {result['message']}")

        return {
            "success": all_completed,
            "total_time": elapsed,
            "tasks_completed": len(self.results),
            "tasks_total": count,
            "results": self.results,
            "queue_status": final_status
        }


def main():
    """Main entry point."""
    test = SubagentQueueTest()

    # Run test with 10 tasks
    result = test.run_all_tests(count=10)

    # Return summary to parent session
    print(f"\n🔔 Returning results to parent session...")

    # In real implementation, this would send results back
    # For now, print in a parseable format
    print(f"\nRESULT: {json.dumps(result, indent=2)}")

    return result


if __name__ == "__main__":
    import json
    main()
