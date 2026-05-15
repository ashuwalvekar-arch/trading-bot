import schedule
import subprocess
import time

print("AI Auto Trainer Started")


def retrain():

    print("Starting AI retraining...")

    try:

        subprocess.run(
            ["python", "train_ai.py"],
            check=True
        )

        print("AI retraining completed")

    except Exception as e:

        print(f"Retraining failed: {e}")


# TEST MODE
# Retrain every 60 seconds
schedule.every(60).seconds.do(retrain)

# First training immediately
retrain()

while True:

    schedule.run_pending()

    time.sleep(1)