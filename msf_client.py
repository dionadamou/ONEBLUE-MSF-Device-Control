#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import requests
import threading
import json


class MSFClient:
    def __init__(self, host="10.0.46.98", port=5001, api_key=None, show_events=True):
        self.base = f"http://{host}:{port}"
        self.headers = {}
        if api_key:
            self.headers["X-API-Key"] = api_key

        self.show_events = show_events
        self._stop_event_thread = False
        self._connected = False
        self._hello_seen = False

        if show_events:
            threading.Thread(target=self._event_listener, daemon=True).start()
            for _ in range(50):  # up to 5 seconds
                if self._connected:
                    break
                time.sleep(0.1)

    # -------------------------
    # HTTP helpers
    # -------------------------
    def _post(self, path, json=None):
        return requests.post(f"{self.base}{path}", json=json, headers=self.headers)

    def _get(self, path):
        return requests.get(f"{self.base}{path}", headers=self.headers)

    def emergency_stop(self, reason="remote estop"):
        return self._post("/api/emergency_stop", {"reason": reason})

    def set_power(self, enable: bool, reason="client power"):
        return self._post("/api/power", {"enable": bool(enable), "reason": reason})

    def get_status(self):
        return self._get("/status").json()

    # -------------------------
    # SSE events
    # -------------------------
    def _event_listener(self):
        try:
            with requests.get(f"{self.base}/api/events", headers=self.headers, stream=True) as r:
                for line in r.iter_lines():
                    if self._stop_event_thread:
                        break
                    if not line:
                        continue
                    if line.startswith(b"data: "):
                        payload = line[6:]
                        try:
                            ev = json.loads(payload)
                            self._print_event(ev)
                        except Exception:
                            pass
        except Exception as e:
            print(f"[MSF] Event stream error: {e}")

    def _print_event(self, ev):
        t = ev.get("type")
        msg = ev.get("msg", "")
        label = ev.get("label")
        status = ev.get("status")

        if t == "hello":
            if not self._hello_seen:
                print("[MSF] Connected to MSF event stream")
                self._hello_seen = True
                self._connected = True
            return

        if t in ("ao", "wait"):
            return

        if t == "step":
            print(f"[MSF] STEP: {msg}")
        elif t == "status":
            print(f"[MSF] STATUS: {msg}")
        elif t == "job":
            print(f"[MSF] JOB EVENT: {label} -> {status}")
        elif t == "control":
            print(f"[MSF] CONTROL: {msg}")
        else:
            print(f"[MSF] EVENT: {ev}")

    # -------------------------
    # Job runner
    # -------------------------
    def run(self, step, **params):
        payload = {"step": step}
        payload.update(params or {})
        r = self._post("/api/run", payload)
        resp = r.json()

        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "Unknown error"))

        print(f"[MSF] Started: {step}")
        return resp["job_id"]

    def wait_for_job(self, job_id):
        while True:
            jr = self._get(f"/api/jobs/{job_id}").json()
            status = jr["job"]["status"]

            if status in ("done", "error"):
                print(f"[MSF] Finished: {status}")
                return status

            time.sleep(0.5)

    # -------------------------
    # High-level steps
    # -------------------------
    def initialisation(self):
        return self.wait_for_job(self.run("initialisation"))

    def filter_loading(self):
        return self.wait_for_job(self.run("filter_loading"))

    def sample_filtration(self, *, volume_ml=None, duration_s=None, flow=None):
        """
        Preferred: volume_ml (API auto-stops when target reached)
        Fallback: duration_s (sleep then stop_sample)
        Optional: flow override (if your /api/run supports it)
        """
        params = {}
        if flow is not None:
            params["flow"] = float(flow)

        if volume_ml is not None:
            params["volume_ml"] = float(volume_ml)
            job = self.run("sample_filtration", **params)
            return self.wait_for_job(job)

        # legacy duration mode
        if duration_s is None:
            duration_s = 60

        job = self.run("sample_filtration", **params)
        print(f"[MSF] Filtration for {duration_s}s...")
        time.sleep(float(duration_s))
        print("[MSF] Sending stop signal...")
        self._post("/api/stop_sample")
        return self.wait_for_job(job)

    def cleaning(self, flow=None):
        params = {}
        if flow is not None:
            params["flow"] = float(flow)
        return self.wait_for_job(self.run("cleaning", **params))
