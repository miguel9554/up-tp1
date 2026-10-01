# Síntesis lógica con LibreLane (sky130)

Este proyecto corre **síntesis lógica** y **análisis estático de timing (STA)**
de diseños en Verilog/SystemVerilog con el flujo open source [LibreLane] y el
PDK **sky130** de SkyWater. Genera reportes similares a los de una herramienta
de síntesis comercial (Cadence Genus): QoR, área, compuertas, timing y
potencia.

Incluye dos diseños:

| Diseño    | Qué es                                              | Tiempo de corrida |
| :-------- | :-------------------------------------------------- | :---------------- |
| `counter` | Contador de 8 bits: ejemplo chico para aprender el flujo | segundos     |
| `ibex`    | CPU RISC-V [Ibex] con macros de SRAM                | ~2 min cada una   |

Todas las herramientas (Yosys, OpenSTA, Verilator, ...) corren dentro del
contenedor Docker oficial de LibreLane, así que en tu máquina solo tenés que
instalar Docker, `git` y `make`.

[LibreLane]: https://github.com/librelane/librelane
[Ibex]: https://github.com/lowRISC/ibex

---

## 1. Instalación (una sola vez)

Estas instrucciones son para **Ubuntu 22.04 / 24.04 (x86_64)**. Necesitás
unos **20 GB libres en disco** (8 GB de la imagen del contenedor, 6 GB del
PDK, más las corridas) y conexión a Internet para la primera corrida.

### 1.1 Herramientas básicas y Docker

```bash
sudo apt update
sudo apt install -y git make docker.io
```

Permití que tu usuario use Docker sin `sudo`:

```bash
sudo usermod -aG docker $USER
```

**Cerrá la sesión y volvé a entrar** (o reiniciá) para que el cambio de grupo
tenga efecto. Después verificá que Docker funciona:

```bash
docker run --rm hello-world
```

Tendrías que ver `Hello from Docker!`. Si aparece `permission denied ...
docker.sock`, todavía no cerraste y volviste a abrir la sesión.

### 1.2 Obtener el proyecto

El repositorio está en <https://github.com/miguel9554/up-tp1>. El CPU Ibex
está incluido como submódulo de git, así que cloná con `--recursive`:

```bash
git clone --recursive https://github.com/miguel9554/up-tp1.git
cd up-tp1
```

> Si ya clonaste sin `--recursive`, corré `git submodule update --init`
> dentro del proyecto.

### 1.3 Descargar el contenedor de LibreLane

```bash
docker pull ghcr.io/librelane/librelane:3.0.14
```

Es una descarga grande (~1.5 GB, ~7.5 GB descomprimida); se hace una sola vez.

### 1.4 Descargar el PDK

El PDK (*process design kit*) contiene las bibliotecas de celdas estándar, las
macros de SRAM y todo lo que las herramientas necesitan saber del proceso
sky130. Lo administra **ciel**, que ya viene incluido en el contenedor; no
hace falta instalarlo.

```bash
make pdk
```

Esto descarga en `~/.ciel` (~6 GB) la versión exacta del PDK que espera esta
versión de LibreLane, incluyendo las dos bibliotecas de celdas estándar que se
usan acá (`sky130_fd_sc_hd`, `sky130_fd_sc_hs`) y las macros de SRAM. Solo hay
que hacerlo una vez. En la [sección 4](#4-archivos-del-pdk-y-de-las-bibliotecas)
se explica qué hay adentro y dónde encontrar cada archivo.

Listo. Todo lo que sigue se corre desde el directorio del proyecto.

---

## 2. Primera síntesis: el contador

El diseño está en `designs/counter/`:

```
designs/counter/
├── src/counter.v        RTL: contador de 8 bits con enable y reset asincrónico
├── config.json          configuración de LibreLane (diseño, clock, SDC, ...)
├── constraints.sdc      restricciones de timing (clock, retardos de E/S, carga)
└── variants/
    ├── hd.json          variante: biblioteca de celdas de alta densidad
    └── hs.json          variante: biblioteca de celdas de alta velocidad
```

Abrí `config.json`: ahí se indica el módulo top (`DESIGN_NAME`), los archivos
fuente (`VERILOG_FILES`), el puerto y el período del clock (`CLOCK_PORT`,
`CLOCK_PERIOD` en ns) y el archivo de restricciones SDC.

### 2.1 Síntesis

```bash
make synth
```

Esto corre el lint de Verilator y la síntesis con Yosys, mapeando el RTL a
celdas de la biblioteca `sky130_fd_sc_hd`. Al final imprime un resumen de QoR:

```
| Metric              |   Value |
| :------------------ | ------: |
| Cell count          |      26 |
| Std-cell area (µm²) | 380.365 |
...
```

Cada corrida crea un directorio nuevo `designs/counter/runs/<variante>_<fecha>_<hora>/`:

```
runs/hd_2026-10-01_14-33-08/
├── reports/              <-- reportes legibles (empezá por acá)
├── final/nl/counter.nl.v     netlist a nivel compuertas
├── final/metrics.json        todas las métricas, en formato para máquinas
├── 06-yosys-synthesis/       paso de síntesis (logs, reportes crudos de Yosys)
├── resolved.json             configuración final, con las rutas a todos los archivos usados
├── flow.log                  log completo de la corrida
└── warning.log, error.log    deberían estar vacíos
```

Vale la pena mirar el netlist `final/nl/counter.nl.v`: el bloque `always` se
convirtió en instancias de celdas de la biblioteca (flip-flops
`sky130_fd_sc_hd__dfrtp_2`, `xor2`, `and3`, ...).

### 2.2 Síntesis + análisis de timing

```bash
make sta
```

Lo mismo que `make synth`, más el análisis estático de timing del netlist
sintetizado con **OpenSTA** en tres esquinas PVT:

| Esquina            | Proceso | Temperatura | Tensión |
| :----------------- | :------ | ----------: | ------: |
| `nom_tt_025C_1v80` | típico  |       25 °C |  1.80 V |
| `nom_ss_100C_1v60` | lento   |      100 °C |  1.60 V |
| `nom_ff_n40C_1v95` | rápido  |      -40 °C |  1.95 V |

Para cada esquina se usa el archivo `.lib` de la biblioteca caracterizado en
esas condiciones (ver [sección 4.3](#43-archivos-de-timing-lib-y-esquinas)).

### 2.3 Reportes

`make synth` / `make sta` escriben estos archivos en `<run>/reports/`:

| Archivo     | Contenido                                                       | Requiere |
| :---------- | :-------------------------------------------------------------- | :------- |
| `qor.md`    | Resumen: celdas, área, lint, slack, violaciones, potencia       |          |
| `area.md`   | Área: secuencial / combinacional / macros                       |          |
| `gates.md`  | Instancias y área de cada tipo de celda                         |          |
| `timing.md` | Slack de setup/hold por esquina + caminos críticos de setup y hold | `sta` |
| `power.md`  | Potencia por esquina (interna / conmutación / fuga)             | `sta`    |

Cómo leer `timing.md`:

- El **slack de setup** (WS = *worst slack*, peor slack) tiene que ser
  **positivo**: el dato llega antes del próximo flanco de clock. Es peor en la
  esquina lenta (`ss`).
- El **slack de hold** también tiene que ser **positivo**: el dato no cambia
  demasiado pronto después del flanco de clock. Es peor en la esquina rápida
  (`ff`).
- El **camino crítico** lista cada celda desde el punto de inicio (puerto de
  entrada o flip-flop) hasta el punto final (puerto de salida o flip-flop), con
  el retardo de cada celda y el tiempo de llegada acumulado.

Cosas para probar (editá y volvé a correr `make sta`):

1. Bajá `CLOCK_PERIOD` en `config.json` (por ejemplo 10 → 3 → 1.5 ns) hasta
   que el slack de setup se vuelva negativo. ¿Cuál es la frecuencia máxima?
2. Cambiá el ancho del contador (`WIDTH` en `src/counter.v`) a 32 bits. ¿Cómo
   cambian el área y el camino crítico?

> El timing es **pre-layout**: las celdas no están ubicadas y los cables
> todavía no tienen resistencia ni capacidad, así que los números reales
> después de place-and-route son peores. La potencia usa una actividad de
> conmutación por defecto, así que es solo una estimación.

### 2.4 Comparar bibliotecas de celdas estándar

sky130 tiene varias bibliotecas de celdas estándar. Cada diseño tiene una
**variante** por biblioteca en `variants/`:

- `hd`: `sky130_fd_sc_hd`, **alta densidad** (chica, bajo consumo). Por defecto.
- `hs`: `sky130_fd_sc_hs`, **alta velocidad** (más grande, más rápida, más consumo).

Elegí una con `VARIANT`, o corré todas las variantes y comparalas:

```bash
make sta VARIANT=hs     # una variante
make sta-all            # todas las variantes, y después la comparación
```

`make sta-all` escribe `designs/counter/runs/compare.md`, con la última
corrida de cada variante lado a lado (área, slack por esquina, potencia...).
Lo podés regenerar en cualquier momento con `make compare`.

Un archivo de variante solo contiene los parámetros que cambian, y se combina
con `config.json`. Para agregar una variante, agregá un archivo en `variants/`.

---

## 3. Un CPU real: Ibex con macros de SRAM

[Ibex] es un CPU RISC-V de 32 bits (RV32IMC) de lowRISC. Su código fuente está
en `external/ibex` (el submódulo de git); `designs/ibex/` solo contiene lo
necesario para sintetizarlo:

```
designs/ibex/
├── config.json               configuración (ver abajo)
├── constraints.sdc           restricciones de timing
├── lint.vlt                  excepciones para warnings de lint conocidos e inofensivos
├── src/prim_ram_1p.sv        RAM implementada con macros de SRAM de sky130
├── src/prim_clock_gating.sv  clock gate con la celda ICG de sky130
└── variants/hd.json, hs.json
```

Qué cambia respecto del contador (ver `config.json`):

- **SystemVerilog**: `USE_SLANG` lee los fuentes con el frontend slang.
  `VERILOG_FILES` lista ~140 archivos directamente de `external/ibex`, y
  `VERILOG_INCLUDE_DIRS` apunta a los directorios con los headers de macros
  (`` `include "prim_assert.sv" ``, ...).
- **Parámetros**: `SYNTH_PARAMETERS` redefine parámetros del módulo top.
  `ICache=1'b1` habilita la caché de instrucciones.
- **Macros de SRAM**: la caché de instrucciones tiene 2 vías, cada una con una
  RAM de tags (22 bits x 256) y una RAM de datos (64 bits x 256). En lugar de
  construirlas con flip-flops, `src/prim_ram_1p.sv` las arma con la macro de
  SRAM del PDK `sky130_sram_1kbyte_1rw1r_32x256_8` (32 bits x 256 palabras):
  1 macro por RAM de tags y 2 por RAM de datos, **6 macros** en total.
  `MACROS` le indica a LibreLane dónde están las vistas de la macro (layout,
  `.lib` de timing, modelo Verilog) y lista las 6 instancias. La síntesis
  trata cada macro como una caja negra, y el STA usa su `.lib` para el timing.
- **Clock**: un período relajado de 100 ns (10 MHz). Es una demostración, no
  una implementación optimizada.

Correlo:

```bash
make sta DESIGN=ibex                # biblioteca de alta densidad, ~2 minutos
make sta-all DESIGN=ibex            # hd y hs, y después la comparación (~5 minutos)
```

Cosas para mirar:

- `reports/area.md`: las 6 macros de SRAM ocupan la mayor parte del área (~86 %).
- `reports/gates.md`: dominan las macros, los flip-flops (`dfrtp`) y los
  multiplexores (`mux2`, `mux4`) del banco de registros.
- `reports/timing.md`: el camino crítico empieza en una salida de SRAM (la
  RAM de tags) y pasa por la lógica de la caché hasta el bus de instrucciones.
- `runs/compare.md`: biblioteca hs vs hd en un diseño grande.

> `qor.md` reporta miles de **violaciones de max slew / max cap**. Es
> esperable: antes de place-and-route, los nets con mucho fanout (reset,
> enables, muxes) están manejados por una sola celda chica. Agregarles buffers
> es tarea del place-and-route, que este proyecto no corre.

---

## 4. Archivos del PDK y de las bibliotecas

### 4.1 Dónde está el PDK

`make pdk` usa ciel para instalar el PDK en `~/.ciel`, en un directorio por
versión:

```
~/.ciel/ciel/sky130/versions/<hash>/sky130A/
```

`<hash>` es la versión del PDK (un hash de git largo). Para no escribirlo,
guardá la ruta en una variable de la terminal:

```bash
PDK=$(ls -d ~/.ciel/ciel/sky130/versions/*/sky130A)
ls $PDK/libs.ref
```

> Si tenés más de una versión instalada, el comando anterior devuelve varias
> rutas. La que usa una corrida está en su `resolved.json`
> (`grep libs.ref <run>/resolved.json`).

Dentro del contenedor (`make shell`), el mismo directorio aparece como
`/pdks/ciel/sky130/versions/<hash>/sky130A/`. Por eso las rutas de
`resolved.json` empiezan con `/pdks`: para verlas desde tu máquina,
reemplazá `/pdks` por `~/.ciel`.

### 4.2 Estructura de una biblioteca

Cada biblioteca está en `$PDK/libs.ref/<biblioteca>/`:

| Biblioteca           | Qué es                                       |
| :------------------- | :------------------------------------------- |
| `sky130_fd_sc_hd`    | celdas estándar de alta densidad (variante `hd`) |
| `sky130_fd_sc_hs`    | celdas estándar de alta velocidad (variante `hs`) |
| `sky130_sram_macros` | macros de SRAM (Ibex usa `sky130_sram_1kbyte_1rw1r_32x256_8`) |

Y adentro, un subdirectorio por **vista** (cada herramienta usa una distinta):

| Subdirectorio | Formato | Contenido | Lo usa |
| :------------ | :------ | :-------- | :----- |
| `lib/`     | Liberty (`.lib`) | timing, potencia, área y función lógica de cada celda, una por esquina PVT | síntesis (Yosys/ABC), STA (OpenSTA) |
| `lef/`     | LEF | dimensiones de cada celda (`SIZE`) y posición de sus pines | place-and-route |
| `verilog/` | Verilog | modelo funcional de cada celda (simulación, cajas negras) | simulación, lint, síntesis de macros |
| `gds/`     | GDSII | layout completo (máscaras) | fabricación |
| `spice/`, `cdl/` | SPICE | netlist a nivel transistor | simulación eléctrica, LVS |
| `mag/`, `maglef/` | Magic | layout para el editor Magic | DRC/LVS, extracción |
| `techlef/` | LEF técnico | capas de metal y reglas de ruteo | place-and-route |

### 4.3 Archivos de timing (`.lib`) y esquinas

El nombre de cada `.lib` indica la esquina en la que fue caracterizado:

```
sky130_fd_sc_hd__ss_100C_1v60.lib
                 │  │    └── tensión: 1.60 V
                 │  └─────── temperatura: 100 °C
                 └────────── proceso: ss (lento), tt (típico), ff (rápido)
```

Cada esquina del STA (sección 2.2) usa el `.lib` con el mismo nombre:

| Esquina del STA     | Archivo `.lib` de la biblioteca `hd`  |
| :------------------ | :------------------------------------ |
| `nom_tt_025C_1v80`  | `sky130_fd_sc_hd__tt_025C_1v80.lib`   |
| `nom_ss_100C_1v60`  | `sky130_fd_sc_hd__ss_100C_1v60.lib`   |
| `nom_ff_n40C_1v95`  | `sky130_fd_sc_hd__ff_n40C_1v95.lib`   |

Para `hs`, lo mismo con `sky130_fd_sc_hs__...`. Las macros de SRAM tienen un
**solo** `.lib`, `sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib`, que se usa
en las tres esquinas.

Un `.lib` es texto: cada celda es un bloque `cell ("nombre") { ... }` con su
área, y adentro un bloque `pin (...)` por pin con su capacidad y sus arcos de
timing (`timing () { ... }`). Para encontrar una celda:

```bash
grep -n 'cell ("sky130_fd_sc_hd__dfrtp_2")' $PDK/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__ss_100C_1v60.lib
```

y abrí el archivo en esa línea con un editor (`less +<línea> archivo` o tu
editor favorito). Dentro del bloque de la celda vas a encontrar:

- `area`: área de la celda en µm² (la que usa `gates.md`).
- En cada pin de entrada de datos, arcos con `timing_type : "setup_rising"` y
  `"hold_rising"`: el **tiempo de setup y hold** del flip-flop respecto del
  flanco de subida del clock (`related_pin : "CLK"`).
- En los pines de salida, arcos con `cell_rise`/`cell_fall` (retardo) y
  `rise_transition`/`fall_transition` (slew de salida).

Los valores no son un número único sino **tablas** (`values(...)`) indexadas
por las variables que define su `lu_table_template` al principio del archivo
(por ejemplo, el slew de entrada y la capacidad de carga para un retardo, o el
slew del clock y el slew del dato para un setup). OpenSTA interpola en esas
tablas con los slews y cargas reales de cada camino; por eso el mismo tipo de
celda puede tener retardos distintos en lugares distintos del circuito.

### 4.4 Dimensiones de las celdas (`.lef`)

```bash
grep -A8 '^MACRO sky130_fd_sc_hd__dfrtp_2$' $PDK/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef
```

La línea `SIZE <ancho> BY <alto>` da las dimensiones en µm. Todas las celdas
de una misma biblioteca tienen la misma **altura** (se ubican en filas) y
varían en ancho.

### 4.5 Nombres de las celdas

Los nombres siguen el formato `<biblioteca>__<función>_<fuerza>`, por ejemplo
`sky130_fd_sc_hd__nand2_2`: compuerta NAND de 2 entradas con fuerza de manejo
(*drive strength*) 2. Una fuerza mayor significa transistores más anchos: más
corriente, más área y más capacidad de entrada. La descripción de cada celda
está en la documentación de sky130:
<https://skywater-pdk.readthedocs.io>.

---

## 5. Referencia

### Targets de make

| Comando                         | Qué hace                                          |
| :------------------------------ | :------------------------------------------------ |
| `make pdk`                      | Descarga el PDK sky130 en `~/.ciel` (una vez)     |
| `make synth`                    | Lint + síntesis                                   |
| `make sta`                      | Lint + síntesis + análisis estático de timing     |
| `make sta-all`                  | `make sta` para cada variante, y `make compare`   |
| `make compare`                  | Compara la última corrida de cada variante        |
| `make report`                   | Regenera los reportes de la última corrida        |
| `make shell`                    | Abre una terminal dentro del contenedor           |
| `make clean`                    | Borra todas las corridas del diseño               |

Opciones: `DESIGN=<nombre>` (por defecto `counter`) y `VARIANT=<nombre>` (por
defecto `hd`). Ejemplo: `make sta DESIGN=ibex VARIANT=hs`.

### Correr cualquier herramienta en el contenedor

`run.sh` corre cualquier comando dentro del contenedor de LibreLane, con este
directorio montado en `/work` y el PDK en `/pdks`:

```bash
./run.sh yosys -V               # versiones de las herramientas
./run.sh librelane --help       # opciones de LibreLane
./run.sh                        # terminal interactiva (igual que make shell)
```

Los archivos creados en el contenedor pertenecen a tu usuario.

### Agregar tu propio diseño

1. Copiá `designs/counter` a `designs/<nombre>` y borrá su `runs/`.
2. Poné tu RTL en `src/`, y en `config.json` configurá `DESIGN_NAME` (módulo
   top), `CLOCK_PORT` y `CLOCK_PERIOD`.
3. Adaptá el puerto de clock y el reset en `constraints.sdc`.
4. `make sta DESIGN=<nombre>`.

### Problemas frecuentes

| Problema                                        | Solución                                                    |
| :---------------------------------------------- | :---------------------------------------------------------- |
| `permission denied ... /var/run/docker.sock`    | Corré `sudo usermod -aG docker $USER`, cerrá la sesión y volvé a entrar |
| `external/ibex` está vacío                      | `git submodule update --init`                               |
| `no files matched glob pattern ... /pdks/...`   | Falta el PDK: corré `make pdk`                              |
| `No space left on device`                       | Liberá espacio (`docker system prune`): se necesitan ~20 GB |
| Errores de lint o síntesis en tu propio diseño  | Leé `<run>/flow.log` y el log del paso que falló            |

### Más información

- Documentación de LibreLane: <https://librelane.readthedocs.io>
- Documentación del PDK sky130: <https://skywater-pdk.readthedocs.io>
- Documentación de Ibex: <https://ibex-core.readthedocs.io>
