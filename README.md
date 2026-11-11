# ANT+ Field Console

A live terminal dashboard for ANT+ sensors, built with Textual and OpenANT. Reads heart rate, power, and bike speed/cadence.

## Run

```sh
uv run ant-inspector
```

Use `uv run ant-inspector --speed-only` for a full-screen, resize-aware speed readout. On Linux, run `./setup-ant-usb.sh` once if the ANT USB receiver reports access denied, then reconnect it. Speed defaults to a 2.105 m wheel circumference; override with `ANT_WHEEL_CIRCUMFERENCE_M` if needed.
