"""Khoi tao InfluxDB lan dau: user, org ptit_org, bucket iot_bucket (retention 7 ngay).
Pham Gia Huy - B23DCAT131"""
import json
import os
import urllib.request

from dotenv import load_dotenv

load_dotenv()
URL = os.getenv("INFLUX_URL", "http://localhost:8086")

with urllib.request.urlopen(f"{URL}/api/v2/setup") as resp:
    allowed = json.load(resp).get("allowed")

if not allowed:
    print("InfluxDB da duoc thiet lap tu truoc.")
else:
    body = json.dumps({
        "username": os.environ["INFLUX_USERNAME"],
        "password": os.environ["INFLUX_PASSWORD"],
        "org": os.environ["INFLUX_ORG"],
        "bucket": os.environ["INFLUX_BUCKET"],
        "retentionPeriodSeconds": 7 * 24 * 3600,
        "token": os.environ["INFLUX_TOKEN"],
    }).encode()
    req = urllib.request.Request(f"{URL}/api/v2/setup", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        result = json.load(resp)
    print(f"Da tao org '{result['org']['name']}', bucket '{result['bucket']['name']}' "
          f"(retention 7 ngay), user '{result['user']['name']}'")
