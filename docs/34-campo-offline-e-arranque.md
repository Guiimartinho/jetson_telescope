# 34 — Prontidão de campo: arranque do Atlas e operação 100% offline

Três defeitos encontrados **medindo a Jetson em operação real** (não no PC): o console de campo
levava mais de um minuto para abrir a primeira aba, dependia de internet para calcular
visibilidade, e a porta serial não abriria para o usuário quando a controladora da montagem
fosse plugada. Os três atacam a mesma promessa de `docs/33`: *"no campo, pelo celular, sem internet"*.

---

## 1. O sintoma: 78,8 s para abrir o Atlas

O Atlas é a **primeira** aba que o usuário toca (escolher alvo). Medido no Orin, com os serviços
no ar há 47 dias:

```
GET /api/targets   ->  78,8 s   (1ª chamada)
GET /api/targets   ->   0,27 s  (2ª chamada)
```

No celular, 79 s de tela parada lê como "o aparelho travou". Decompondo no próprio Orin:

| Custo | Tempo | Causa |
|---|--:|---|
| Download IERS do astropy | **~70 s** | tentativa de baixar a tabela de orientação da Terra |
| `catalog.load()` | 6,6 s | OpenNGC/pyongc, 12.014 objetos, cache só no módulo |
| 1ª transformação de coordenada | 1,7 s | astropy monta os frames `EarthLocation`/`AltAz` |

O log do serviço acusava a causa dominante no instante exato da chamada:

```
IERSStaleWarning: IERS_Auto predictive values are older than 30.0 days
but downloading the latest table did not find newer values
```

## 2. Por que isso é pior no campo do que na bancada

Na bancada há rede: a tentativa falha em ~70 s e segue. **No campo não há internet** — a mesma
tentativa vira timeout de DNS/TCP, a cada boot do serviço. É uma dependência de rede escondida
dentro de um produto que se vende como offline.

## 3. A correção

### 3.1 Travar o astropy em modo offline — `catalog.configure_astropy_offline()`

Idempotente, chamada por `altitude_deg()` (todo caminho que calcula altitude) e pelo warm-up.
Precisa de **duas** travas:

```python
iers.conf.auto_download = False    # não sai para a rede; usa a tabela embutida
iers.conf.auto_max_age  = None     # aceita a tabela embutida mesmo "velha"
```

> **A armadilha (pega pelo teste, não pela leitura).** Desligar só o `auto_download` **quebra** o
> cálculo: o astropy passa a levantar
> `ValueError: interpolating from IERS_Auto using predictive values that are more than 30.0 days old`
> — exatamente o caso do Orin. Sem `auto_max_age=None` a "correção" teria trocado *lento* por
> *quebrado*, que é bem pior. O teste `test_altitude_still_works_offline` falhou primeiro e
> obrigou a segunda trava.

**Custo da troca:** o astropy passa a usar o movimento polar médio de 50 anos, avisando que isso
"pode afetar a precisão no nível de arcsec". Filtramos visibilidade em **graus** (`min_alt=25°`) —
irrelevante. Para o plate solving a referência é a imagem, não a IERS.

### 3.2 Pré-aquecer o catálogo — `console.warm_cache()`

`ConsoleServer.start()` dispara o aquecimento numa thread daemon, em paralelo com o servidor: trava
o astropy offline, carrega o OpenNGC e faz uma transformação de coordenada. O custo passa a ser pago
no arranque do serviço (que sobe no boot), não no primeiro toque do usuário. Nunca levanta — sem
pyongc/astropy devolve `False` e o console segue no fallback estático.

### 3.3 Grupo `dialout` (pré-requisito do Milestone F)

O usuário não estava em `dialout`, então `/dev/ttyUSB0` só abriria com `sudo` — e o
`indi_lx200_OnStep` roda como usuário. Corrigido com `usermod -aG dialout`, antes de a
controladora chegar à bancada.

**Atualização (2026-10-09): o `dialout` era necessário, mas não bastava.** O kernel do
JetPack 6 vem com `CONFIG_USB_SERIAL_CH341` desligado, então a ponte CH340 da controladora
nem chegava a criar o `/dev/ttyUSB0`. `scripts/jetson_install_ch341.sh` compila o módulo
`ch341` (o do kernel mainline, na versão exata do kernel em execução) e mascara a regra udev
do `brltty`, que no Ubuntu 22.04 derruba o CH340 segundos depois de ele aparecer. Tem de ser
rodado de novo se o kernel for atualizado. Ver `docs/35` §8.1.

## 4. Validação (Orin Nano Super, 2026-09-08)

| | antes | depois |
|---|--:|--:|
| `/api/targets`, 2 s após o restart do serviço (pior caso) | 78,8 s | **3,07 s** |
| `/api/targets` aquecido | 0,27 s | **0,28 s** |
| Depende de internet para calcular altitude | sim | **não** |
| `/dev/ttyUSB*` acessível sem sudo | não | **sim** |

Dados do Atlas conferidos após a mudança (altitudes reais, São Paulo, ~22 h): M8 a 40° visível;
M31 a 13°, M42 a −23°, NGC2244 a −40° corretamente fora. Testes: **+5** (3 em `test_catalog.py`,
2 em `test_console.py`) → **210 verdes** no PC (GPU) e **16/16** nos módulos tocados no Orin
(aarch64, Python 3.10, astropy 6.1.7).

## 5. Regra que fica

> **Nenhum caminho do produto pode depender de rede em tempo de execução.** Bibliotecas científicas
> (astropy é o caso clássico) baixam dados auxiliares por padrão; em um aparelho de campo isso é um
> defeito latente. Ao adotar uma lib nova, verificar o que ela busca na primeira chamada.

E o corolário de método: **medir no alvo**. Estes três defeitos são invisíveis no PC de dev — a
tabela IERS local está fresca, o disco é rápido e a porta serial nunca foi usada. Só apareceram
cronometrando a Jetson de verdade.

Ver `docs/33` (console de campo), `docs/26` (catálogo) e `docs/31` (bring-up de hardware).
