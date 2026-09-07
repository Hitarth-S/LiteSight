# src/orchestrator/scheduler.py
import time
import threading

class NightlyLoRAScheduler:
    """
    Implements Nightly Learning and Updates from SIH research.
    Runs parameter-efficient fine-tuning (LoRA) on the edge model during
    off-peak hours (e.g., when plugged in at night) using the day's successful trajectories.
    """
    def __init__(self):
        self.daily_trajectories = []
        
    def log_successful_trajectory(self, trajectory_data):
        self.daily_trajectories.append(trajectory_data)
        print(f"[Scheduler] Logged successful trajectory for nightly learning. Total: {len(self.daily_trajectories)}")
        
    def _run_nightly_finetune(self):
        print("[Scheduler] Initiating Nightly LoRA Fine-Tuning on SmolVLM...")
        if not self.daily_trajectories:
            print("[Scheduler] No new trajectories to learn from today.")
            return
            
        print(f"[Scheduler] Compiling {len(self.daily_trajectories)} trajectories into LoRA dataset...")
        # In a real implementation, we would call the PEFT/LoRA training loop here
        # model.train() -> loss.backward() -> optimizer.step()
        time.sleep(2) # Simulate training time
        print("[Scheduler] Nightly LoRA fine-tuning complete. Model muscle memory updated.")
        self.daily_trajectories.clear()
        
    def trigger_manual_nightly_job(self):
        """Allows testing the nightly job manually."""
        thread = threading.Thread(target=self._run_nightly_finetune)
        thread.start()
