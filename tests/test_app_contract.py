"""O app do celular (app/) e a Jetson têm de falar a mesma língua.

O app é Dart e roda os próprios testes (`flutter test`). O que amarra os dois lados fica aqui:
  * as respostas REAIS da API estão gravadas em `app/test/fixtures`, e os testes do app as leem;
    se a API mudar sem regravar, este teste falha;
  * os ícones do app saem do `ui_kit` (uma fonte só) e não podem ficar para trás;
  * nenhum emoji nem ícone de biblioteca pronta entra no app.
"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

pytestmark = pytest.mark.skipif(not (APP / "pubspec.yaml").exists(), reason="sem o projeto do app")


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_app_fixtures_are_what_the_api_really_answers(capsys):
    pytest.importorskip("fastapi")
    pytest.importorskip("cryptography")
    code = _script("export_api_fixtures").main(["--check"])
    assert code == 0, ("a API mudou: rode `py -3.11 scripts/export_api_fixtures.py` e ajuste o app\n"
                       + capsys.readouterr().out)


def test_fixtures_do_not_depend_on_files_outside_git(capsys, monkeypatch):
    """Num clone novo (o do CI) não existe `data/`: as imagens do céu são baixadas e ficam fora
    do git. As respostas gravadas não podem mudar por causa disso — a ficha de um alvo dizia
    "tem miniatura" só na máquina de quem já tinha a imagem."""
    pytest.importorskip("fastapi")
    pytest.importorskip("cryptography")
    import os
    real = os.path.exists
    monkeypatch.setattr(os.path, "exists",
                        lambda p: False if str(p).replace("\\", "/").startswith("data/") else real(p))
    code = _script("export_api_fixtures").main(["--check"])
    assert code == 0, capsys.readouterr().out


def test_app_icons_come_from_the_ui_kit(capsys):
    code = _script("export_app_icons").main(["--check"])
    assert code == 0, ("ícones desatualizados: rode `py -3.11 scripts/export_app_icons.py`\n"
                       + capsys.readouterr().out)


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")


def test_app_has_no_emoji_and_no_stock_icons():
    """Regra do produto: só os nossos ícones, desenhados. Nada de emoji, nada de `Icons.`."""
    culprits = []
    for path in sorted((APP / "lib").rglob("*.dart")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if _EMOJI.search(line) or re.search(r"\b(Cupertino)?Icons\.", line):
                culprits.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:80]}")
    assert not culprits, "\n".join(culprits)


def test_pairing_proof_vector_is_the_one_the_jetson_computes():
    """O vetor que o teste em Dart confere sai da conta da Jetson, não de um número colado."""
    import json
    from src.api.identity import b64u, b64u_decode
    from src.api.pairing import pairing_proof
    v = json.loads((APP / "test" / "fixtures" / "pairing_vector.json").read_text(encoding="utf-8"))
    proof = pairing_proof(b64u_decode(v["secret"]), b64u_decode(v["nonce"]),
                          b64u_decode(v["fingerprint"]), v["client_name"])
    assert b64u(proof) == v["proof"]
