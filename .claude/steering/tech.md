# Technology Steering — agente-ong

> Stack, herramientas y decisiones técnicas. Referenciado por `/spec-design` y `/spec-execute`.

## Lenguaje y runtime

- **Python** (lenguaje principal). Objetivo: 3.11+.
- Gestión de dependencias vía `requirements.txt` (o `pyproject.toml` si se decide más adelante).

## Orquestación de agentes

- **LangGraph** para definir el grafo multi-agente (estados, transiciones, control de flujo).
- **LangChain** para componentes de apoyo (prompts, herramientas/tools, cargadores de
  documentos, integraciones de modelos).
- Arquitectura **multi-agente**: agentes especializados que colaboran (p.ej. buscador de
  convocatorias, analista/recomendador, redactor, revisor de presupuesto, generador de
  material visual, exportador). El diseño concreto del grafo se definirá por spec.

## Modelos LLM

- **Multi-proveedor.** El código abstrae el proveedor para poder alternar entre
  **Claude (Anthropic)**, **OpenAI** y otros sin reescribir la lógica de agentes.
- Configurar el proveedor/modelo mediante variables de entorno; nunca hardcodear claves.
- Por defecto, usar el modelo más capaz disponible para tareas de redacción larga y
  estructurada.

## Búsqueda e ingesta de información

> Prioridad: **calidad y verificación cruzada sobre velocidad.**

- **Tavily** — búsqueda web general orientada a agentes (resultados limpios).
- **Firecrawl** — lectura/scraping profundo de páginas web concretas.
- **Fuentes oficiales** — integrar de forma específica:
  - **BDNS** (Base de Datos Nacional de Subvenciones, España).
  - **TED** (Tenders Electronic Daily, Unión Europea).
- Verificación cruzada entre fuentes antes de presentar una convocatoria como válida.
- El material de referencia descargado se guarda en local (ver `structure.md`).

## Persistencia / memoria del producto

- **SQLite** (módulo `sqlite3` de la stdlib de Python, sin dependencias externas) es la
  **persistencia real del producto**: guarda el estado entre sesiones (registro de fuentes
  consultadas, índice de material capturado, proyectos y su estado, aprendizaje). Viaja con
  la app en un archivo `.db`, sin servicios externos que el cliente deba instalar.
- La persistencia se expone tras un **puerto** (p. ej. `ResearchStore` en el módulo
  investigador), de modo que el adaptador concreto (SQLite) sea sustituible sin acoplar el
  núcleo.

> **ENGRAM NO es parte del producto.** ENGRAM es una **herramienta de desarrollo** (memoria
> de Claude Code entre sesiones del equipo, vía su plugin). El cliente final no instala ni
> usa ENGRAM. Motivo: requiere su runtime propio (`engram serve` / binario) y está diseñado
> para memorias de agente en prosa, no para almacenamiento estructurado de la app.

## Interfaz de usuario

- **Streamlit** — interfaz web. Soporta subida de archivos, interacción en lenguaje
  natural, visualización de respuestas y descarga de entregables con poco código.

## Generación de entregables

- Exportación a **PDF, presentación y DOCX** (y otros formatos según necesidad).
- Generación de **gráficos y material audiovisual simple** de apoyo a las propuestas.
- Las librerías concretas (p.ej. python-docx, python-pptx, reportlab/weasyprint,
  matplotlib) se elegirán por spec al implementar la exportación.

## Restricciones y convenciones técnicas

- **Sin secretos en el repo.** Claves de API (Anthropic, OpenAI, Tavily, Firecrawl…) solo
  por variables de entorno / `.env` (ignorado por git).
- **Abstracción de proveedores** para LLM y para fuentes de búsqueda: facilitar el cambio
  o la adición de nuevos.
- Priorizar trazabilidad: las afirmaciones y datos de una propuesta deben poder rastrearse
  a su fuente.

## Decisiones pendientes (a resolver por spec)

- Diseño exacto del grafo de agentes en LangGraph.
- Estrategia de almacenamiento/indexado del material de `RECURSOS/` (¿vector store? ¿cuál?).
- Librerías concretas de exportación y de generación de gráficos.
