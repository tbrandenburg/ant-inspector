# ANT+ Field Console

A live terminal dashboard for ANT+ sensors, built with Textual and OpenANT. Reads heart rate, power, and bike speed/cadence.

## Run

```sh
uv run ant-inspector
```

On Linux, run `./setup-ant-usb.sh` once if the ANT USB receiver reports access denied, then reconnect it. Set `ANT_WHEEL_CIRCUMFERENCE_M` to show speed in km/h.
