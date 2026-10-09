"""Segurança do manifesto de poda do OnStepX (firmware/scripts/prune_onstepx.py).

A poda apaga arquivos de verdade. Uma regra mal escrita — um diretório a mais na lista, um
prefixo de glob largo demais — removeria justamente o HAL do ESP32 ou o pinmap da nossa
placa, e o sintoma seria um erro de compilação obscuro (ou pior: um build que passa e um
telescópio que não anda). Estes testes validam o MANIFESTO, sem precisar da árvore baixada
nem de toolchain. Ver docs/35.
"""
import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "firmware", "scripts", "prune_onstepx.py")


@pytest.fixture(scope="module")
def prune():
    if not os.path.exists(SCRIPT):
        pytest.skip("firmware/scripts/prune_onstepx.py ausente")
    spec = importlib.util.spec_from_file_location("prune_onstepx", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _todos_os_alvos(prune):
    """Todo caminho que qualquer camada declara remover."""
    alvos = []
    for camada in prune.CAMADAS.values():
        alvos.extend(camada.get("dirs", []))
    return alvos


# ---- o que NUNCA pode ser removido ---------------------------------------
def test_esp32_hal_is_never_a_target(prune):
    """Sem o HAL do ESP32 não há firmware — HAL.h cai nele por #if defined(ESP32)."""
    for alvo in _todos_os_alvos(prune):
        assert "HAL/esp" not in alvo, f"camada removeria o HAL do ESP32: {alvo}"
        assert "HAL/default" not in alvo, f"camada removeria o HAL default: {alvo}"


def test_our_pinmap_is_protected(prune):
    """O glob de pinmaps apaga Pins.*.h — o da nossa placa tem de estar protegido."""
    assert prune._protegido("src/pinmaps/Pins.FYSETC_E4.h")
    assert prune._protegido("src/pinmaps/Pins.defaults.h")
    assert prune._protegido("src/pinmaps/Models.h")


def test_glob_would_remove_other_boards_but_not_ours(prune):
    """A regra de glob precisa realmente pegar as outras placas (senão a poda é inócua)."""
    assert not prune._protegido("src/pinmaps/Pins.MaxESP4.h")
    assert not prune._protegido("src/pinmaps/Pins.MiniPCB.h")


def test_entry_points_and_config_protected(prune):
    for essencial in ("OnStepX.ino", "OnStepX.ino.cpp", "Config.h"):
        assert prune._protegido(essencial), f"{essencial} tem de ser intocavel"


def test_core_libraries_are_never_targets(prune):
    """O núcleo (eixos, tarefas, serial, wifi, comandos) não pode entrar em camada nenhuma."""
    nucleo = ["lib/axis", "lib/tasks", "lib/serial", "lib/wifi", "lib/commands", "telescope"]
    for alvo in _todos_os_alvos(prune):
        for n in nucleo:
            assert n not in alvo, f"camada removeria o nucleo: {alvo}"


# ---- o manifesto em si ----------------------------------------------------
def test_tiers_are_ordered_and_documented(prune):
    """Camadas numeradas a partir de 1, sem buracos, cada uma justificando o porquê."""
    assert sorted(prune.CAMADAS) == list(range(1, len(prune.CAMADAS) + 1))
    for n, c in prune.CAMADAS.items():
        assert c.get("nome"), f"camada {n} sem nome"
        assert len(c.get("porque", "")) > 40, f"camada {n} sem justificativa util"


def test_tier1_only_touches_platform_and_board_files(prune):
    """A camada 1 é a única 'segura por construção': só pode mexer em HAL/ e pinmaps/."""
    for alvo in prune.CAMADAS[1].get("dirs", []):
        assert alvo.startswith("src/HAL/"), f"camada 1 saiu do escopo de plataforma: {alvo}"
    assert prune.CAMADAS[1]["glob_dir"] == "src/pinmaps"


def test_no_duplicate_targets_across_tiers(prune):
    alvos = _todos_os_alvos(prune)
    assert len(alvos) == len(set(alvos)), "caminho repetido em mais de uma camada"


def test_no_target_escapes_the_tree(prune):
    """Nenhum alvo pode subir de diretório — a poda só age dentro da árvore baixada."""
    for alvo in _todos_os_alvos(prune):
        assert not alvo.startswith(("/", "\\")) and ".." not in alvo, f"caminho perigoso: {alvo}"
