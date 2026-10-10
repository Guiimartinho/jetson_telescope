"""API v1 do telescópio — o que o app do celular consome.

Adapter de ENTRADA (Ports & Adapters): traduz HTTPS/WebSocket para o núcleo que já existe
(Controller, FrameHub, catálogo, render, MountLink). Nasce protegida: TLS 1.3 com o certificado
do aparelho, pareamento por QR e token em toda chamada. Ver app/docs/04-api.md e 07-seguranca.md.
"""
__version__ = "0.1.0"
