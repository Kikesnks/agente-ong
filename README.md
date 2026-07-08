# agente-ong

**Aplicación multi-agente de IA para ayudar a ONGs a encontrar subvenciones y redactar propuestas de proyecto.**

## Qué es

`agente-ong` es un sistema de agentes especializados construido en Python que automatiza dos de las tareas más costosas para una ONG: **encontrar convocatorias de financiación** y **redactar propuestas profesionales** que maximicen las posibilidades de aprobación.

El sistema busca en fuentes oficiales (BDNS del Gobierno de España, TED de la UE) y en la web general (Tavily), verifica la información cruzando fuentes, y aprende entre sesiones para mejorar con el uso.

## Autoría y proceso de construcción

Este proyecto nace de una idea propia basada en 20 años de experiencia gestionando negocios sostenibles de ámbito turístico en la región amazónica, trabajando con ONGs de cooperación internacional y conociendo de primera mano las necesidades de la región, la dificultad de encontrar financiación y de redactar propuestas competitivas.

Sobre el terreno ves muchas necesidades, muchos problemas que resolver y muchas ideas para hacerlo — pero la parte burocrática actúa como un cuello de botella que impide que muchos proyectos salgan adelante. Por ello decidí construir una aplicación práctica y rigurosa, fácil e intuitiva para el usuario, que automatice los dos puntos más tediosos de ese proceso: la búsqueda de recursos económicos y la redacción de propuestas de alto nivel.

**El rol del autor en este proyecto:**
- **Ideación y visión de producto**: definición del problema, los usuarios objetivos y el valor que debe aportar la herramienta.
- **Especificaciones funcionales**: redacción y aprobación de todos los `requirements.md` — qué debe hacer el sistema, qué no, y por qué.
- **Decisiones de arquitectura**: elección del stack (LangGraph, SQLite, Streamlit, patrón Ports & Adapters), decisión de separar ENGRAM del producto final, diseño del sistema de verificación cruzada con 5 estados, elección de SQLite frente a otras alternativas, decisión de investigación asíncrona, gestión de proyectos múltiples y subida de documentos en la UI.
- **Diseño del sistema**: aprobación de todos los `design.md` — cómo se estructura el código, qué patrones usar, cómo fluyen los datos.
- **Validación**: revisión y aprobación de cada tarea implementada, ejecución de pruebas contra APIs reales, detección y corrección de problemas en producción (filtro de fechas en TED, orientación de queries en Tavily, gestión de colisiones de archivos, etc.).
- **Criterio de producto**: todas las decisiones sobre qué incluir, qué posponer y qué descartar son decisiones propias documentadas y justificadas.

**El rol de Claude Code (IA):** implementación del código bajo especificaciones aprobadas previamente. Claude Code escribe el código; el autor decide qué se construye, cómo se estructura y si el resultado es válido.

La metodología utilizada es **Spec-Driven Development (SDD)** del framework LIDR: ninguna línea de código se escribe sin un `requirements.md` y un `design.md` aprobados por el autor. **Esto garantiza que el sistema refleja decisiones deliberadas, no sugerencias automáticas de una IA.**

## Stack

- Python 3.14 + LangChain + LangGraph (orquestación de agentes)
- SQLite (persistencia local, sin dependencias externas)
- Streamlit (interfaz de usuario)
- Fuentes: Tavily · Firecrawl · BDNS · TED (Tenders Electronic Daily)

**Principio rector (definido por el autor):** calidad y verificación cruzada por encima de velocidad. El sistema nunca inventa datos — todo dato es trazable a su fuente.

## Estado actual

Las dos primeras specs están **completas**: módulo investigador (36/36 tareas) e interfaz
Streamlit (33/33 tareas). **202 tests** en verde (unitarios, integración y end-to-end).

### ✅ Módulo investigador — completado y validado en producción

El primer módulo, `src/agente_ong/research/`, está completo:

- **4 fuentes de búsqueda** integradas y verificadas contra sus APIs reales
- **Política de verificación cruzada** con 5 estados (`VERIFIED`, `OFFICIAL_UNCROSSED`, `UNCROSSED_UNVERIFIED`, `CONFLICTING`, `NOT_FOUND`) — diseñada por el autor para reflejar distintos niveles de confianza en los datos
- **Grafo LangGraph** de 7 nodos con arista condicional
- **Persistencia SQLite** entre sesiones (el sistema recuerda lo aprendido)
- **Validado con datos reales**: ~54 convocatorias relevantes encontradas, con verificación cruzada funcionando en producción

```python
from agente_ong.research import Investigador, ResearchConfig, ResearchRequest

with Investigador(ResearchConfig.from_env()) as inv:
    informe = inv.run(ResearchRequest(
        mode="calls",
        query_terms=["cooperación internacional", "agua"],
        search_context="convocatoria subvención ONG 2026"
    ))
```

### ✅ Interfaz Streamlit — completada

La interfaz de usuario, `src/agente_ong/ui/`, está completa y operativa:

- Investigación **asíncrona** (el usuario no espera bloqueado; la app sigue usable)
- Gestión de **múltiples proyectos** por sesión, persistidos entre sesiones
- **Contexto de búsqueda por proyecto**: el usuario describe su organización y ámbito una
  vez al crear el proyecto, y todas sus investigaciones lo heredan
- **Subida de documentos** de la ONG por proyecto (validación de tipo y tamaño)
- Resultados **ordenados por fiabilidad** con filtros (fecha, importe, estado de verificación)
- Control de **profundidad de búsqueda** (rápida / normal / exhaustiva)
- Activación/desactivación de **fuentes individuales** por investigación
- **Descarga del informe** en Markdown, con fuente y estado de verificación por cada dato

### 📋 Pendiente

- Integración de LLM (Claude / OpenAI / Ollama)
- Chat de proyecto: conversar con el LLM sobre los resultados del informe y los documentos del proyecto
- Agente redactor de propuestas (con tono ONG auténtico, diseñado para pasar detectores de IA — decisión de producto del autor)

## Arquitectura

El patrón **Ports & Adapters** fue elegido deliberadamente por el autor para garantizar que el núcleo del sistema no dependa de tecnologías concretas — si mañana SQLite se queda corto o Tavily cambia su API, se cambia el adaptador sin tocar la lógica:

```
ResearchStore (puerto)
├── InMemoryStore   (tests / modo efímero)
└── SqliteStore     (producción — .data/agente_ong.db)

SearchSource (puerto)
├── TavilySource    (búsqueda web general)
├── FirecrawlSource (lectura profunda de páginas)
├── BdnsSource      (fuente oficial ES — API pública)
└── TedSource       (fuente oficial UE — API pública)
```

## Instalación

```bash
git clone https://github.com/Kikesnks/agente-ong.git
cd agente-ong
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
pip install -r requirements.txt
pip install -e .
```

Copia `.env.example` a `.env` y rellena tus claves:

```bash
cp .env.example .env      # macOS/Linux
copy .env.example .env    # Windows
```

```
TAVILY_API_KEY=tvly-...
FIRECRAWL_API_KEY=fc-...
```

BDNS y TED son APIs públicas — no necesitan clave. `.env.example` documenta también el
resto de variables opcionales (límites de la investigación, vocabulario de convocatoria,
rutas de persistencia — ver `ResearchConfig.from_env()` en `research/config.py`).

## Lanzar la interfaz

Con el entorno virtual activado:

```bash
streamlit run src/agente_ong/ui/app.py
```

La app carga `.env` automáticamente al arrancar — no hace falta exportar las variables a
mano en el shell. La base de datos se crea automáticamente en `.data/agente_ong.db`. Sin
claves de API, la búsqueda web (Tavily) y la lectura profunda (Firecrawl) no estarán
operativas, pero las fuentes oficiales (BDNS y TED) funcionan igualmente; la propia app
avisa en la barra lateral si detecta alguna clave opcional ausente.

**Streamlit Community Cloud**: `.env` no se despliega (está en `.gitignore`). Configura
las mismas variables en el panel de la app → *Settings → Secrets*, con el mismo formato
`CLAVE=valor`; la app las copia automáticamente a su entorno al arrancar.