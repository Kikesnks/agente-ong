# Structure Steering — agente-ong

> Organización de archivos, convenciones y patrones. Referenciado por `/spec-tasks` y `/spec-execute`.

## Estado del repositorio

Proyecto en desarrollo activo desde 2026-05. Última actualización de este documento:
04-07-2026 (al cerrar SPEC 2). La estructura siguiente refleja el código real, no una
propuesta. Las carpetas marcadas como "reservada" están planificadas pero no
materializadas todavía; se activarán en su spec correspondiente.

## Estructura de carpetas (actual)

Código materializado a fecha 04-07-2026:

```
ONGs/
├─ .claude/
│  ├─ steering/              # product.md, tech.md, structure.md (este conjunto)
│  └─ specs/                 # una carpeta por spec (integracion-llm, investigador-v2, streamlit)
├─ src/
│  └─ agente_ong/
│     ├─ llm/                # abstracción multi-proveedor de LLM (SPEC 2)
│     │  ├─ adapters/        # adaptadores concretos (Ollama activo; Claude/OpenAI aplazados)
│     │  ├─ prompts/         # prompts editables como .md (patrón "skill")
│     │  ├─ provider.py      # puerto LLMProvider
│     │  ├─ errors.py        # errores propios + reintentos
│     │  ├─ prompt_loader.py # carga de prompts desde .md
│     │  ├─ semantic_filter.py  # classify_result
│     │  └─ filter_report.py    # integración filtro + investigador
│     ├─ research/           # investigación de convocatorias (SPEC investigador + investigador-v2)
│     │  ├─ sources/         # BDNS, TED, Tavily, HttpReader, Firecrawl
│     │  ├─ store/           # persistencia SQLite (puerto + adaptador)
│     │  ├─ collector.py, config.py, depth.py, graph.py, investigador.py,
│     │  │  ledger.py, models.py, textclean.py, triage.py, urlnorm.py,
│     │  │  verification.py
│     └─ ui/                 # interfaz Streamlit (SPEC streamlit)
│        ├─ app.py, jobs.py, models.py, project_store.py,
│        │  report_serde.py, report_view.py, request_builder.py, uploads.py
├─ tests/                    # espeja la estructura de src/
├─ scripts/                  # utilidades de desarrollo (no desplegado en Streamlit Cloud)
├─ Contexto_para_mi/         # documentos de trabajo del desarrollador (gitignored)
├─ RECURSOS/                 # material de trabajo (ver convención abajo)
│  ├─ ENTRENAMIENTO/         # descargados por los agentes (aprendizaje)
│  └─ [nombre_proyecto]/     # material subido por el humano por proyecto
├─ requirements.txt          # dependencias
├─ .env                      # claves de API (NO versionar)
└─ .gitignore
```

## Estructura de carpetas (reservada para specs futuras)

Carpetas planificadas pero no materializadas. Se activarán cuando su spec lo requiera:

- `agents/` — agentes especializados (buscador, redactor, presupuesto). Posible
  materialización cuando la integración LLM se profundice para búsquedas y redacción.
- `graph/` — definición del grafo LangGraph si se separa de `research/graph.py`.
- `tools/` — herramientas reutilizables entre agentes.
- `export/` — generación de PDF/DOCX/PPTX y gráficos (previsto en SPEC 4).

La decisión sobre si estas carpetas se activan tal cual, o si la agrupación por
dominio actual (`research/`, futuros `writer/`, `budget/`) es la definitiva, se
tomará en la spec correspondiente.

## Convención clave: carpeta `RECURSOS/`

Definida por el producto y de cumplimiento obligatorio:

- `RECURSOS/ENTRENAMIENTO/` → archivos que los agentes descargan o copian de internet
  (plantillas, proyectos aprobados, ejemplos) como apoyo y aprendizaje.
- `RECURSOS/[nombre_proyecto]/` → documentación (texto, imagen, audio, vídeo, links…)
  que **sube el humano** desde la interfaz para crear un proyecto concreto.

Cuando la UI recibe un recurso, debe guardarlo en `RECURSOS/[nombre_proyecto]/`.

## Convenciones de código (Python)

- **Nombres:** `snake_case` para módulos, funciones y variables; `PascalCase` para clases.
- **Carpetas/paquetes:** `snake_case`.
- **Un módulo por responsabilidad clara**: cada dominio en su propia carpeta
  (`research/` para investigación de convocatorias; futuros `writer/`, `budget/`).
  Si en el futuro se materializa `agents/`, seguirá la misma norma (un agente por módulo).
- **Integraciones externas desacopladas**: cada fuente externa (Tavily, Firecrawl, BDNS,
  TED, HttpReader) en su propio módulo bajo `research/sources/`.
- **Abstracción de proveedores** centralizada: LLM en `llm/` (puerto `LLMProvider` +
  adaptadores), búsqueda en `research/sources/` (puerto `SearchSource` + adaptadores).
  El resto del código no depende de un proveedor concreto.
- **Configuración por entorno:** leer claves y modelos de variables de entorno; ningún
  secreto en el código ni en el repo.

## Convenciones de proyectos (dominio)

- Cada proyecto de subvención se identifica por `[nombre_proyecto]` y tiene su carpeta en
  `RECURSOS/`.
- El estado de cada proyecto (borrador, en redacción, listo, presentado…) se mantiene en
  la persistencia del producto (**SQLite**, ver `tech.md`) para poder resumirlo a petición
  del usuario. (ENGRAM es herramienta de desarrollo, no parte del producto.)

## Testing

- Pruebas en `tests/`, reflejando la estructura de `src/`.
- Priorizar tests de la lógica de agentes y de la abstracción de proveedores (mockeando
  llamadas externas a LLM y a APIs de búsqueda).

## Notas

- Las decisiones de estructura abiertas (vector store, librerías de export) se cerrarán en
  sus respectivas specs; este documento se actualizará cuando se decidan.
- Convención SDD del proyecto: las specs cerradas pueden reabrirse temporalmente para
  ampliaciones (nuevos requisitos, tareas adicionales) siempre que el motivo, la fecha
  de reapertura y la fecha de nuevo cierre queden documentados en la propia spec y en
  Contexto_para_mi/decisiones_pendientes.md.
