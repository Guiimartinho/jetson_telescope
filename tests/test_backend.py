import numpy as np

from src.backend import to_device, asnumpy, backend_name


def test_roundtrip_host_device_host():
    a = np.arange(6, dtype=np.float32).reshape(2, 3)
    b = asnumpy(to_device(a))
    assert isinstance(b, np.ndarray)
    np.testing.assert_allclose(b, a)


def test_backend_name_nonempty():
    assert isinstance(backend_name(), str) and backend_name()
