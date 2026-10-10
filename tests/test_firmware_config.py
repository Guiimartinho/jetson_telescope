"""Coerência da config do firmware da montagem (OnStepX na FYSETC E4).

Por que estes testes existem: um pino errado no `Config.h` não dá erro de compilação — dá um
telescópio que não se move, ou um endstop que dispara sozinho no meio de um goto. Foi
exatamente o caso encontrado no bring-up: o pinmap do OnStepX põe a UART dos TMC no GPIO15,
que nesta placa é o Z-MIN, enquanto a fiação real dos drivers é GPIO21/22. Aqui isso vira um
teste que roda em qualquer máquina, sem placa e sem toolchain. Ver docs/35.
"""
import importlib.util
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "firmware", "config", "Config.telescope.h")
FETCH = os.path.join(ROOT, "firmware", "scripts", "fetch_onstepx.py")
PINMAP = os.path.join(ROOT, "firmware", "components", "onstepx", "onstepx-src",
                      "src", "pinmaps", "Pins.FYSETC_E4.h")

# --- Verdade de campo: tabela de pinos OFICIAL da FYSETC para a E4 v1.0 ----------------
# (github.com/FYSETC/FYSETC-E4 — seção "Pin Definition"). É contra isto que validamos.
E4_PINS = {
    "X_STEP": 27, "X_DIR": 26, "X_EN": 25,
    "Y_STEP": 33, "Y_DIR": 32, "Y_EN": 25,
    "Z_STEP": 14, "Z_DIR": 12, "Z_EN": 25,
    "E0_STEP": 16, "E0_DIR": 17, "E0_EN": 25,
    "X_MIN": 34, "Y_MIN": 35, "Z_MIN": 15,      # Z_MIN compartilha com Z-DIAG
    "MOTOR_UART_TX": 22, "MOTOR_UART_RX": 21,   # UART dos TMC2209, fiação real da placa
    "FAN0": 13,
}

# Bauds que a conexão serial do INDI oferece (Connection::Serial). O `indi_lx200_OnStep` só
# conecta se o firmware estiver num deles.
INDI_SERIAL_BAUDS = (9600, 19200, 38400, 57600, 115200, 230400)


def _defines(path):
    """Extrai `#define NOME VALOR` de um header C. Ignora comentários de fim de linha."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r'\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+?)\s*(?://.*)?$', line)
            if m:
                out[m.group(1)] = m.group(2).strip()
    return out


@pytest.fixture(scope="module")
def cfg():
    if not os.path.exists(CONFIG):
        pytest.skip("firmware/config/Config.telescope.h ausente")
    return _defines(CONFIG)


def _num(v):
    return float(v.rstrip("fF"))


# ---- placa e canais -------------------------------------------------------
def test_pinmap_is_the_e4(cfg):
    assert cfg["PINMAP"] == "FYSETC_E4"


def test_serial_a_stays_on_so_tmc_rx_is_overridable(cfg):
    """O pinmap só deixa SERIAL_TMC_RX sobrescrevível no ramo SERIAL_A != OFF. Se alguém
    desligar o USB, a UART dos TMC pula para GPIO3/1 e nossa config é ignorada em silêncio."""
    assert cfg["SERIAL_A_BAUD_DEFAULT"] != "OFF"


def test_jetson_link_is_usb_serial_at_an_indi_baud(cfg):
    """O link com a Jetson é o cabo USB: SERIAL_A = UART0 = ponte CH340, falando LX200 com o
    `indi_lx200_OnStep`. Fora da lista de bauds do INDI o driver simplesmente não conecta.

    (A Jetson precisa do módulo `ch341`, que o kernel do JetPack 6 não traz —
    `scripts/jetson_install_ch341.sh`. Ver docs/35.)"""
    assert int(cfg["SERIAL_A_BAUD_DEFAULT"]) in INDI_SERIAL_BAUDS


def test_radio_is_a_secondary_access_point(cfg):
    """O rádio fica ligado como PONTO DE ACESSO próprio da placa: um acesso secundário
    (celular, depuração) que funciona em campo sem roteador. O link da Jetson continua sendo
    o cabo. Modo estação exigiria a senha da rede de casa dentro do firmware."""
    assert cfg["SERIAL_RADIO"] == "WIFI_ACCESS_POINT"


def test_no_network_credentials_are_versioned(cfg):
    """A Config é versionada; senha não mora nela. A senha do AP vem de
    `config/Config.local.h` (fora do git) e a Config recusa compilar sem ela — nunca sai um
    firmware com a senha padrão do OnStepX ("password")."""
    for nome in ("STA_SSID", "STA_PASSWORD", "AP_PASSWORD"):
        assert nome not in cfg, f"{nome} definido no arquivo versionado"
    with open(CONFIG, encoding="utf-8") as f:
        texto = f.read()
    assert '"Config.local.h"' in texto
    assert re.search(r"#ifndef\s+AP_PASSWORD\s*\n\s*#error", texto), (
        "a Config precisa falhar a compilacao quando AP_PASSWORD nao veio do arquivo local")
    with open(os.path.join(ROOT, "firmware", ".gitignore"), encoding="utf-8") as f:
        assert "config/Config.local.h" in f.read()


def test_idf_log_stays_out_of_the_lx200_channel():
    """O console do IDF divide a UART0 com o SERIAL_A. Em INFO o WiFi imprime uma linha a
    cada cliente que entra ou sai do AP; no meio de uma resposta LX200 isso corrompe a
    leitura do INDI. O nível padrão tem de ser WARN (o log do bootloader é à parte)."""
    with open(os.path.join(ROOT, "firmware", "sdkconfig.defaults"), encoding="utf-8") as f:
        linhas = [ln.strip() for ln in f if not ln.lstrip().startswith("#")]
    assert "CONFIG_LOG_DEFAULT_LEVEL_WARN=y" in linhas


def test_debug_switches_live_only_inside_the_diagnostic_block():
    """O debug do OnStepX sai pela MESMA serial do LX200: num firmware de produto ele
    corromperia o link com a Jetson. As chaves de diagnóstico só podem existir dentro do
    bloco `#ifdef ONSTEPX_DIAG` (ligado por `idf.py -DONSTEPX_DIAG=ON build`)."""
    with open(CONFIG, encoding="utf-8") as f:
        texto = f.read()
    bloco = re.search(r"#ifdef\s+ONSTEPX_DIAG\b(.*?)#endif", texto, re.S)
    assert bloco, "bloco de diagnostico ausente"
    fora = texto.replace(bloco.group(0), "")
    for chave in ("DEBUG", "MOTOR_DRIVER_DETECT", "SERIAL_DEBUG_BAUD"):
        assert re.search(rf"#\s*define\s+{chave}\b", bloco.group(1)), f"{chave} fora do bloco?"
        assert not re.search(rf"^\s*#\s*define\s+{chave}\b", fora, re.M), (
            f"{chave} definido FORA do bloco de diagnostico")


# ---- segredos locais (gerados pelo fetch, nunca versionados) ---------------
@pytest.fixture(scope="module")
def fetch():
    if not os.path.exists(FETCH):
        pytest.skip("firmware/scripts/fetch_onstepx.py ausente")
    spec = importlib.util.spec_from_file_location("fetch_onstepx", FETCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_local_config_is_generated_with_a_real_password(fetch, tmp_path):
    """Sem arquivo local, o fetch gera um com senha aleatória (WPA2 exige >= 8 caracteres)."""
    a, b = tmp_path / "a.h", tmp_path / "b.h"
    assert fetch.ensure_local_config(str(a)) is True
    assert fetch.ensure_local_config(str(b)) is True
    senha_a = _defines(str(a))["AP_PASSWORD"].strip('"')
    senha_b = _defines(str(b))["AP_PASSWORD"].strip('"')
    assert 8 <= len(senha_a) <= 63 and senha_a != "password"
    assert senha_a != senha_b, "a senha gerada tem de ser aleatoria"


def test_local_config_is_never_overwritten(fetch, tmp_path):
    """A senha escolhida pelo usuário sobrevive a qualquer novo fetch."""
    p = tmp_path / "Config.local.h"
    p.write_text('#define AP_PASSWORD "minha-senha-123"\n', encoding="utf-8")
    assert fetch.ensure_local_config(str(p)) is False
    assert "minha-senha-123" in p.read_text(encoding="utf-8")


def test_serial_b_is_off_because_the_e4_has_no_second_uart(cfg):
    """Regressão: a E4 só expõe SERIAL_A. `src/pinmaps/Validate.h` recusa a compilação com
    `#error "SERIAL_B isn't defined, SERIAL_B_BAUD_DEFAULT should be OFF."` — foi um erro
    real de build, não hipótese."""
    assert cfg["SERIAL_B_BAUD_DEFAULT"] == "OFF"


def test_config_file_version_is_declared(cfg):
    """Sem FileVersionConfig o OnStepX emite #warning, que o -Werror do IDF 6 torna fatal."""
    assert int(cfg["FileVersionConfig"]) >= 6


# ---- o bug real: UART dos TMC --------------------------------------------
def test_tmc_uart_matches_the_boards_real_wiring(cfg):
    """A UART dos drivers tem de apontar para a fiação REAL da placa, não para o padrão
    do pinmap do OnStepX."""
    assert int(cfg["SERIAL_TMC_RX"]) == E4_PINS["MOTOR_UART_RX"]
    assert int(cfg["SERIAL_TMC_TX"]) == E4_PINS["MOTOR_UART_TX"]


def test_tmc_uart_does_not_collide_with_z_endstop(cfg):
    """Regressão do achado do bring-up: o padrão do OnStepX (GPIO15) é o Z-MIN/Z-DIAG."""
    for pin in (int(cfg["SERIAL_TMC_RX"]), int(cfg["SERIAL_TMC_TX"])):
        assert pin != E4_PINS["Z_MIN"], "UART dos TMC no pino do endstop de Z"


def test_tmc_uart_does_not_collide_with_any_motor_pin(cfg):
    usados = {v for k, v in E4_PINS.items() if k.endswith(("_STEP", "_DIR", "_EN"))}
    for pin in (int(cfg["SERIAL_TMC_RX"]), int(cfg["SERIAL_TMC_TX"])):
        assert pin not in usados, f"GPIO{pin} ja e usado por um driver de motor"


# ---- eixos ----------------------------------------------------------------
def test_axes_use_the_right_slots_and_driver(cfg):
    """RA no slot X, DEC no Y, focalizador no E0 — os três com TMC2209 (soldados na placa)."""
    assert cfg["AXIS1_DRIVER_MODEL"] == "TMC2209"     # RA  -> X
    assert cfg["AXIS2_DRIVER_MODEL"] == "TMC2209"     # DEC -> Y
    assert cfg["AXIS4_DRIVER_MODEL"] == "TMC2209"     # foco -> E0


@pytest.mark.parametrize("axis", ["AXIS1", "AXIS2"])
def test_steps_per_degree_matches_documented_formula(cfg, axis):
    """passos/grau = (200 passos do motor * microsteps * reducao) / 360.

    A redução é provisória (a mecânica ainda não existe), mas o NÚMERO e a FÓRMULA não
    podem se separar: quando a redução real for medida, este teste pega a conta errada."""
    micro = _num(cfg[f"{axis}_DRIVER_MICROSTEPS"])
    spd = _num(cfg[f"{axis}_STEPS_PER_DEGREE"])
    reducao = spd * 360.0 / (200.0 * micro)
    assert abs(reducao - round(reducao)) < 1e-6, (
        f"{axis}: passos/grau {spd} implica reducao {reducao:.4f}, que nao e inteira — "
        "confira a conta ou documente a reducao fracionaria")
    assert 1 < reducao < 1000


@pytest.mark.parametrize("axis,nominal_ma", [("AXIS1", 1700), ("AXIS2", 1700), ("AXIS4", 1000)])
def test_driver_current_below_motor_nominal(cfg, axis, nominal_ma):
    """Com UART a corrente é por software. Rodar abaixo do nominal mantém motor e driver
    frios — a montagem quase não pede torque (docs/32)."""
    irun = _num(cfg[f"{axis}_DRIVER_IRUN"])
    assert 200 <= irun <= nominal_ma, f"{axis}_DRIVER_IRUN={irun} mA fora da faixa segura"


def test_mount_type_is_equatorial(cfg):
    """O OpenAstroExplorer é equatorial com contrapeso → GEM (precisa de meridian flip)."""
    assert cfg["MOUNT_TYPE"] == "GEM"


# ---- o patch no pinmap (só quando a árvore foi baixada) -------------------
@pytest.mark.skipif(not os.path.exists(PINMAP),
                    reason="arvore do OnStepX ausente (rode firmware/scripts/fetch_onstepx.py)")
def test_pinmap_patch_makes_tmc_tx_overridable():
    """Sem a guarda `#ifndef`, o pinmap redefine SERIAL_TMC_TX para 15 DEPOIS da nossa
    config — nossa escolha seria descartada silenciosamente."""
    with open(PINMAP, encoding="utf-8") as f:
        texto = f.read()
    assert "#ifndef SERIAL_TMC_TX" in texto, (
        "patch ausente: rode py -3.11 firmware/scripts/fetch_onstepx.py")


@pytest.mark.skipif(not os.path.exists(PINMAP), reason="arvore do OnStepX ausente")
def test_pinmap_axis_pins_match_the_official_table():
    """O pinmap do OnStepX tem de bater com a tabela oficial da FYSETC nos eixos que usamos."""
    pm = _defines(PINMAP)
    assert int(pm["AXIS1_STEP_PIN"]) == E4_PINS["X_STEP"]
    assert int(pm["AXIS1_DIR_PIN"]) == E4_PINS["X_DIR"]
    assert int(pm["AXIS2_STEP_PIN"]) == E4_PINS["Y_STEP"]
    assert int(pm["AXIS2_DIR_PIN"]) == E4_PINS["Y_DIR"]
    assert int(pm["AXIS4_STEP_PIN"]) == E4_PINS["E0_STEP"]
    assert int(pm["AXIS4_DIR_PIN"]) == E4_PINS["E0_DIR"]
    assert int(pm["SHARED_ENABLE_PIN"]) == E4_PINS["X_EN"]
