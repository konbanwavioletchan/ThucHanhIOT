"""latency_report.py - Thong ke do tre end-to-end tu du lieu trong InfluxDB.
Bai thuc hanh IoT so 2 - Pham Gia Huy - B23DCAT131

Cach dung:  python latency_report.py --range 30m
  ESP32 -> ThingsBoard   = ts ThingsBoard nhan - sent_ms (NTP tren ESP32)
  ThingsBoard -> Collector = thoi diem collector nhan - ts ThingsBoard
  End-to-end             = tong hai chang tren
"""
import argparse
import os
import sys

import numpy as np
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser()
parser.add_argument("--range", default="30m", help="khoang thoi gian, vd 15m, 30m, 1h")
args = parser.parse_args()

client = InfluxDBClient(url=os.getenv("INFLUX_URL"), token=os.getenv("INFLUX_TOKEN"), org=os.getenv("INFLUX_ORG"))
bucket = os.getenv("INFLUX_BUCKET")
query = f'''from(bucket: "{bucket}")
  |> range(start: -{args.range})
  |> filter(fn: (r) => r._measurement == "sensor_raw")
  |> filter(fn: (r) => r._field == "device_to_tb_ms" or r._field == "tb_to_collector_ms" or r._field == "sequence")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")'''
df = client.query_api().query_data_frame(query)
client.close()
if isinstance(df, list):
    df = df[0] if df else None
if df is None or df.empty:
    sys.exit(f"Khong co du lieu trong {args.range} gan nhat.")

# bo ban tin cua firmware cu chua co sent_ms (-1) va ban tin collector lay bu khi khoi dong (-1)
df = df[(df["device_to_tb_ms"] >= 0) & (df["tb_to_collector_ms"] >= 0)]
d2t = df["device_to_tb_ms"].to_numpy()
t2c = df["tb_to_collector_ms"].to_numpy()
e2e = d2t + t2c


def line(name, v):
    p50, p95, p99 = np.percentile(v, [50, 95, 99])
    print(f"  {name:<24}: mean={v.mean():9.1f}  P50={p50:9.1f}  P95={p95:9.1f}  "
          f"P99={p99:9.1f}  min={v.min():8.1f}  max={v.max():9.1f} ms")


device = df["device_id"].iloc[0] if "device_id" in df else "ESP32-B23DCAT131"
print(f"== {device} ({args.range}) - Pham Gia Huy B23DCAT131 ==")
print(f"  so ban ghi              : {len(df)}")
line("ESP32 -> ThingsBoard", d2t)
line("ThingsBoard -> Collector", t2c)
line("End-to-end", e2e)
