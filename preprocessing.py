"""preprocessing.py - Tien xu ly du lieu IoT tu InfluxDB.
Bai thuc hanh IoT so 2 - Pham Gia Huy - B23DCAT131

Cac buoc: doc theo khoang thoi gian -> loai trung -> missing values -> outlier (IQR)
-> resampling 1 phut -> rolling mean, delta -> chuan hoa Z-score & Min-Max
-> ghi measurement moi `sensor_processed` + xuat CSV.
"""
import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

STUDENT = os.getenv("STUDENT", "Pham Gia Huy - B23DCAT131")
SENSORS = ["temperature", "humidity", "distance_cm"]
LIMITS = {"temperature": (-40, 80), "humidity": (0, 100), "distance_cm": (2, 450)}
OUTPUT = Path(__file__).resolve().parent / "output"


def read_raw(client, bucket, time_range):
    query = f'''from(bucket: "{bucket}")
  |> range(start: {time_range})
  |> filter(fn: (r) => r._measurement == "sensor_raw")
  |> filter(fn: (r) => contains(value: r._field, set: ["temperature", "humidity", "distance_cm"]))
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", "device_id", "temperature", "humidity", "distance_cm"])'''
    frame = client.query_api().query_data_frame(query)
    if isinstance(frame, list):
        frame = pd.concat(frame, ignore_index=True) if frame else pd.DataFrame()
    if frame.empty:
        return frame
    frame["_time"] = pd.to_datetime(frame["_time"], utc=True)
    return frame.set_index("_time").sort_index()


def transform(raw, interval="1min"):
    data = raw[SENSORS].copy()
    report = {"raw_rows": len(data)}

    # 1. Loai ban ghi trung timestamp
    data = data[~data.index.duplicated(keep="last")]
    report["duplicates_removed"] = report["raw_rows"] - len(data)

    # 2. Gia tri ngoai mien vat ly -> NaN
    for col, (low, high) in LIMITS.items():
        data.loc[(data[col] < low) | (data[col] > high), col] = np.nan

    # 3. Phat hien outlier bang IQR -> NaN
    outliers = 0
    for col in SENSORS:
        q1, q3 = data[col].quantile([0.25, 0.75])
        iqr = q3 - q1
        if pd.notna(iqr) and iqr > 0:
            mask = (data[col] < q1 - 1.5 * iqr) | (data[col] > q3 + 1.5 * iqr)
            outliers += int(mask.sum())
            data.loc[mask, col] = np.nan
    report["outliers_iqr"] = outliers

    # 4. Missing values: noi suy theo thoi gian -> ffill -> bfill
    report["missing_before"] = int(data.isna().sum().sum())
    data = data.interpolate(method="time").ffill().bfill()
    report["missing_after"] = int(data.isna().sum().sum())

    # 5. Resampling theo cua so thoi gian
    result = data.resample(interval).mean().interpolate(method="time").ffill().bfill()
    report["resampled_rows"] = len(result)

    # 6. Dac trung + chuan hoa
    for col in SENSORS:
        series = result[col]
        result[f"{col}_rolling_mean"] = series.rolling(3, min_periods=1).mean()
        result[f"{col}_delta"] = series.diff().fillna(0)
        std = series.std(ddof=0)
        result[f"{col}_zscore"] = 0.0 if not std else (series - series.mean()) / std
        span = series.max() - series.min()
        result[f"{col}_norm"] = 0.0 if not span else (series - series.min()) / span
    return result.round(4), report


def process_once(time_range, interval):
    client = InfluxDBClient(url=os.getenv("INFLUX_URL"), token=os.getenv("INFLUX_TOKEN"),
                            org=os.getenv("INFLUX_ORG"))
    bucket = os.getenv("INFLUX_BUCKET")
    raw = read_raw(client, bucket, time_range)
    if raw.empty:
        print("Chua co du lieu sensor_raw trong khoang thoi gian nay.")
        client.close()
        return

    processed_all = []
    writer = client.write_api(write_options=SYNCHRONOUS)
    for device_id, device_raw in raw.groupby("device_id"):
        processed, report = transform(device_raw, interval)
        points = []
        for ts, row in processed.iterrows():
            p = Point("sensor_processed").tag("device_id", device_id).tag("pipeline", "iqr-interp-resample-norm")
            for name, value in row.items():
                p.field(name, float(value))
            points.append(p.time(ts.to_pydatetime(), WritePrecision.MS))
        writer.write(bucket=bucket, record=points)
        processed_all.append(processed.assign(device_id=device_id))

        print(f"Device: {device_id}")
        print(f"  So ban ghi raw              : {report['raw_rows']}")
        print(f"  Ban ghi trung da loai       : {report['duplicates_removed']}")
        print(f"  Outlier phat hien (IQR)     : {report['outliers_iqr']}")
        print(f"  Missing truoc / sau xu ly   : {report['missing_before']} / {report['missing_after']}")
        print(f"  So ban ghi sau resample {interval}: {report['resampled_rows']}")
        print(f"  -> Da ghi {len(points)} diem vao measurement 'sensor_processed'")
    writer.close()
    client.close()

    OUTPUT.mkdir(exist_ok=True)
    raw.to_csv(OUTPUT / "raw_data.csv")
    out = pd.concat(processed_all)
    out.to_csv(OUTPUT / "processed_data.csv")
    print(f"  -> Xuat {OUTPUT / 'raw_data.csv'} va {OUTPUT / 'processed_data.csv'}")
    with pd.option_context("display.width", 160, "display.max_columns", 8):
        print("\n5 dong cuoi sau tien xu ly:")
        print(out[["temperature", "temperature_rolling_mean", "temperature_delta",
                   "temperature_norm", "humidity", "distance_cm"]].tail())


def main():
    parser = argparse.ArgumentParser(description="Tien xu ly du lieu IoT")
    parser.add_argument("--range", default="-2h", dest="time_range", help="vd: -1h, -24h")
    parser.add_argument("--interval", default="1min", help="cua so resample, vd: 30s, 1min")
    parser.add_argument("--watch", type=int, default=0, help="chay lai moi N giay (0 = chay 1 lan)")
    args = parser.parse_args()

    print("=" * 60)
    print(" PREPROCESSING: InfluxDB sensor_raw -> sensor_processed")
    print(f" Sinh vien : {STUDENT}")
    print(f" Khoang thoi gian: {args.time_range} | Resample: {args.interval}")
    print("=" * 60)
    while True:
        print(f"\n[{time.strftime('%H:%M:%S')}] Bat dau tien xu ly")
        try:
            process_once(args.time_range, args.interval)
        except Exception as exc:
            print(f"[ERROR] {type(exc).__name__}: {exc}")
        if not args.watch:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPreprocessing stopped.")
