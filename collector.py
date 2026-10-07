"""collector.py - Lay telemetry tu ThingsBoard Cloud, kiem tra hop le va ghi vao InfluxDB.
Bai thuc hanh IoT so 2 - Pham Gia Huy - B23DCAT131

Luong: ESP32 (Wokwi) --MQTT--> ThingsBoard Cloud --REST API--> collector.py --> InfluxDB
"""
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

STUDENT = os.getenv("STUDENT", "Pham Gia Huy - B23DCAT131")
TB_URL = os.getenv("TB_URL", "https://thingsboard.cloud")
TB_DEVICE_ID = os.getenv("TB_DEVICE_ID", "")
TB_API_KEY = os.getenv("TB_API_KEY", "").strip()
POLL_SECONDS = 5
BACKFILL_MINUTES = int(os.getenv("BACKFILL_MINUTES", "10"))

KEYS = ["device_id", "temperature", "humidity", "distance_cm", "rssi", "sequence", "uptime_s", "sent_ms"]
# HC-SR04 tren Wokwi o muc toi da 400 cm tra ve ~403.5 cm (sai so thoi gian echo) nen noi bien len 450 cm
LIMITS = {"temperature": (-40, 80), "humidity": (0, 100), "distance_cm": (2, 450), "rssi": (-120, 0)}
REQUIRED = ["temperature", "humidity", "distance_cm", "sequence"]


def tb_headers():
    key = TB_API_KEY if TB_API_KEY.startswith("ApiKey ") else f"ApiKey {TB_API_KEY}"
    return {"X-Authorization": key}


def fetch_telemetry(start_ts, end_ts):
    """Doc timeseries cua device tu ThingsBoard, gom cac key theo timestamp."""
    url = f"{TB_URL}/api/plugins/telemetry/DEVICE/{TB_DEVICE_ID}/values/timeseries"
    params = {"keys": ",".join(KEYS), "startTs": start_ts, "endTs": end_ts,
              "limit": 1000, "orderBy": "ASC", "useStrictDataTypes": "true"}
    resp = requests.get(url, headers=tb_headers(), params=params, timeout=10)
    resp.raise_for_status()
    rows = {}
    for key, values in resp.json().items():
        for item in values:
            rows.setdefault(item["ts"], {})[key] = item["value"]
    return [dict(ts=ts, **vals) for ts, vals in sorted(rows.items())]


def validate(row):
    """Tra ve (hop_le, ly_do)."""
    missing = [k for k in REQUIRED if row.get(k) is None]
    if missing:
        return False, f"thieu truong {missing}"
    for key, (low, high) in LIMITS.items():
        if key in row:
            try:
                value = float(row[key])
            except (TypeError, ValueError):
                return False, f"{key} khong phai so"
            if not low <= value <= high:
                return False, f"{key}={value} ngoai mien [{low}, {high}]"
    return True, ""


def main():
    if not TB_API_KEY or not TB_DEVICE_ID:
        sys.exit("Thieu TB_API_KEY hoac TB_DEVICE_ID trong file .env")

    print("=" * 60)
    print(" COLLECTOR: ThingsBoard Cloud -> InfluxDB")
    print(f" Sinh vien : {STUDENT}")
    print(f" Device    : {TB_DEVICE_ID}")
    print(f" InfluxDB  : {os.getenv('INFLUX_URL')}  bucket={os.getenv('INFLUX_BUCKET')}")
    print("=" * 60)

    client = InfluxDBClient(url=os.getenv("INFLUX_URL"), token=os.getenv("INFLUX_TOKEN"),
                            org=os.getenv("INFLUX_ORG"))
    writer = client.write_api(write_options=SYNCHRONOUS)
    bucket = os.getenv("INFLUX_BUCKET")

    start_ms = int(time.time() * 1000)
    last_ts = start_ms - BACKFILL_MINUTES * 60 * 1000   # lay bu du lieu cu khi khoi dong
    # Tiep tuc tu ban tin cuoi cung da co trong InfluxDB de khong ghi de ban tin da luu
    tables = client.query_api().query(f'''from(bucket: "{bucket}") |> range(start: -{BACKFILL_MINUTES + 1}m)
      |> filter(fn: (r) => r._measurement == "sensor_raw" and r._field == "sequence") |> last()''')
    for table in tables:
        for rec in table.records:
            last_ts = max(last_ts, int(rec.get_time().timestamp() * 1000))
    last_seq = None
    stats = {"saved": 0, "rejected": 0, "duplicate": 0, "lost": 0}

    while True:
        try:
            now_ms = int(time.time() * 1000)
            rows = fetch_telemetry(last_ts + 1, now_ms)
            for row in rows:
                last_ts = max(last_ts, row["ts"])
                ok, reason = validate(row)
                if not ok:
                    stats["rejected"] += 1
                    print(f"[REJECT] ts={row['ts']} {reason}")
                    continue

                seq = int(row["sequence"])
                if last_seq is not None:
                    if seq == last_seq:
                        stats["duplicate"] += 1
                        print(f"[DUPLICATE] sequence={seq} bo qua")
                        continue
                    if seq > last_seq + 1:
                        stats["lost"] += seq - last_seq - 1
                        print(f"[WARN] mat {seq - last_seq - 1} ban tin (sequence {last_seq} -> {seq})")
                    elif seq < last_seq:
                        print(f"[INFO] sequence reset {last_seq} -> {seq} (ESP32 khoi dong lai)")
                last_seq = seq

                received_ms = int(time.time() * 1000)
                sent_ms = int(row.get("sent_ms") or 0)
                device_to_tb_ms = row["ts"] - sent_ms if sent_ms > 0 else -1
                # Ban tin lay bu (gui truoc khi collector khoi dong) khong phan anh do tre thuc -> -1
                tb_to_collector_ms = received_ms - row["ts"] if row["ts"] >= start_ms - POLL_SECONDS * 1000 else -1

                point = (Point("sensor_raw")
                         .tag("device_id", str(row.get("device_id", "ESP32-B23DCAT131")))
                         .field("temperature", float(row["temperature"]))
                         .field("humidity", float(row["humidity"]))
                         .field("distance_cm", float(row["distance_cm"]))
                         .field("rssi", int(row.get("rssi", 0)))
                         .field("sequence", seq)
                         .field("uptime_s", int(row.get("uptime_s", 0)))
                         .field("device_to_tb_ms", float(device_to_tb_ms))
                         .field("tb_to_collector_ms", float(tb_to_collector_ms))
                         .time(datetime.fromtimestamp(row["ts"] / 1000, timezone.utc), WritePrecision.MS))
                t0 = time.perf_counter()
                writer.write(bucket=bucket, record=point)
                db_ms = (time.perf_counter() - t0) * 1000
                writer.write(bucket=bucket, record=Point("pipeline_metrics")
                             .tag("device_id", str(row.get("device_id", "ESP32-B23DCAT131")))
                             .field("db_write_ms", db_ms)
                             .field("tb_to_collector_ms", float(tb_to_collector_ms))
                             .field("device_to_tb_ms", float(device_to_tb_ms))
                             .field("saved_count", stats["saved"] + 1)
                             .field("rejected_count", stats["rejected"])
                             .field("duplicate_count", stats["duplicate"])
                             .field("lost_count", stats["lost"])
                             .time(received_ms, WritePrecision.MS))
                stats["saved"] += 1
                ts_text = datetime.fromtimestamp(row["ts"] / 1000).strftime("%H:%M:%S")
                print(f"[{ts_text}] seq={seq:<4} T={float(row['temperature']):6.2f}C "
                      f"H={float(row['humidity']):6.2f}% D={float(row['distance_cm']):7.2f}cm "
                      f"| TB->collector={tb_to_collector_ms}ms db={db_ms:.1f}ms")
                print("  -> Đã lưu thành công vào InfluxDB!")
        except requests.HTTPError as exc:
            print(f"[ERROR] ThingsBoard API: {exc.response.status_code} {exc.response.text[:200]}")
        except requests.RequestException as exc:
            print(f"[ERROR] Khong ket noi duoc ThingsBoard: {exc}")
        except Exception as exc:  # loi InfluxDB, du lieu...
            print(f"[ERROR] {type(exc).__name__}: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCollector stopped.")
