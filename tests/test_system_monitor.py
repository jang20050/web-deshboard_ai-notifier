import json
from unittest import mock

import system_monitor as sm


def test_level_rules():
    assert sm.level(50, 75, 90) == "good"
    assert sm.level(80, 75, 90) == "warning"
    assert sm.level(95, 75, 90) == "critical"
    assert sm.level(None, 75, 90) == "unknown"
    assert sm.level(10, 30, 15, reverse=True) == "critical"


def test_lhm_picks_cpu_not_gpu():
    data = {"Text": "Sensor", "Children": [{"Text": "PC", "Children": [
        {"Text": "AMD Ryzen 7", "ImageURL": "images_icon/cpu.png", "Children": [
            {"Text": "Temperatures", "Children": [{"Text": "Core (Tctl/Tdie)", "Value": "61,5 °C"}]}]},
        {"Text": "GeForce", "ImageURL": "images_icon/nvidia.png", "Children": [
            {"Text": "Temperatures", "Children": [{"Text": "GPU Core", "Value": "80.0 °C"}]}]}]}]}

    class Resp:
        def read(self):
            return json.dumps(data).encode()

    with mock.patch("urllib.request.OpenerDirector.open", return_value=Resp()):
        v, src = sm._lhm_web()
    assert v == 61.5 and "Tctl" in src
