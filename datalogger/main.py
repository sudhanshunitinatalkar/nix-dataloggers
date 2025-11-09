import time
import threading
import schedule
import store
import modbus
import publish

def job_collect():
    print("Running collection...")
    try:
        data = modbus.read_data()
        store.save_reading(data)
    except Exception as e:
        print(f"Collection error: {e}")

def job_publish():
    print("Running publisher...")
    try:
        publish.publish_pending()
    except Exception as e:
        print(f"Publisher error: {e}")

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    print("Starting Datalogger Main Wrapper...")
    store.init_db()

    # Schedule jobs
    # Collect data every 10 seconds
    schedule.every(10).seconds.do(job_collect)
    # Attempt to publish every 30 seconds
    schedule.every(30).seconds.do(job_publish)

    # Run immediately on startup once
    job_collect()
    job_publish()

    run_scheduler()