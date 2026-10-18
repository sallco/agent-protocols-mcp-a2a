# HDT5 & HDT6 — Orquestación Multiagente y Evaluación de Calidad (Evals) (Parachute S.A.)

Sistema Multiagente (MAS) para atención al cliente, evaluación meteorológica y calendarización de saltos en paracaídas para el evento nacional Guatemala 2026.

La nueva etapa de protocolos está definida en el [diseño acordado de MCP y A2A](docs/diseno_mcp_a2a.md), con arquitectura, interfaces, hitos y criterios de aceptación. Su implementación se revisará paso a paso.

Este proyecto abarca dos etapas clave del ciclo de desarrollo de software e inteligencia artificial:
1. **HDT5 — Orquestación Multiagente**: Implementación, benchmark y análisis comparativo de **tres arquitecturas de orquestación**:
   - **Centralizada**: Un orquestador principal que delega en especialistas mediante `as_tool()`.
   - **Jerárquica**: Un orquestador raíz que coordina supervisores de dominio (`Conocimiento` y `Operaciones`), los cuales a su vez coordinan agentes hoja.
   - **Descentralizada**: Red de agentes pares que se transfieren el control entre sí mediante `handoff()`, preservando contexto sin un coordinador central.
2. **HDT6 — Evaluación de Calidad con Evals (Promptfoo)**: Marco integral de evaluación automatizada para la puesta en productivo del agente sobre la arquitectura seleccionada (**Centralizada**), validando factualidad RAG, reglas deterministas, latencia y ejecución segura de herramientas.

> 📄 **Informe técnico completo de HDT5 (PDF):** [`docs/Hoja de trabajo 5 - Orquestación.pdf`](docs/Hoja%20de%20trabajo%205%20-%20Orquestaci%C3%B3n.pdf) *(análisis comparativo, métricas y respuestas a preguntas de diseño)*. Ver [previsualización abajo](#6-documentación-e-informe-técnico).
> 📊 **Reporte de evaluación de HDT6 (Promptfoo):** [`evals/results/promptfoo.json`](evals/results/promptfoo.json) *(100% de tests aprobados)*. Ver [sección de evals abajo](#5-hoja-de-trabajo-6--evals-con-promptfoo-puesta-en-producción).

---

## 1. Arquitecturas de Orquestación

### Arquitectura 1: Centralizada (`arch_centralizada.py`)

Un único agente orquestador atiende al usuario y coordina a los especialistas como herramientas (`as_tool()`). El control siempre retorna al centro antes de emitir una respuesta consolidada.

```mermaid
graph TD
    U["Usuario"] <--> O["Orquestador Central<br/>(Único punto de contacto)"]

    O -->|as_tool: consultar_faqs| A1["Especialista FAQs<br/>(Conocimiento institucional)"]
    O -->|as_tool: consultar_clima_seguridad| A2["Especialista Clima/Seguridad<br/>(Pronóstico y Veredicto)"]
    O -->|as_tool: gestionar_agenda| A3["Especialista Agenda<br/>(Cupos y Citas)"]

    A1 --> T1[("PostgreSQL + pgvector<br/>120 FAQs / HNSW")]
    A2 --> T2["API Open-Meteo<br/>(Ventana 08-16h)"]
    A2 --> T3["core/safety.py<br/>(Reglas deterministas)"]
    A3 --> T4[("PostgreSQL: citas<br/>(Restricción única fecha/hora)")]
```

### Arquitectura 2: Jerárquica (`arch_jerarquica.py`)

Estructura de dos niveles de decisión: el Orquestador Raíz delega en un **Supervisor de Conocimiento** (FAQs y políticas) y un **Supervisor de Operaciones**, quien impone la secuencia obligatoria: `clima -> evaluación de seguridad -> agenda`.

```mermaid
graph TD
    U["Usuario"] <--> R["Orquestador Raíz<br/>(Dirección y Síntesis)"]

    R -->|as_tool| S1["Supervisor de Conocimiento<br/>(FAQs y Políticas)"]
    R -->|as_tool| S2["Supervisor de Operaciones<br/>(Impositor de secuencia técnica)"]

    S1 -->|as_tool| H1["Agente FAQs Hoja"]
    S1 -->|as_tool| H2["Agente Políticas Hoja"]

    S2 -->|as_tool: 1. Clima| H3["Agente Clima Hoja"]
    S2 -->|as_tool: 2. Veredicto| H4["Agente Evaluación Hoja"]
    S2 -->|as_tool: 3. Reserva| H5["Agente Agenda Hoja"]

    H1 --> T1[("PostgreSQL + pgvector<br/>faqs")]
    H3 --> T2["API Open-Meteo<br/>(08-16h)"]
    H4 --> T3["core/safety.py<br/>(Veredicto Python)"]
    H5 --> T4[("PostgreSQL: citas<br/>(Transaccional)")]
```

### Arquitectura 3: Descentralizada (`arch_descentralizada.py`)

Red de pares autónomos sin coordinador permanente. La atención inicia en `agente_faqs` y el control se transfiere dinámicamente mediante `handoff()` según el dominio requerido.

```mermaid
graph LR
    U["Usuario"] <--> F["Agente FAQs<br/>(Receptor inicial)"]

    F <-->|handoff: clima / viabilidad| C["Agente Clima / Seguridad"]
    C <-->|handoff: reservar con evidencia| A["Agente Agenda / Citas"]
    A <-->|handoff: dudas institucionales| F
    A <-->|handoff: falta evidencia clima| C

    F --> T1[("PostgreSQL + pgvector<br/>faqs")]
    C --> T2["API Open-Meteo + safety.py"]
    A --> T3[("PostgreSQL: citas<br/>(Guardarraíl determinista)")]
```

---

## 2. Decisiones Técnicas y Guardarraíles Críticos

1. **Evaluación de Seguridad Determinista en Python Puro (`core/safety.py`)**:
   - El LLM **nunca** calcula ni relaja umbrales de seguridad.
   - Viento: `< 20 km/h` (IDEAL), `20–28 km/h` (MARGINAL: solo tándem experimentado), `> 28 km/h` (PROHIBIDO).
   - Ráfagas: `> 35 km/h` (PROHIBIDO).
   - Precipitación: `> 0.0 mm` (PROHIBIDO).
   - Nubes: `< 30%` (IDEAL), `30–75%` (MARGINAL), `> 75%` (PROHIBIDO).
   - Temperatura: Informativa, sin veto.
   - Veredicto global: El **peor** de los estados individuales.

2. **Ventana Operativa de Salto (08:00–16:00) vs Agregación Diaria 24h**:
   - En las coordenadas del Pacífico guatemalteco (`14.013722, -90.771611`), la temporada lluviosa de septiembre/octubre presenta chubascos nocturnos y nubosidad de tormenta que provocarían que `precipitation_sum > 0` y `cloud_cover_max > 75%` en prácticamente el 100% de los días a nivel de 24 horas.
   - Por ello, el sistema adopta como modo principal la **agregación sobre la franja diurna operativa (08:00 a 16:00)** consultando las variables horarias de Open-Meteo. También se soporta modo `--mock-clima ideal|marginal|prohibido` para pruebas reproducibles.

3. **Invariante de Evidencia Meteorológica por Turno**:
   - Para evitar fallos de red o latencia al confirmar citas, la evidencia meteorológica obtenida es válida durante todo el turno de conversación.
   - La función `agendar_cita` verifica que: `fecha_cita == fecha_evidencia`, `coords == coords_base` y `veredicto != PROHIBIDO`.

4. **Persistencia Transaccional con Restricción Única**:
   - Tabla `citas` en PostgreSQL con restricción `UNIQUE (fecha, hora)` que impide sobrecupos (1 cita por franja de 1 hora, 8 franjas diarias de 08:00 a 15:00).
   - Idempotencia garantizada por clave única.

---

## 3. Instalación y Configuración

### 3.1 Requisitos Previos y Entorno Python

El proyecto requiere **uv**, **Docker / Docker Compose** y **Node.js 20 o superior** para las evaluaciones con Promptfoo. La versión de Python está fijada en 3.12 y `uv` crea y administra automáticamente el entorno virtual:

```bash
uv sync
```

No es necesario activar `.venv` ni instalar dependencias con `pip`; `pyproject.toml` y `uv.lock` son las fuentes de dependencias reproducibles del proyecto.

---

### 3.2 Base de Datos PostgreSQL con pgvector

Una vez que el motor de Docker esté en ejecución, levanta el contenedor con la base de datos y la extensión vectorial:

```bash
docker compose up -d
docker compose ps
```
*(El comando es idéntico en Linux, macOS y Windows PowerShell/CMD).*

### 3.3 Configuración del archivo `.env`

Copia la plantilla de variables de entorno según tu sistema operativo:

- **Linux / macOS**:
  ```bash
  cp .env.example .env
  ```
- **Windows (PowerShell)**:
  ```powershell
  Copy-Item .env.example .env
  ```
- **Windows (CMD)**:
  ```cmd
  copy .env.example .env
  ```

Configura tus credenciales en el archivo `.env`:
```dotenv
NVIDIA_API_KEY=<tu-clave-de-nvidia>
OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1
MODEL=z-ai/glm-5.3
DATABASE_URL=postgresql://parachute:parachutepass@localhost:5432/parachutedb
FAQ_TABLE=faqs
CITAS_TABLE=citas
```

---

## 4. Guía de Ejecución

### 4.1 Carga del Corpus de FAQs
Genera embeddings normalizados de 384 dimensiones y carga las 120 FAQs en PostgreSQL:
```bash
uv run python main.py load
```

### 4.2 Prueba de Humo con Fallback de Modelos
Valida la conectividad a NVIDIA NIM y comprueba tool calling, `as_tool()`, `handoff()` y desactivación de telemetría:
```bash
uv run python main.py smoke-test
```

### 4.3 Ejecución del Chat en las Tres Arquitecturas

Puedes iniciar una sesión interactiva en cualquiera de las tres arquitecturas:

- **Arquitectura Centralizada (predeterminada)**:
  ```bash
  uv run python main.py chat --arquitectura centralizada
  ```
- **Arquitectura Jerárquica**:
  ```bash
  uv run python main.py chat --arquitectura jerarquica
  ```
- **Arquitectura Descentralizada**:
  ```bash
  uv run python main.py chat --arquitectura descentralizada
  ```

*Nota: También puedes ejecutar directamente `uv run python arch_centralizada.py`, `uv run python arch_jerarquica.py` o `uv run python arch_descentralizada.py`.*

#### 🧪 Simulación de Escenarios Meteorológicos con `--mock-clima`
Para probar determinísticamente los guardarraíles sin depender del clima real del día:
```bash
# Simular condiciones óptimas (viento bajo, despejado, sin lluvia)
uv run python main.py chat --arquitectura centralizada --mock-clima ideal

# Simular condiciones de riesgo (lluvia o viento fuerte que veta la reserva)
uv run python main.py chat --arquitectura centralizada --mock-clima prohibido
```

#### 💬 Ejemplos de Preguntas y Flujos para Probar

A continuación se presentan consultas sugeridas para validar la especialización de cada agente, las transferencias de control y los guardarraíles del sistema:

##### 1. Conocimiento y Políticas (FAQs RAG)
Prueba la recuperación semántica sobre la base de 120 preguntas frecuentes:
- *"¿Cuáles son los requisitos de peso y edad mínima para realizar un salto tándem?"*
- *"¿Qué tipo de ropa y calzado recomiendan llevar el día de la actividad?"*
- *"¿Qué certificaciones tienen los instructores y qué incluye el seguro de salto?"*

##### 2. Evaluación Meteorológica y Reglas de Seguridad
Prueba la consulta a Open-Meteo y el evaluador determinista en Python (`core/safety.py`):
- *"¿Es seguro saltar mañana? ¿Cómo estarán el viento y la nubosidad en la zona de salto?"*
- *"¿Se puede saltar el próximo sábado en la mañana en las coordenadas del evento?"*
- *"¿Qué sucede si hay ráfagas de viento mayores a 30 km/h el día de mi salto?"*

##### 3. Flujo Integrado: Consulta de Clima + Reserva de Cita
Prueba la coordinación completa: el sistema evalúa el clima y, solo si es viable, reserva en PostgreSQL:
- *"Hola, quiero agendar un salto para mañana a las 10:00 a nombre de Diego Calderón (correo: diego@example.com, tel: 5555-1234). ¿Las condiciones climáticas lo permiten?"*
- *"¿Hay cupos disponibles para pasado mañana entre las 09:00 y las 12:00? Si el clima es apto, resérvame a las 11:00 para María López (maria@example.com, tel: 4444-1234)."*

##### 4. Control de Límites y Preguntas Fuera de Dominio
Prueba que los agentes no alucinen ni desvíen su propósito:
- *"¿Me pueden vender un boleto de avión comercial hacia Flores, Petén?"* (debe declinar amablemente y enfocarse en saltos de paracaidismo de Parachute S.A.).
- *"¿Cuál es la receta para preparar un pastel de chocolate?"*

### 4.4 Pruebas Automatizadas
Ejecuta la suite de pruebas unitarias y de integración (casos frontera de seguridad, fechas relativas, concurrencia de reservas y aislamiento de FAQs):
```bash
uv run pytest tests/
```

Las pruebas de citas crean una tabla `test_citas_<uuid>` por caso y eliminan
únicamente esa tabla al finalizar. No limpian ni modifican las citas de la tabla
configurada para la aplicación. Requieren PostgreSQL disponible; las pruebas que
no usan persistencia no abren conexiones a la base de datos.

### 4.5 Benchmark Comparativo de Arquitecturas
Ejecuta la matriz comparativa de latencia y respuestas:
```bash
uv run python main.py benchmark
```
Los resultados observados se almacenan en `data/comparativa_arquitecturas.json`.

### 4.6 Evals con Promptfoo (Resumen Rápido)

Para ejecutar rápidamente la suite de evaluación con Promptfoo:

```bash
# Instalar dependencias de evaluación
npm ci

# Ejecutar suite con intérprete del entorno virtual
PROMPTFOO_PYTHON=.venv/bin/python npm run eval:ci

# Abrir visor interactivo en navegador
npm run eval:view
```

El reporte de evaluación se guarda en `evals/results/promptfoo.json`. Para ver la documentación detallada de la metodología, justificación, tipos de evals y resultados, consulta la [Sección 5](#5-hoja-de-trabajo-6--evals-con-promptfoo-puesta-en-producción).

---

## 5. Hoja de Trabajo #6 — Evals con Promptfoo (Puesta en Producción)

Para cerrar el ciclo de desarrollo previo a la puesta en producción en Parachute S.A., se implementó un marco formal de evaluaciones (**Evals**) utilizando **Promptfoo**. Este framework evalúa de manera continua, reproducible y automatizada las dos funcionalidades críticas del sistema sobre la arquitectura seleccionada.

---

### 5.1 Selección y Justificación de la Mejor Arquitectura

Tras el análisis comparativo y el benchmark de la Hoja de Trabajo #5, se seleccionó la **Arquitectura Centralizada (`arch_centralizada.py`)** como la mejor solución técnica para producción por las siguientes razones:

1. **Control Determinista y Prevención de Desvíos**:
   El orquestador central funge como único punto de contacto y orquesta las herramientas (`consultar_faqs`, `consultar_clima_seguridad`, `gestionar_agenda`) garantizando que los flujos sigan el protocolo operacional sin desviaciones ni alucinaciones de roles.
2. **Eficiencia en Tokens y Latencia**:
   La arquitectura jerárquica introduce supervisores intermedios que aumentan la latencia y el consumo de tokens en turnos dobles de delegación. La descentralizada, por su parte, requiere transferencias de estado (`handoff`) propensas a dispersión de contexto. La centralizada ofrece el mejor balance entre velocidad de respuesta y trazabilidad.
3. **Auditabilidad y Verificación de Herramientas**:
   Permite registrar e inspeccionar en una sola secuencia de ejecución (`tool_sequence`) cada herramienta ejecutada, facilitando aserciones de seguridad y guardarraíles deterministas en CI/CD.

---

### 5.2 Funcionalidades Evaluadas del Sistema

El agente de Parachute S.A. tiene dos capacidades fundamentales, ambas cubiertas exhaustivamente en la suite de evaluación:

1. **Resolución de Preguntas Frecuentes (FAQs RAG)**:
   - Consulta sobre el corpus de 120 preguntas institucionales indexadas en PostgreSQL con pgvector (HNSW).
   - Respuestas con fuentes exactas (`FAQ-ID`), montos de recargos por peso y tiempos de espera médica.
   - Derivación controlada a soporte humano (`soporte@parachutesa.gt`) cuando la información requerida no existe en la base de conocimiento oficial.
2. **Calendarización y Gestión de Citas**:
   - Resolución de fechas relativas a formato ISO (`YYYY-MM-DD`).
   - Evaluación meteorológica obligatoria (Open-Meteo o fixtures deterministas) sobre la ventana diurna operativa (08:00 a 16:00).
   - Invariante de seguridad: veto estricto de agendamiento si el veredicto meteorológico es `PROHIBIDO` o la fecha está fuera de la ventana del evento.
   - Reserva atómica en PostgreSQL con verificación de disponibilidad de cupo (1 cita por hora).

---

### 5.3 Tipos de Evaluaciones Implementadas

La configuración en [`evals/promptfooconfig.yaml`](evals/promptfooconfig.yaml) y [`evals/casos.yaml`](evals/casos.yaml) implementa las cuatro dimensiones de evaluación requeridas:

| Tipo de Eval | Propósito y Criterio | Implementación en Promptfoo |
| :--- | :--- | :--- |
| **Factualidad (`factuality`)** | Evalúa que la respuesta del agente no alucine y sea semánticamente fiel a la verdad institucional (e.g. peso máximo estricto de 100 kg, recargo de Q250 entre 90 y 100 kg, espera de 24h tras buceo). | Evaluador basado en LLM vía NVIDIA NIM ([`evals/grader_nvidia.py`](evals/grader_nvidia.py)) con el modelo activo (`z-ai/glm-5.3`). |
| **Determinísticos (`contains` / `regex`)** | Verificación estricta de códigos de FAQ obligatorios (`FAQ-021`, `FAQ-029`), valores exactos (`100 kg`, `24 horas`, `Q250`), correo oficial (`soporte@parachutesa.gt`), estados de veredicto (`IDEAL`, `MARGINAL`, `PROHIBIDO`) y expresiones de denegación. | Aserciones estándar `contains` y `regex` con soporte insensible a mayúsculas/minúsculas. |
| **Latencia (`latency`)** | Garantizar que el agente responda dentro de límites operacionales aceptables en un entorno de producción. | Aserción global en `defaultTest`: `latency_ms < 120000` (120 segundos). |
| **Ejecución de Herramientas (`tool execution`)** | Validar que el agente llame a las herramientas correctas en el orden adecuado, y que **se abstenga** de llamar a herramientas transaccionales ante condiciones adversas. | Aserciones `javascript` sobre `tool_sequence` y `appointment.exito`: <br/>• Flujo positivo: verifica la secuencia completa `['resolver_fecha', 'consultar_clima', 'evaluar_condiciones', 'consultar_disponibilidad', 'agendar_cita']`. <br/>• Guardarraíl negativo: comprueba que `agendar_cita` **no** se invoque ante veredicto `PROHIBIDO` o fecha fuera de ventana. |

---

### 5.4 Aislamiento Transaccional y Reproducibilidad

Para garantizar que la suite de evaluación sea 100% determinista, aislada y ejecutable en CI/CD:

1. **Aislamiento de Citas en Base de Datos ([`evals/isolated_agenda.py`](evals/isolated_agenda.py))**:
   Cada caso de evaluación corre en su propio esquema temporal en PostgreSQL creando una tabla efímera `eval_citas_<uuid>`. Esto evita que las reservas de un caso de prueba colisionen o bloqueen franjas horarias en casos subsiguientes, y elimina el riesgo de contaminar la tabla de citas de producción.
2. **Fixtures Meteorológicos Deterministas**:
   Se emplean modos mock (`ideal`, `marginal`, `prohibido`) en los casos de reserva para evaluar los guardarraíles de seguridad sin depender de la conectividad o fluctuaciones de la API de Open-Meteo.
3. **Modo Offline de Embeddings**:
   Se exportan `HF_HUB_OFFLINE=1` y `TRANSFORMERS_OFFLINE=1` en [`evals/run_promptfoo.sh`](evals/run_promptfoo.sh) y [`evals/provider_centralizada.py`](evals/provider_centralizada.py) para utilizar el modelo local predescargado de `SentenceTransformer`, evitando peticiones externas redundantes.
4. **Cierre Limpio de Conexiones Asíncronas**:
   El proveedor asíncrono cierra explícitamente el cliente HTTP y los transportes de conexión en bloques `finally`, evitando excepciones de bucle de eventos cerrado (`RuntimeError: Event loop is closed`) en versiones recientes de Python (3.11+ / 3.14).

---

### 5.5 Guía de Ejecución y Reporte de Entrega

#### Prerrequisitos
- Node.js 20 o superior y npm.
- uv con Python 3.12 y dependencias sincronizadas mediante `uv sync`.
- Base de datos PostgreSQL iniciada con Docker Compose y corpus de FAQs cargado (`uv run python main.py load`).
- Clave de API de NVIDIA configurada en `.env`.

#### Ejecución de la Suite (CI Mode)
```bash
# 1. Instalar dependencias de evaluación
npm ci

# 2. Ejecutar la evaluación especificando el intérprete de Python del entorno virtual
PROMPTFOO_PYTHON=.venv/bin/python npm run eval:ci
```

#### Visualización Interactiva en Navegador
Para abrir la interfaz web de Promptfoo y explorar las respuestas, prompts, tokens, latencias y detalles de cada aserción:
```bash
npm run eval:view
```

#### Archivo de Reporte para la Entrega
El archivo de reporte generado por Promptfoo ha sido confirmado y versionado en el repositorio:
- 📄 **Ruta del reporte:** [`evals/results/promptfoo.json`](evals/results/promptfoo.json)
- **Estado de la evaluación:**
  - ✅ **Tests aprobados:** **7 / 7 (100% PASS)**
  - ❌ **Tests fallidos:** **0 (0%)**
  - ⚠️ **Errores de ejecución:** **0 (0%)**

---

## 6. Documentación e Informe Técnico (HDT5)

El informe académico formal de la práctica HDT5, con las respuestas fundamentadas a las preguntas de diseño, el análisis crítico de desempeño y los diagramas de flujo, se encuentra disponible en formato PDF en la carpeta `docs/`:

- 📄 **Documento completo:** [docs/Hoja de trabajo 5 - Orquestación.pdf](docs/Hoja%20de%20trabajo%205%20-%20Orquestaci%C3%B3n.pdf)

### Previsualización del Informe

<p align="center">
  <a href="docs/Hoja%20de%20trabajo%205%20-%20Orquestaci%C3%B3n.pdf" title="Clic para abrir el PDF">
    <img src="docs/preview_informe.png" alt="Previsualización del Informe Técnico PDF" width="750"/>
  </a>
  <br/>
  <em>Haz clic en la imagen superior para abrir o descargar el documento PDF completo (4 páginas).</em>
</p>
