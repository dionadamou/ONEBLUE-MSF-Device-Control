from msf_client import MSFClient
import time

# ---- dummy partner hardware ----
def turn_valve_on():
    print("[PARTNER] Turning valve ON")
    time.sleep(1)

def aspirate_sample():
    print("[PARTNER] Aspirating sample...")
    time.sleep(2)
    print("[PARTNER] Sample aspirated")

def run_spectroscopy():
    print("[PARTNER] Spectroscopy started")
    for i in range(5):
        print(f"[PARTNER] Measuring... {i+1}/5")
        time.sleep(1)
    print("[PARTNER] Spectroscopy finished")

# ---- sequence ----
msf = MSFClient("10.0.46.98", port=5001)

msf.set_power(True, "start run")


msf.initialisation()
msf.filter_loading()

# run filtration until 50 mL delivered (auto stop)
msf.sample_filtration(volume_ml=30, flow=17)


turn_valve_on()
aspirate_sample()


print("[PARTNER] Starting MSF cleaning (non-blocking)")
clean_job = msf.run("cleaning")

run_spectroscopy()

print("[PARTNER] Waiting for MSF cleaning to finish")
msf.wait_for_job(clean_job)

print("DONE")
