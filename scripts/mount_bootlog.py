#!/usr/bin/env python3
"""Reinicia a controladora e mostra o log de boot — a rodar NA JETSON (só stdlib, Linux).

Com o firmware de diagnóstico (`idf.py -DONSTEPX_DIAG=ON build`) o log narra a inicialização
inteira, incluindo se cada TMC2209 respondeu na UART. O INDI tem de estar parado, porque o
driver segura a porta:

    sudo systemctl stop telescope-indi
    python3 scripts/mount_bootlog.py [segundos]
    sudo systemctl start telescope-indi
"""
import fcntl
import os
import select
import struct
import sys
import termios
import time

PORT = "/dev/telescope-mount"
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0

fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0                                     # cru: sem tradução nem eco
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL        # 8N1, sem HUPCL
a[4] = a[5] = termios.B115200
termios.tcsetattr(fd, termios.TCSANOW, a)


def line(bit: int, on: bool) -> None:
    fcntl.ioctl(fd, termios.TIOCMBIS if on else termios.TIOCMBIC, struct.pack("I", bit))


# Circuito de auto-reset do ESP32: RTS ativo com DTR solto = EN baixo (reset) e IO0 alto
# (boot normal, não modo download). Soltar o RTS deixa a placa subir.
line(termios.TIOCM_DTR, False)
line(termios.TIOCM_RTS, True)
time.sleep(0.15)
termios.tcflush(fd, termios.TCIFLUSH)
line(termios.TIOCM_RTS, False)

end = time.time() + secs
out = sys.stdout.buffer
while time.time() < end:
    if select.select([fd], [], [], 0.1)[0]:
        try:
            out.write(os.read(fd, 4096))
            out.flush()
        except BlockingIOError:
            pass

# volta ao estado em que o Linux deixa as linhas ao abrir a porta (as duas ativas = sem reset)
line(termios.TIOCM_DTR, True)
line(termios.TIOCM_RTS, True)
os.close(fd)
