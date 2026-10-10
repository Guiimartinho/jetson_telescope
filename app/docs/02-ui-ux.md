# 02 — UI e UX

## 1. Para quem e em que situação

O app é usado **de noite, ao ar livre, com uma mão, às vezes de luva**, por alguém que quer
olhar para o céu e não para o celular. Quem usa pode ser iniciante. Disso saem as regras:

| Regra | Consequência na tela |
|---|---|
| **Não estragar a visão noturna** | tema escuro sempre; modo vermelho; nenhuma tela branca, nem por um instante; brilho reduzido |
| **Uma mão, alvo grande** | ações principais na metade de baixo; botões de pelo menos 48 dp, os principais com 64 dp |
| **A imagem é a estrela** | em Observar a foto ocupa a tela; os controles ficam recolhidos por cima dela |
| **Parar é sempre possível** | o botão PARAR aparece em qualquer tela enquanto algo se move ou captura |
| **Dizer a verdade** | conexão, origem do dado (real ou simulado) e erros aparecem como são, com o que fazer em seguida |
| **Simples primeiro** | iniciante vê três botões; o modo Pro abre curvas, histograma e números |
| **A Jetson trabalha sozinha** | fechar o app ou perder o sinal não para a sessão; ao voltar, o app mostra o que aconteceu |

## 2. Navegação

Cinco destinos na barra de baixo, na ordem em que a noite acontece:

```
  Atlas      Planejar     OBSERVAR     Galeria     Aparelho
  escolher   a noite      agora        o que fiz   montagem, rede, sistema
```

- **Observar** fica no centro, maior, e é onde o app abre. Com nada rodando, ele é o painel de
  início: estado do telescópio, alvo sugerido, continuar a última sessão.
- Uma **faixa de estado** fica no topo de todas as telas: nome do telescópio e conexão,
  atividade atual, modo vermelho.
- Enquanto houver um trabalho rodando, um **PARAR** compacto flutua acima da barra em qualquer
  destino.

## 3. Telas

Esboços em proporção de celular em pé. `[ ]` é botão, `( )` é seletor, `<<<` é imagem.

### 3.1 Conectar

```
+------------------------------------+
|  (logo)  TELESCOPIO                |
|                                    |
|  Procurando na rede...             |
|                                    |
|  +------------------------------+  |
|  | Telescopio do Guilherme      |  |
|  | na rede de casa   sinal bom  |  |
|  +------------------------------+  |
|  +------------------------------+  |
|  | Demonstracao (sem aparelho)  |  |
|  +------------------------------+  |
|                                    |
|  [ Ler QR code do aparelho ]       |
|  [ Digitar endereco ]              |
|                                    |
|  Nao achou? Veja se o celular esta |
|  no mesmo WiFi do telescopio.      |
+------------------------------------+
```

Nas próximas vezes essa tela nem aparece: o app conecta no último aparelho e vai direto para
Observar. Ela volta se a conexão falhar por mais de alguns segundos.

### 3.2 Observar, parado (início)

```
+------------------------------------+
| Telescopio  conectado     [vermelho]|
+------------------------------------+
|                                    |
|   Pronto para observar             |
|   Montagem em casa  Camera simulada|
|   GPU ok   31 C   200 GB livres    |
|                                    |
|  +------------------------------+  |
|  | <<< M8 Lagoa >>>             |  |
|  | Alto agora (52 graus)        |  |
|  | [ Observar este alvo ]       |  |
|  +------------------------------+  |
|                                    |
|  Continuar: M20 Trifida, ontem     |
|  21 min integrados      [ Abrir ]  |
|                                    |
+------------------------------------+
| Atlas  Planejar [OBSERVAR] Gal Apar|
+------------------------------------+
```

### 3.3 Observar, indo para o alvo

O goto é uma sequência com etapas que podem falhar; o app mostra qual está em curso.

```
+------------------------------------+
| Telescopio  conectado     [vermelho]|
+------------------------------------+
| <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< |
| <<<<      previa ao vivo      <<<< |
| <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< |
| <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< |
+------------------------------------+
|  M8 Lagoa                          |
|  1 Apontar            feito        |
|  2 Reconhecer o ceu   agora...     |
|  3 Centralizar        falta        |
|  4 Focar              falta        |
|                                    |
|           [   PARAR   ]            |
+------------------------------------+
```

Se o reconhecimento do céu falhar, a etapa 2 vira o erro, com saída: `[ Tentar de novo ]`
`[ Focar primeiro ]` `[ Escolher outro alvo ]`.

### 3.4 Observar, empilhando

```
+------------------------------------+
| M8 Lagoa      empilhando  [vermelho]|
+------------------------------------+
| <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< |
| <<<<                          <<<< |
| <<<<   imagem empilhada       <<<< |
| <<<<   pinca = zoom           <<<< |
| <<<<                          <<<< |
| <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< |
+------------------------------------+
|  42 fotos   21 min   nitidez boa   |
|  ----------------------------      |  <- puxar para cima: modo Pro
|  [ Brilho ]  [ PARAR ]  [ Salvar ] |
+------------------------------------+
```

Puxando a folha para cima aparecem, em ordem: exposição e ganho; histograma com os pontos de
preto e branco; SNR e FWHM ao longo do tempo; quadros rejeitados e por quê. Deitando o celular,
a imagem ocupa a tela inteira e os controles vão para uma coluna à direita.

### 3.5 Atlas

```
+------------------------------------+
| [ Buscar alvo: M42, Orion, NGC... ]|
| (Hoje) (Nebulosa) (Galaxia) (Aglo.)|
+------------------------------------+
| <<<  M8 Lagoa           alto 52    |
|      Nebulosa  cabe no campo       |
| <<<  M20 Trifida        alto 49    |
|      Nebulosa  cabe no campo       |
| <<<  M51 Redemoinho     baixo 12   |
|      Galaxia   sobe as 02:10       |
| (i)  NGC 253 Escultor   alto 61    |
|      Galaxia   maior que o campo   |
+------------------------------------+
| Atlas  Planejar [OBSERVAR] Gal Apar|
+------------------------------------+
```

O filtro "Hoje" já vem ligado e ordena pelo que está melhor agora. Alvos que não cabem no
campo ou estão baixos aparecem, mas dizem por quê.

### 3.6 Ficha do alvo

```
+------------------------------------+
| <  M8 Nebulosa da Lagoa            |
+------------------------------------+
| <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< |
| <<<  foto + moldura do nosso  <<<< |
| <<<  sensor sobre o alvo      <<<< |
+------------------------------------+
| Altitude nesta noite               |
|      .--''''--.                    |
|   .-'          '-.                 |
| _/_______________\_____ 25 graus   |
| 19h   22h   01h   04h              |
| Melhor: 20:10 a 23:40              |
| Tamanho 90 x 40 arcmin  mag 6,0    |
|                                    |
| [ Observar agora ] [ Por no plano ]|
+------------------------------------+
```

### 3.7 Planejar

```
+------------------------------------+
| Plano desta noite        [ Iniciar ]|
+------------------------------------+
| 20:10  M8 Lagoa         60 min     |
|        alto ate 23:40              |
| 21:15  M20 Trifida      45 min     |
| 22:05  NGC 253          90 min     |
|        ::: arraste para reordenar  |
| 23:40  (livre ate 04:50)           |
|                                    |
| [ + Adicionar alvo ]               |
+------------------------------------+
| Regras: nao abaixo de 25 graus     |
| Refazer o foco a cada alvo         |
+------------------------------------+
```

Com a noite rodando, a mesma tela vira linha do tempo: o que terminou (com miniatura), o que
está em curso, o que falta, e os motivos de cada alvo pulado.

### 3.8 Galeria e estúdio

```
+------------------+-----------------+
| <<< M8  21 min   | <<< M20 45 min  |
|     ontem        |     ontem       |
+------------------+-----------------+
| <<< M51 2 h      | <<< Lua         |
|     12 set       |     10 set      |
+------------------+-----------------+

  tocar numa sessao abre o estudio:

+------------------------------------+
| <  M8 Lagoa   21 min    [ Exportar ]|
+------------------------------------+
| <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< |
| <<<<   segurar = ver o antes  <<<< |
| <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< |
+------------------------------------+
| (Natural)(Vivido)(Nebulosa)(Suave) |
| Brilho        ------o-------       |
| Cor           ---o----------       |
| Ruido         ---------o----       |
| [ Mais ajustes ]                   |
+------------------------------------+
```

Cada movimento de controle pede uma prévia à Jetson; o app mostra a anterior até a nova
chegar, sem piscar.

### 3.9 Aparelho

```
+------------------------------------+
| Montagem        conectada          |
| RA 18h03  DEC -24 23   parada      |
|         [ N ]                      |
|   [ O ] [PARAR] [ L ]   veloc. (2) |
|         [ S ]                      |
| [ Estacionar ] [ Casa ] (Rastreio) |
+------------------------------------+
| Foco    posicao 6294               |
| [ -100 ] [ -10 ] [ +10 ] [ +100 ]  |
+------------------------------------+
| Rede    em casa (WiFi do roteador) |
| Sistema versoes, disco, desligar   |
+------------------------------------+
```

## 4. Fluxos principais

**Primeira vez (produto).** Ligar o telescópio → abrir o app → ler o QR do aparelho (entra no
WiFi dele e pareia) → dar um nome → opcional: informar o WiFi de casa → o app envia hora e
local → pronto. Cinco passos, nenhum IP.

**Noite rápida.** Abrir o app (conecta sozinho) → tocar no alvo sugerido → o app aponta,
reconhece o céu, centraliza e foca → começa a empilhar → olhar a imagem crescer → Salvar.
Um toque para começar, um para terminar.

**Noite autônoma.** Atlas → "Pôr no plano" em três ou quatro alvos → Planejar → Iniciar →
bloquear o celular. De manhã o app mostra a linha do tempo e as imagens.

**O sinal caiu.** A faixa de estado passa a "reconectando"; a imagem fica congelada com a hora
da última atualização; nada é desfeito. Ao voltar, o app busca o estado completo.

**Algo deu errado.** O erro aparece na etapa em que ocorreu, em linguagem direta ("Não consegui
reconhecer o céu: poucas estrelas na imagem"), com as saídas possíveis. Nunca um código solto.

## 5. Sistema visual

Herda o `src/server/ui_kit.py`, para o app e as páginas parecerem o mesmo produto.

| Elemento | Definição |
|---|---|
| Cores | fundo `#04060c`, superfície `#0a0f1b`, destaque `#33ddc4`, dourado `#f5b95c`, lilás `#9aa2ff`, ok `#49d17e`, erro `#ff5d6c`, texto `#e9eefb`, texto fraco `#8492b0` |
| Modo vermelho | filtro sobre o app inteiro: tudo em tons de vermelho escuro, brilho reduzido. Um toque na faixa de estado |
| Tipografia | uma fonte sem serifa para texto e uma monoespaçada para números de telemetria; as duas livres e embutidas no app, para Android e iPhone ficarem iguais |
| Ícones | **só os nossos**, desenhados (retículo, foco, obturador, nebulosa, galáxia, planeta, satélite…). Nenhum emoji, nenhum ícone de biblioteca pronta. Exportados do `ui_kit` para o app por script, para existir uma fonte só |
| Forma | cantos de 14 e 11 dp, grade de 8 dp, superfícies com borda fina em vez de sombra |
| Movimento | transições curtas (até 150 ms), sem clarões; a imagem nunca pisca ao atualizar |
| Toque | vibração curta quando um comando é aceito; som só se o usuário ligar |

## 6. Palavras

Modo simples fala como gente: "Ir para o alvo", "Focar", "42 fotos, 21 minutos", "nitidez
boa". O modo Pro usa os termos do ofício (FWHM, SNR, ganho, plate solve). O mesmo dado, dois
vocabulários. Português do Brasil primeiro; inglês pela mesma estrutura de tradução.

## 7. Acessibilidade

Contraste conferido nos dois temas (o vermelho tem pouco contraste por natureza: os textos
ficam maiores nele); o app respeita o tamanho de fonte do sistema; todo botão tem rótulo para
leitor de tela; nada depende só de cor (estado sempre tem texto junto).
