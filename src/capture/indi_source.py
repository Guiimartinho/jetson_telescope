"""Fonte de câmera via INDI — usa o IndiClient puro-Python (roda no PC de dev E na Jetson).

Antes dependia de `pyindi-client` (só Jetson); agora fala o protocolo INDI direto, então dá pra
validar contra o `indi_simulator_ccd` (ou o servidor falso na CI) sem nenhum hardware. No bring-up,
troque `device` para o nome real do driver (ex.: "ZWO CCD ASI585MC") — o resto é igual.
Implementa o mesmo port `FrameSource.read(out) -> (frame_float32, meta)`. Ver docs/20 e docs/08.
"""
from __future__ import annotations
import io
import numpy as np

from .source import FrameSource
from ..io.indi_client import IndiClient


class IndiCameraSource(FrameSource):
    """Câmera CCD/CMOS via INDI. Dispara CCD_EXPOSURE e decodifica o BLOB FITS em ndarray."""

    def __init__(self, device="CCD Simulator", host="localhost", port=7624,
                 exposure_s=2.0, gain=None, is_color=False, bayer="RGGB",
                 client: IndiClient | None = None, connect_timeout=10.0):
        self.device_name = device
        self.exposure_s = float(exposure_s)
        self.gain = gain
        self.is_color = is_color
        self.bayer = bayer
        self._own_client = client is None
        self.client = client or IndiClient(host, port).connect()
        self._setup(connect_timeout)

    def _setup(self, timeout):
        cli = self.client
        cli.get_properties(self.device_name)
        cli.connect_device(self.device_name, timeout=timeout)
        cli.wait_vector(self.device_name, "CCD_EXPOSURE", timeout=timeout)
        cli.enable_blob(self.device_name, "CCD1")           # sem isso o CCD não manda imagem
        if self.gain is not None and cli.get(self.device_name, "CCD_GAIN"):
            cli.send_number(self.device_name, "CCD_GAIN", {"GAIN": float(self.gain)})

    def read(self, out=None):
        cli = self.client
        cli.clear_blob()
        cli.send_number(self.device_name, "CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": self.exposure_s})
        blob = cli.wait_blob(timeout=self.exposure_s + 30)
        frame = self._decode(blob["data"])
        if out is not None and out.shape == frame.shape:
            out[...] = frame
            frame = out
        return frame, dict(kind="camera", exposure_s=self.exposure_s, format=blob["format"])

    @staticmethod
    def _decode(data: bytes) -> np.ndarray:
        from astropy.io import fits                          # reuso: leitura FITS
        with fits.open(io.BytesIO(data)) as hdul:
            arr = np.asarray(hdul[0].data, dtype=np.float32)
        return arr

    def close(self):
        if self._own_client:
            self.client.close()
