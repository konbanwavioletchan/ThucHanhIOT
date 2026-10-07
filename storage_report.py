"""storage_report.py - Thong ke luu tru: ti le mat ban tin, trung, tu choi, dung luong bucket, thoi gian truy van.
Bai thuc hanh IoT so 2 - Pham Gia Huy - B23DCAT131

Cach dung:  python storage_report.py --range 30m
"""
import argparse
import os
import subprocess
import sys
import time

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser()
parser.add_argument("--range", default="30m", help="khoang thoi gian tinh ti le mat ban tin")
args = parser.parse_args()

client = InfluxDBClient(url=os.getenv("INFLUX_URL"), token=os.getenv("INFLUX_TOKEN"), org=os.getenv("INFLUX_ORG"))
api = client.query_api()
bucket = os.getenv("INFLUX_BUCKET")


def values(flux):
    return [rec.get_value() for table in api.query(flux) for rec in table.records]


# Ti le mat ban tin theo sequence (moi doan tang lien tuc la mot lan chay ESP32)
seqs = values(f'''from(bucket: "{bucket}") |> range(start: -{args.range})
  |> filter(fn: (r) => r._measurement == "sensor_raw" and r._field == "sequence") |> sort(columns: ["_time"])''')
expected, prev = 0, None
for s in seqs:
    if prev is None or s <= prev:      # bat dau / ESP32 khoi dong lai
        expected += 1
    else:
        expected += s - prev
    prev = s
saved = len(seqs)
lost = expected - saved

# Bo dem cua collector (trung / tu choi) tai thoi diem gan nhat
last = {}
for table in api.query(f'''from(bucket: "{bucket}") |> range(start: -{args.range})
  |> filter(fn: (r) => r._measurement == "pipeline_metrics")
  |> filter(fn: (r) => r._field == "duplicate_count" or r._field == "rejected_count") |> last()'''):
    for rec in table.records:
        last[rec.get_field()] = rec.get_value()

print(f"== Luu tru InfluxDB - bucket {bucket} - Pham Gia Huy B23DCAT131 ==")
print(f"  ban tin du kien ({args.range}) : {expected}, da luu: {saved}, mat: {lost / expected * 100 if expected else 0:.1f}%")
print(f"  ban tin trung              : {last.get('duplicate_count', 0)}")
print(f"  ban tin bi tu choi         : {last.get('rejected_count', 0)}")

# Dung luong du lieu InfluxDB trong container Docker
try:
    size = subprocess.run(["docker", "exec", "influxdb", "du", "-sh", "/var/lib/influxdb2/engine/data"],
                          capture_output=True, text=True, timeout=20).stdout.split()[0]
except (OSError, IndexError, subprocess.TimeoutExpired):
    size = "khong doc duoc"
print(f"  dung luong bucket (TSM)    : {size}")

# Thoi gian truy van du lieu 1h / 24h
for rng in ("1h", "24h"):
    t0 = time.perf_counter()
    n = len(values(f'''from(bucket: "{bucket}") |> range(start: -{rng})
      |> filter(fn: (r) => r._measurement == "sensor_raw" and r._field == "temperature")'''))
    print(f"  truy van {rng:<4}              : {n} ban ghi, {(time.perf_counter() - t0) * 1000:.1f} ms")
client.close()
