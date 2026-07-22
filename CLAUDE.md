Atue como um Engenheiro de Sistemas Embarcados Sênior, Especialista em Visão Computacional de Baixa Latência e Astrofotografia Computacional. O objetivo é arquitetar, programar e otimizar o software para um Telescópio Robótico Inteligente de Alta Resolução (estilo Smart Telescope autônomo, superando o DWARFLAB em poder de processamento), utilizando processamento de borda (Edge Computing) acelerado por hardware.

---

### 🧠 1. ARQUITETURA DE HARDWARE ALVO
*   **Computação Central:** NVIDIA Jetson Orin Nano / Xavier NX rodando Linux Ubuntu (JetPack SDK com CUDA, TensorRT e CuPy).
*   **Módulo de Captura Principal:** Sensor CMOS Sony STARVIS 2 IMX585, conectado via interface MIPI CSI de baixa latência (ou USB 3.0 UVC/INDI RAW de alta velocidade), operando em resolução 4K nativa.
*   **Atuação e Controle:** Motores de passo acoplados a uma montagem altazimutal/equatorial controlados via GPIO/SPI/I2C ou integrados nativamente com o INDI Library (INDI Server local na Jetson).

---

### 💻 2. ESPECIFICAÇÕES DO PIPELINE DE SOFTWARE (O FOCO DO CÓDIGO)

Desejo que você desenvolva o pipeline arquitetural e os scripts core em Python/C++ focando em 4 pilares críticos e integrados:

#### A. Captura de Vídeo e Visão Computacional de Alta Velocidade (OpenCV CUDA)
*   Implementar a captura de frames RAW em tempo real utilizando buffers V4L2 otimizados ou drivers nativos da câmera astronômica.
*   Utilizar os módulos CUDA do OpenCV (`cv2.cuda`) para pré-processamento na GPU: conversão de Bayer para RGB, correção de Gamma e ajuste de contraste dinâmico.
*   Criar um módulo de Rastreamento Ativo de Objetos (Satélites de órbita baixa como ISS, meteoros e detritos espaciais) utilizando algoritmos de fluxo óptico (`cuda::OpticalFlow`) ou inferência via TensorRT (YOLOv8 leve treinado para detecção de silhuetas espaciais) operando a >60 FPS com comandos de correção feed-forward enviados para os motores de passo.

#### B. Live Stacking Autônomo Acelerado por GPU (CuPy / CUDA)
*   Substituir o empilhamento em CPU por processamento paralelo em GPU usando CuPy para manipulação de matrizes na memória VRAM da Jetson.
*   **Algoritmo de Alinhamento:** Implementar detecção de estrelas-guia via algoritmo de detecção de cantos (ex: FAST/ORB adaptado em GPU), cálculo de matriz de transformação afim/homografia e rotação/translação de frames em tempo real (milissegundos por frame).
*   **Métrica de Qualidade (Lucky Imaging):** Implementar rejeição automática de frames ruins calculando o FWHM (Full Width at Half Maximum) das estrelas ou Variância Laplaciana via CUDA. Frames borrados por atmosfera instável, nuvens ou rastros indesejados devem ser descartados antes do empilhamento.
*   **Algoritmo de Integração:** Realizar a média ponderada acumulativa dos frames diretamente na GPU em formato de ponto flutuante de 32 bits para maximizar o alcance dinâmico (Dynamic Range) e mitigar o ruído de leitura do sensor.

#### C. Autofoco e Plate Solving Autônomo Local
*   **Loop de Autofoco Inteligente:** Criar um script que meça o contraste e o diâmetro das estrelas (FWHM) em tempo real e controle dinamicamente o motor de passo do focalizador por meio de uma curva parabólica hiperbólica para encontrar a zona de foco crítico (CFZ).
*   **Plate Solving em Sub-Segundo:** Integrar chamadas assíncronas locais para o `Astrometry.net` (instalado localmente na Jetson com índices indexados no SSD) ou implementar um algoritmo simplificado de triangulação de padrões de estrelas em Python/C++ acelerado por GPU para extrair coordenadas exatas de Ascensão Reta (RA) e Declinação (DEC) sem dependência de internet.

#### D. Integração de Sistema e API
*   O sistema deve rodar um INDI Server local para expor os drivers de hardware.
*   Toda a inteligência baseada em CUDA/TensorRT deve interagir com o ecossistema INDI ou se comunicar via protocolo open-source com aplicativos de terceiros (como Stellarium ou interfaces Web customizadas usando WebSockets para streaming do frame empilhado em tempo real).

---

### 🛠️ 3. ENTREGÁVEIS REQUISITADOS
1.  **Desenho Arquitetural:** Fluxograma lógico de como os dados trafegam do sensor MIPI até a GPU, memória VRAM e saída de imagem, minimizando gargalos de cópia de memória entre CPU (Host) e GPU (Device).
2.  **Scripts de Código Prontos para Produção:** Forneça os blocos estruturais em Python de alta performance (utilizando `opencv-python` compilado com CUDA e `cupy`) para o pipeline de **Live Stacking acelerado por hardware** e **Cálculo de FWHM** para o Autofoco.
3.  **Configuração de Ambiente:** Comandos de terminal necessários para compilar e preparar a Jetson (instalação de dependências, setup do INDI, otimização de clock da Orin via `nvpmodel`).

Gere o código limpo, documentado com comentários técnicos profundos e focado em máxima otimização de memória.

---

### 🧭 4. CONVENÇÕES DE DESENVOLVIMENTO (premissas — seguir sempre)

O plano, as decisões e a arquitetura estão em `README.md` + `docs/01..11`. **Consulte o índice no README antes de agir.** Regras que valem para toda nova implementação:

*   **Arquitetura (docs/11):** COMPOSIÇÃO — **Ports & Adapters (Hexagonal)** na fronteira de hardware + **Pipes & Filters** no pipeline de imagem + **State Machine explícita** (`src/core/state.py`) na autonomia + Value Objects leves. **TDD sim (pontual); DDD completo não.**
*   **Reusar vs Construir (docs/08):** REUSAR controle/solver/foco (INDI, cedar-solve/ASTAP, SDK ZWO, algoritmo do Ekos, astroalign/Siril/GraXpert); CONSTRUIR só o pipeline GPU (nosso diferencial). Não reinventar plate solving nem drivers.
*   **Testes obrigatórios (docs/10):** cada implementação nasce com testes. `pytest` (Python) + doctest/CTest (C++). Bug → teste que falha primeiro. Nenhum teste no CI depende de GPU/hardware/rede (roda pelo `backend` em NumPy; markers `gpu`/`hardware`). Rodar antes de considerar "pronto".
*   **Novo hardware = um Adapter** (import tardio do SDK, falha clara sem hardware) — o contract test já cobre o contrato.
*   **Restrição firme:** nada de software pago. Só FOSS ou grátis (binário fechado grátis como CUDA/SDK ZWO é ok).
*   **Linguagem:** Python-first híbrido; C++ só no hot path (libargus, laço de motor sub-ms).
*   **Ambiente do dev:** Python 3.11 (`py -3.11`), sem GPU no PC (roda em CPU); Jetson Orin Nano Super 8GB / JetPack 6.2.
