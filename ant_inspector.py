"""Live ANT+ sensor dashboard."""

from __future__ import annotations

import queue
import os
import threading
import time
import argparse
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.widgets import Footer, Header, Label, ProgressBar, Static

DEFAULT_WHEEL_CIRCUMFERENCE_M = 2.105
_DIGITS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "001", "001"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    ".": ("000", "000", "000", "000", "010"),
    "-": ("000", "000", "111", "000", "000"),
}


def render_speed_art(value: str, width: int, height: int) -> str:
    """Scale a block-digit speed readout to the available terminal cells."""
    value = value if value and all(char in _DIGITS for char in value) else "----"
    columns = len(value) * 3 + len(value) - 1
    if width < columns or height < 5:
        return value
    scale_x = max(1, width // columns)
    scale_y = max(1, height // 5)
    lines = []
    for row in range(5):
        cells = []
        for index, char in enumerate(value):
            cells.extend("█" * scale_x if bit == "1" else " " * scale_x for bit in _DIGITS[char][row])
            if index < len(value) - 1:
                cells.append(" " * scale_x)
        line = "".join(cells).rstrip()
        lines.extend([line] * scale_y)
    return "\n".join(lines)


class Metric(Static):
    DEFAULT_CSS = """
    Metric { height: 7; border: round #29465b; padding: 0 1; background: #101a24; }
    Metric .caption { color: #8ca6b8; text-style: bold; }
    Metric .value { color: #f1f7fb; text-style: bold; height: 2; }
    Metric .unit { color: #57d6c5; }
    """

    def __init__(self, caption: str, unit: str, *, id: str) -> None:
        super().__init__(id=id)
        self.caption, self.unit = caption, unit

    def compose(self) -> ComposeResult:
        yield Label(self.caption, classes="caption")
        yield Label("—", id=f"{self.id}-value", classes="value")
        yield Label(self.unit, classes="unit")

    def update_value(self, value: str) -> None:
        self.query_one(f"#{self.id}-value", Label).update(value)


class AntDashboard(App):
    TITLE = "ANT+  /  FIELD CONSOLE"
    SUB_TITLE = "LIVE SENSOR TELEMETRY"
    CSS = """
    Screen { background: #0b1118; }
    Header { background: #101a24; color: #57d6c5; }
    #content { padding: 1 2; height: 1fr; }
    #banner { height: 3; color: #8ca6b8; padding: 0 1; }
    #metrics { height: 9; }
    Metric { width: 1fr; margin: 0 1; }
    #bottom { height: 1fr; margin-top: 1; }
    #signal, #feed { border: round #29465b; padding: 1 2; background: #101a24; }
    #signal { width: 2fr; margin-right: 1; }
    #feed { width: 1fr; }
    .heading { color: #57d6c5; text-style: bold; padding-bottom: 1; }
    #signal-status, #feed-lines { color: #b3c6d2; }
    #bar { margin-top: 1; }
    #speed-screen { height: 1fr; width: 100%; background: #0b1118; padding: 0 1; }
    #speed-art { height: 1fr; width: 100%; content-align: center middle; color: #57d6c5; overflow: hidden; }
    #speed-status { height: 2; text-align: center; color: #8ca6b8; }
    Footer { background: #101a24; }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, *, speed_only: bool = False) -> None:
        super().__init__()
        self.speed_only = speed_only
        self.events: queue.SimpleQueue[tuple[str, object]] = queue.SimpleQueue()
        self.node = None
        self.packet_count = 0
        self.last_packet = 0.0
        self.log_lines: list[str] = []
        self.speed_value = "----"

    def compose(self) -> ComposeResult:
        if self.speed_only:
            with Vertical(id="speed-screen"):
                yield Static("", id="speed-art")
                yield Label("SCANNING FOR SPEED SENSOR  •  KM/H", id="speed-status")
            yield Footer()
            return

        yield Header()
        with Vertical(id="content"):
            yield Label("◈  ANT+ SENSOR ARRAY     /     SCANNING…", id="banner")
            with Horizontal(id="metrics"):
                yield Metric("HEART RATE", "BPM", id="heart")
                yield Metric("POWER", "WATTS", id="power")
                yield Metric("CADENCE", "RPM", id="cadence")
                yield Metric("SPEED", "KM/H", id="speed")
            with Horizontal(id="bottom"):
                with Vertical(id="signal"):
                    yield Label("◉  RECEIVER STATUS", classes="heading")
                    yield Label("Starting ANT receiver…", id="signal-status")
                    yield ProgressBar(total=100, show_eta=False, id="bar")
                with Vertical(id="feed"):
                    yield Label("▤  EVENT LOG", classes="heading")
                    yield Label("Waiting for sensor packets…", id="feed-lines")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(0.2, self.drain_sensor_events)
        if self.speed_only:
            self.refresh_speed_art()
        threading.Thread(target=self.start_receiver, daemon=True, name="ant-receiver").start()

    def on_resize(self, event: Resize) -> None:
        if self.speed_only and self.is_mounted:
            figure = self.query_one("#speed-art", Static)
            figure.update(render_speed_art(self.speed_value, figure.size.width, figure.size.height))

    def refresh_speed_art(self) -> None:
        figure = self.query_one("#speed-art", Static)
        width = figure.size.width or self.size.width
        height = figure.size.height or max(5, self.size.height - 4)
        figure.update(render_speed_art(self.speed_value, width, height))

    def start_receiver(self) -> None:
        """OpenANT runs its blocking event loop on a worker thread."""
        try:
            from openant.devices import ANTPLUS_NETWORK_KEY
            from openant.devices.bike_speed_cadence import (
                BikeCadence,
                BikeSpeed,
                BikeSpeedCadence,
            )
            from openant.devices.heart_rate import HeartRate, HeartRateData
            from openant.devices.power_meter import PowerData, PowerMeter
            from openant.devices.scanner import Scanner
            from openant.easy.node import Node

            node = Node()
            self.node = node
            node.set_network_key(0, ANTPLUS_NETWORK_KEY)
            circumference_m = float(
                os.getenv("ANT_WHEEL_CIRCUMFERENCE_M", str(DEFAULT_WHEEL_CIRCUMFERENCE_M))
            )
            scanner = Scanner(node)
            scanner.on_found = lambda identity: self.events.put(("discovered", identity))
            devices = []
            if not self.speed_only:
                devices.extend([HeartRate(node), PowerMeter(node)])
            speed_cadence = BikeSpeedCadence(node, wheel_circumference_m=circumference_m)
            speed_sensor = BikeSpeed(node)
            devices.extend([speed_cadence, speed_sensor])
            cadence_sensor = None if self.speed_only else BikeCadence(node)
            if cadence_sensor is not None:
                devices.append(cadence_sensor)
            for device in devices:
                device.on_found = lambda device=device: self.events.put(
                    ("found", f"{device.name} #{device.device_id} type {device.device_type}")
                )

            if not self.speed_only:
                def heart_rate_data(_page: int, _name: str, data: HeartRateData) -> None:
                    self.events.put(("metric", ("heart", f"{data.heart_rate}")))

                def power_data(_page: int, _name: str, data: PowerData) -> None:
                    self.events.put(("metric", ("power", str(data.instantaneous_power))))
                    if data.cadence != 255:
                        self.events.put(("metric", ("cadence", str(data.cadence))))

                devices[0].on_device_data = heart_rate_data
                devices[1].on_device_data = power_data

            def speed_cadence_data(_page: int, name: str, data: object) -> None:
                if name == "bike_speed" and data.calculated_speed is not None:
                    self.events.put(("metric", ("speed", f"{data.calculated_speed:.1f}")))
                elif name == "bike_cadence" and data.calculated_cadence is not None:
                    self.events.put(("metric", ("cadence", str(round(data.calculated_cadence)))))

            speed_cadence.on_device_data = speed_cadence_data

            def separate_speed_data(_page: int, _name: str, data: object) -> None:
                if circumference_m and data.calculate_speed(circumference_m) is not None:
                    self.events.put(("metric", ("speed", f"{data.calculated_speed:.1f}")))

            def separate_cadence_data(_page: int, _name: str, data: object) -> None:
                if data.calculate_cadence() is not None:
                    self.events.put(("metric", ("cadence", str(round(data.calculated_cadence)))))

            speed_sensor.on_device_data = separate_speed_data
            if cadence_sensor is not None:
                cadence_sensor.on_device_data = separate_cadence_data
            self.events.put(
                (
                    "status",
                    f"Receiver ready • scanning all ANT+ devices • wheel {circumference_m:.3f} m",
                )
            )
            node.start()
        except Exception as exc:
            self.events.put(("error", f"ANT receiver error: {exc}"))

    def drain_sensor_events(self) -> None:
        while not self.events.empty():
            kind, value = self.events.get()
            if kind == "status":
                if self.speed_only:
                    self.query_one("#speed-status", Label).update(str(value))
                else:
                    self.query_one("#signal-status", Label).update(str(value))
            elif kind == "error":
                if self.speed_only:
                    self.query_one("#speed-status", Label).update(str(value))
                else:
                    self.query_one("#signal-status", Label).update(str(value))
                    self.query_one("#banner", Label).update("◈  ANT+ SENSOR ARRAY     /     RECEIVER ERROR")
            elif kind == "found":
                self.packet_count += 1
                if self.speed_only:
                    self.query_one("#speed-status", Label).update(f"SPEED SENSOR ONLINE  •  {value}")
                else:
                    self.log_lines.append(f"{datetime.now():%H:%M:%S}  FOUND {value}")
            elif kind == "discovered":
                device_id, device_type, transmission_type = value
                if self.speed_only and device_type not in (121, 123):
                    continue
                self.log_lines.append(
                    f"{datetime.now():%H:%M:%S}  ANT+ #{device_id} type {device_type} / {transmission_type}"
                )
                if self.speed_only:
                    self.query_one("#speed-status", Label).update(
                        f"SENSOR {device_id}  •  TYPE {device_type}  •  KM/H"
                    )
                else:
                    self.query_one("#signal-status", Label).update(
                        f"ANT+ sensor found • ID {device_id}, type {device_type}"
                    )
            elif kind == "metric":
                metric_id, metric_value = value
                if self.speed_only:
                    if metric_id == "speed":
                        self.speed_value = metric_value
                        self.refresh_speed_art()
                    else:
                        continue
                else:
                    self.query_one(f"#{metric_id}", Metric).update_value(metric_value)
                self.packet_count += 1
                self.last_packet = time.monotonic()
                self.log_lines.append(f"{datetime.now():%H:%M:%S}  {metric_id.upper():4} {metric_value}")

        if self.speed_only:
            return
        self.log_lines = self.log_lines[-8:]
        if self.log_lines:
            self.query_one("#feed-lines", Label).update("\n".join(self.log_lines) + f"\n\n{self.packet_count:04d} updates")
        if self.last_packet:
            age = time.monotonic() - self.last_packet
            self.query_one("#bar", ProgressBar).update(progress=max(0, 100 - int(age * 25)))
            if age > 5:
                self.query_one("#signal-status", Label).update("Searching • no recent sensor packets")
        self.query_one("#banner", Label).update(f"◈  ANT+ SENSOR ARRAY     /     {self.packet_count:04d} SENSOR UPDATES")

    def on_unmount(self) -> None:
        if self.node is not None:
            self.node.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="ANT+ sensor dashboard")
    parser.add_argument("--speed-only", action="store_true", help="show a full-screen speedometer")
    options = parser.parse_args()
    AntDashboard(speed_only=options.speed_only).run()


if __name__ == "__main__":
    main()
