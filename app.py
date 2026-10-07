"""app.py - Dashboard Streamlit giam sat du lieu IoT real-time.
Bai thuc hanh IoT so 2 - Pham Gia Huy - B23DCAT131

Chay: python -m streamlit run app.py
"""
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

load_dotenv()
STUDENT_NAME = "Phạm Gia Huy"
STUDENT_ID = "B23DCAT131"
BUCKET = os.getenv("INFLUX_BUCKET", "iot_bucket")

st.set_page_config(page_title=f"IoT Dashboard - {STUDENT_ID}", page_icon="📡", layout="wide")


@st.cache_resource
def get_client():
    return InfluxDBClient(url=os.getenv("INFLUX_URL"), token=os.getenv("INFLUX_TOKEN"),
                          org=os.getenv("INFLUX_ORG"))


def query(measurement, time_range, fields):
    field_set = ", ".join(f'"{f}"' for f in fields)
    flux = f'''from(bucket: "{BUCKET}")
  |> range(start: {time_range})
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => contains(value: r._field, set: [{field_set}]))
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")'''
    frame = get_client().query_api().query_data_frame(flux)
    if isinstance(frame, list):
        frame = pd.concat(frame, ignore_index=True) if frame else pd.DataFrame()
    if frame.empty:
        return frame
    frame["_time"] = pd.to_datetime(frame["_time"]).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    return frame.set_index("_time").sort_index()[[f for f in fields if f in frame.columns]]


st.markdown(
    f"""
    <div style="padding:14px 20px;border-radius:10px;background:linear-gradient(90deg,#0b5394,#1c7ed6);color:white">
      <div style="font-size:26px;font-weight:700">📡 Dashboard giám sát dữ liệu IoT real-time</div>
      <div style="font-size:16px;margin-top:4px">Bài thực hành số 2 — Thu thập, lưu trữ và tiền xử lý dữ liệu IoT (INT14149)</div>
      <div style="font-size:16px;margin-top:4px"><b>Sinh viên:</b> {STUDENT_NAME} &nbsp;|&nbsp; <b>MSSV:</b> {STUDENT_ID}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption("ESP32 (Wokwi) → MQTT → ThingsBoard Cloud → collector.py → InfluxDB → preprocessing.py → Streamlit")

with st.sidebar:
    st.header("⚙️ Cấu hình")
    st.write(f"**Sinh viên:** {STUDENT_NAME}")
    st.write(f"**MSSV:** {STUDENT_ID}")
    time_range = st.selectbox("Khoảng thời gian", ["-15m", "-30m", "-1h", "-3h", "-24h"], index=1)
    refresh = st.slider("Tự làm mới (giây)", 2, 30, 5)
    st.write(f"InfluxDB bucket: `{BUCKET}`")


@st.fragment(run_every=refresh)
def realtime():
    raw = query("sensor_raw", time_range,
                ["temperature", "humidity", "distance_cm", "rssi", "sequence",
                 "device_to_tb_ms", "tb_to_collector_ms"])
    if raw.empty:
        st.warning("Chưa có dữ liệu trong InfluxDB. Hãy bật Wokwi và chạy collector.py.")
        return

    last = raw.iloc[-1]
    prev = raw.iloc[-2] if len(raw) > 1 else last
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🌡️ Nhiệt độ", f"{last.temperature:.2f} °C", f"{last.temperature - prev.temperature:+.2f}")
    c2.metric("💧 Độ ẩm", f"{last.humidity:.2f} %", f"{last.humidity - prev.humidity:+.2f}")
    c3.metric("📏 Khoảng cách", f"{last.distance_cm:.1f} cm", f"{last.distance_cm - prev.distance_cm:+.1f}")
    c4.metric("📶 RSSI", f"{int(last.rssi)} dBm")
    c5.metric("🔢 Sequence / Số bản tin", f"{int(last.sequence)} / {len(raw)}")
    st.caption(f"Cập nhật lần cuối: {raw.index[-1]:%H:%M:%S %d/%m/%Y}")

    # Hien thi tung phan theo chieu doc (st.tabs bi reset ve tab dau moi lan fragment tu lam moi)
    tab1, tab2, tab3, tab4 = (st.container(border=True) for _ in range(4))
    tab1.header("📈 Dữ liệu real-time")
    tab2.header("🧹 Dữ liệu sau tiền xử lý")
    tab3.header("⏱️ Độ trễ & lưu trữ")
    tab4.header("📋 Bảng số liệu (50 bản ghi mới nhất)")
    with tab1:
        a, b = st.columns(2)
        a.subheader("Nhiệt độ & Độ ẩm")
        a.line_chart(raw[["humidity", "temperature"]], color=["#1c7ed6", "#e03131"])
        b.subheader("Khoảng cách (cm)")
        b.line_chart(raw[["distance_cm"]], color=["#2f9e44"])

    with tab2:
        proc = query("sensor_processed", time_range,
                     ["temperature", "temperature_rolling_mean", "humidity", "humidity_rolling_mean",
                      "distance_cm", "distance_cm_rolling_mean", "temperature_norm", "humidity_norm",
                      "distance_cm_norm", "temperature_delta"])
        if proc.empty:
            st.info("Chưa có dữ liệu đã xử lý. Chạy preprocessing.py.")
        else:
            st.subheader("Temperature: Raw vs Resampled vs Rolling Mean")
            comp = pd.concat([raw["temperature"].rename("temperature_raw"),
                              proc["temperature"].rename("temperature_resampled_1min"),
                              proc["temperature_rolling_mean"]], axis=1).interpolate(limit_area="inside")
            st.line_chart(comp, color=["#adb5bd", "#e03131", "#f08c00"])
            a, b = st.columns(2)
            a.subheader("Humidity & Distance (rolling mean)")
            a.line_chart(proc[["humidity_rolling_mean", "distance_cm_rolling_mean"]])
            b.subheader("Dữ liệu chuẩn hóa Min-Max [0, 1]")
            b.line_chart(proc[["temperature_norm", "humidity_norm", "distance_cm_norm"]])

    with tab3:
        lat = raw[["device_to_tb_ms", "tb_to_collector_ms"]].where(lambda x: x >= 0)
        metrics = query("pipeline_metrics", time_range,
                        ["db_write_ms", "rejected_count", "duplicate_count", "lost_count"])
        a, b = st.columns(2)
        a.subheader("Độ trễ (ms)")
        a.line_chart(lat)
        b.subheader("Thời gian ghi InfluxDB (ms)")
        if not metrics.empty:
            b.line_chart(metrics[["db_write_ms"]], color=["#7048e8"])
        stats = pd.DataFrame({
            "Min (ms)": [lat.device_to_tb_ms.min(), lat.tb_to_collector_ms.min(),
                         metrics.db_write_ms.min() if not metrics.empty else None],
            "Trung bình (ms)": [lat.device_to_tb_ms.mean(), lat.tb_to_collector_ms.mean(),
                                metrics.db_write_ms.mean() if not metrics.empty else None],
            "Max (ms)": [lat.device_to_tb_ms.max(), lat.tb_to_collector_ms.max(),
                         metrics.db_write_ms.max() if not metrics.empty else None],
        }, index=["ESP32 → ThingsBoard", "ThingsBoard → Collector (polling 5s)", "Ghi InfluxDB"]).round(2)
        st.dataframe(stats, use_container_width=True)
        if not metrics.empty:
            m = metrics.iloc[-1]
            x1, x2, x3 = st.columns(3)
            x1.metric("Bản tin bị từ chối", int(m.rejected_count))
            x2.metric("Bản tin trùng", int(m.duplicate_count))
            x3.metric("Bản tin mất (sequence)", int(m.lost_count))

    with tab4:
        st.dataframe(raw.sort_index(ascending=False).head(50), use_container_width=True)


realtime()
st.markdown(f"<div style='text-align:center;color:gray;margin-top:20px'>© {STUDENT_NAME} — {STUDENT_ID} — IoT và Ứng dụng</div>",
            unsafe_allow_html=True)
