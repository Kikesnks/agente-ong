# Structure Steering — agente-ong

> Organización de archivos, convenciones y patrones. Referenciado por `/spec-tasks` y `/spec-execute`.

## Estado del repositorio

Proyecto **greenfield** (sin código aún). La estructura siguiente es la propuesta objetivo;
se irá materializando por specs.

## Estructura de carpetas (propuesta)

```
ONGs/
├─ .claude/
│  └─ steering/              # product.md, tech.md, structure.md (este conjunto)
├─ src/                      # código de la aplicación
│  └─ agente_ong/
│     ├─ agents/             # agentes especializados (buscador, redactor, presupuesto…)
│     ├─ graph/              # definición del grafo LangGraph (estados, nodos, aristas)
│     ├─ tools/              # herramientas/tools (búsqueda, scraping, fuentes oficiales)
│     ├─ llm/                # abstracción multi-proveedor de LLM
│     ├─ search/             # integraciones Tavily, Firecrawl, BDNS, TED
│     ├─ store/              # persistencia SQLite (puerto + adaptadores)
│     ├─ export/             # generación de PDF/DOCX/PPTX y gráficos
│     └─ ui/                 # interfaz Streamlit
├─ RECURSOS/                 # material de trabajo (ver convención abajo)
│  ├─ ENTRENAMIENTO/         # archivos descargados/copiados de internet (aprendizaje)
│  └─ [nombre_proyecto]/     # documentación que sube el humano por cada proyecto
├─ tests/                    # pruebas
├─ requirements.txt          # dependencias
├─ .env                      # claves de API (NO versionar)
└─ .gitignore
```

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
- **Un agente por módulo** dentro de `agents/`, con responsabilidad única y clara.
- **Tools** desacopladas y reutilizables; cada integración externa (Tavily, Firecrawl,
  BDNS, TED) en su propio módulo bajo `search/`.
- **Abstracción de proveedores** centralizada (LLM en `llm/`, búsqueda en `search/`): el
  resto del código no debe depender de un proveedor concreto.
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
