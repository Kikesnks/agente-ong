# Design Document — Agente Investigador

## Overview

El agente investigador es un **módulo Python autocontenido** (`src/agente_ong/research/`,
portable como paquete independiente) que recibe criterios de investigación y devuelve
resultados estructurados con procedencia verificable. Internamente se modela como un
**pequeño grafo de LangGraph** que orquesta un ciclo *planificar → buscar → leer en
profundidad → verificar → decidir si continuar*, apoyado en una capa de **fuentes de
búsqueda intercambiables** (Tavily, Firecrawl, BDNS, TED) detrás de una interfaz común.

Su contrato público no depende de la UI ni de otros agentes del sistema: se invoca con un
objeto de petición y una configuración inyectada (claves de API, rutas, límites), y produce
un informe de investigación con el estado de verificación de cada dato y el registro de
fuentes consultadas. Esto satisface el requisito de portabilidad (Requirement 7).

El **registro de fuentes (`SourceLedger`) es persistente entre investigaciones**: cada
fuente consultada se guarda con un resumen de su contenido útil y su fecha de captura, de
modo que investigaciones futuras reutilicen el conocimiento previo en lugar de empezar de
cero. La persistencia se delega a un puerto (`ResearchStore`), cuyo adaptador `EngramStore`
guarda en ENGRAM — manteniendo el núcleo desacoplado de ENGRAM (portabilidad).

Cubre dos modos de uso sobre el mismo motor:
- **Modo convocatorias** (Requirements 1, 3, 4): localizar y verificar convocatorias.
- **Modo entrenamiento** (Requirement 2): localizar y capturar en local proyectos aprobados.

## Steering Document Alignment

### Technical Standards (tech.md)
- **Multi-proveedor / abstracción de fuentes**: cada fuente (Tavily, Firecrawl, BDNS, TED)
  implementa una interfaz `SearchSource` común; el agente no conoce proveedores concretos
  (tech.md → "Abstracción de proveedores").
- **LangGraph** para el flujo de control del agente y **LangChain** para tools y carga de
  documentos.
- **Calidad sobre velocidad**: el nodo de verificación es de paso obligatorio antes de
  marcar un dato como fiable.
- **Sin secretos en el repo**: toda credencial/ruta llega por `ResearchConfig` inyectada
  desde variables de entorno.
- **Trazabilidad**: todo dato factual lleva su `SourceRef`.
- **ENGRAM como memoria persistente**: integrado vía puerto `ResearchStore`/`EngramStore`,
  sin acoplar el núcleo del módulo.

### Project Structure (structure.md)
- El módulo vive en `src/agente_ong/research/` (subpaquete propio), siguiendo el patrón
  "una responsabilidad por módulo" y "cada integración externa en su propio módulo".
- Las fuentes concretas se ubican en `research/sources/` (equivalente al `search/` de la
  estructura objetivo, encapsulado dentro del módulo portable).
- Los adaptadores de persistencia en `research/store/` (`InMemoryStore`, `EngramStore`).
- Las descargas se guardan **exclusivamente** bajo `RECURSOS/ENTRENAMIENTO/`, ruta recibida
  por configuración y validada (sin path traversal).
- Tests espejo en `tests/research/`.

## Code Reuse Analysis

Proyecto greenfield: no hay código previo que reutilizar. El diseño **establece** los
patrones base (abstracción de fuentes, config inyectada, modelos con procedencia,
persistencia por puerto) que otros agentes del sistema reutilizarán después. Se evita
acoplar nada a este módulo para mantener su portabilidad.

### Existing Components to Leverage
- **Steering docs** (`product.md`, `tech.md`, `structure.md`): fuente de convenciones.
- **ENGRAM** (memoria persistente): el núcleo del módulo NO depende de ENGRAM directamente
  (para ser portable); la persistencia del ledger y del índice de capturas se delega al
  puerto `ResearchStore`. En agente-ong, el adaptador concreto (`EngramStore`) usa ENGRAM.

### Integration Points
- **Sistema de ficheros `RECURSOS/ENTRENAMIENTO/`**: destino de las descargas/copias.
- **APIs externas**: Tavily (REST), Firecrawl (REST), BDNS (API/portal oficial España), TED
  (API oficial UE).
- **ENGRAM** (vía `EngramStore`): persistencia del `SourceLedger` y del índice de capturas.
- **Llamador (otros agentes / UI Streamlit)**: consume `Investigador.run(request)`.

## Architecture

El módulo separa tres capas: **orquestación** (grafo LangGraph), **dominio** (modelos y
políticas de verificación) y **fuentes/persistencia** (adaptadores intercambiables). El
registro de fuentes consultadas (`SourceLedger`) es transversal, **persistente** vía
`ResearchStore`, y evita repeticiones y ciclos a la vez que acumula conocimiento entre
investigaciones.

```mermaid
graph TD
    Caller[Llamador: UI / otros agentes] -->|ResearchRequest + ResearchConfig| Inv[Investigador (fachada)]
    Inv --> Graph[Grafo LangGraph]

    subgraph Grafo
      P[plan] --> RC[recall_ledger]
      RC --> S[search]
      S --> R[read_deep]
      R --> V[verify]
      V -->|faltan datos / mas enlaces| D{continue?}
      D -->|si, dentro de limites| S
      D -->|no| C[compile_report]
      V -->|dato no encontrado| A[ask_user]
      A --> C
    end

    P -. consulta por tematica .-> L
    RC -. carga pistas previas .-> L
    S --> Sources
    R --> Sources
    subgraph Sources[Capa de fuentes - interfaz SearchSource]
      T[TavilySource]
      F[FirecrawlSource]
      B[BdnsSource]
      E[TedSource]
    end

    S -.registra+resume.-> L[(SourceLedger)]
    R -.registra+resume.-> L
    L <-->|persistencia| Store[ResearchStore]
    Store --> Mem[InMemoryStore]
    Store --> Eng[EngramStore -> ENGRAM]
    R -->|descarga aprobados| FS[RECURSOS/ENTRENAMIENTO/]
    C --> Report[ResearchReport]
    Report --> Caller
```

### Patrones de diseño
- **Strategy / Adapter**: `SearchSource` con implementaciones por proveedor.
- **Ports & Adapters**: `ResearchStore` (persistencia) y el destino de descargas son
  puertos; el núcleo no conoce su implementación concreta → portabilidad y ENGRAM desacoplado.
- **Graph/State machine** (LangGraph): control explícito del ciclo de profundización, del
  recall del ledger previo y del corte por límites.
- **Policy object**: `VerificationPolicy` decide el estado de cada dato; incluye la
  política de **revalidación por caducidad**.

### Flujo de recall (reutilización entre investigaciones)
1. `plan` consulta el `SourceLedger` (vía `ResearchStore.find_ledger_by_topic`) por la
   temática.
2. `recall_ledger` carga las `LedgerEntry` previas relevantes como **pistas** (URLs
   conocidas + `content_summary`), priorizando dónde buscar y evitando reconsultas inútiles.
3. Las pistas orientan `search`/`read_deep`, pero **no sustituyen** la verificación de datos
   críticos (ver política de revalidación).

## Components and Interfaces

### Investigador (fachada pública)
- **Purpose:** punto de entrada único y portable del módulo.
- **Interfaces:**
  - `run(request: ResearchRequest) -> ResearchReport`
  - `__init__(config: ResearchConfig, sources: list[SearchSource] | None = None, store: ResearchStore | None = None)`
- **Dependencies:** grafo LangGraph, capa de fuentes, `ResearchStore`, config.
- **Reuses:** —(define el patrón base).

### ResearchGraph (orquestación LangGraph)
- **Purpose:** ejecuta el ciclo plan→recall_ledger→search→read_deep→verify→(loop/ask/compile).
- **Interfaces:** nodos `plan`, `recall_ledger`, `search`, `read_deep`, `verify`,
  `ask_user`, `compile_report`; estado `ResearchState`.
- **Dependencies:** `SearchSource`s, `SourceLedger`, `VerificationPolicy`, `DepthLimiter`.
- **Reuses:** modelos de dominio.

### SearchSource (interfaz de fuente — Strategy)
- **Purpose:** abstraer cualquier proveedor de búsqueda/lectura.
- **Interfaces:**
  - `name: str`, `is_official: bool`
  - `search(query: SearchQuery) -> list[SearchHit]`
  - `fetch(url: str) -> FetchedDocument` (lectura profunda; soportado por Firecrawl y, en su
    caso, fuentes oficiales)
  - `supports(capability)` para declarar si hace `search`, `fetch` o ambas
- **Implementaciones:** `TavilySource` (search general), `FirecrawlSource` (fetch profundo),
  `BdnsSource` (oficial, España; `is_official=True`), `TedSource` (oficial, UE;
  `is_official=True`).
- **Dependencies:** cliente HTTP, claves desde config; rate-limit + retry/backoff.

### SourceLedger (registro de fuentes consultadas — PERSISTENTE)
- **Purpose:** Requirements 5 y 6.2 — registrar consultas/URLs, evitar repeticiones y ciclos,
  y **acumular conocimiento entre investigaciones** mediante persistencia.
- **Persistencia:** se hidrata al inicio (recall por temática) y se vuelca a través de
  `ResearchStore`; no es solo en memoria. La sesión en curso trabaja sobre una vista en
  memoria que se sincroniza con el store.
- **Interfaces:**
  - `mark_queried(key)`, `seen(key) -> bool`
  - `record(key, *, kind, outcome, content_summary, source_ref)` — guarda/actualiza una
    entrada con su resumen y `captured_at`.
  - `find_by_topic(terms) -> list[LedgerEntry]` — recall de pistas previas.
  - `entries() -> list[LedgerEntry]`
  - `flush()` — persiste cambios vía `ResearchStore`.
  - La clave de URL se **normaliza** (esquema, host en minúsculas, orden de query params,
    sin fragmento) para deduplicar equivalentes.
- **Dependencies:** `ResearchStore` (puerto de persistencia).

### VerificationPolicy (política de veracidad/cruce + revalidación)
- **Purpose:** Requirements 3 y 4 — asignar estado de verificación a cada dato y gobernar la
  **revalidación por caducidad**.
- **Interfaces:**
  - `classify(claim: Claim, supporting: list[SourceRef]) -> VerificationStatus`
  - `needs_revalidation(claim: Claim, *, intent: str, now: datetime) -> bool`
- **Reglas de clasificación:**
  - ≥2 fuentes coincidentes → `VERIFIED`.
  - 1 fuente y `source.is_official` → `OFFICIAL_UNCROSSED` (aceptable; se anota la fuente
    oficial concreta).
  - 1 fuente no oficial → `UNCROSSED_UNVERIFIED` (preocupante).
  - 0 fuentes → `NOT_FOUND` (dispara `ask_user`).
  - Fuentes contradictorias → `CONFLICTING` (se reportan ambas, no se elige en silencio).
- **Política de revalidación (nueva):**
  - El `content_summary` persistido del ledger se usa **solo como pista** para localizar
    fuentes ya conocidas, **nunca** como dato definitivo.
  - Para datos **críticos** (`importe`, `plazo` y, en general, los que se vayan a usar en una
    propuesta), si el `intent` es "use_in_proposal", el dato SHALL revalidarse contra la
    fuente actual antes de darse por bueno.
  - `needs_revalidation` devuelve `True` si el `captured_at` de la fuente supera el umbral de
    frescura configurable (`staleness_days`) o si el dato es crítico y proviene únicamente de
    una pista de ledger no reconfirmada en esta investigación. La caducidad se marca como
    `stale` en el `Claim` para que el informe lo refleje.

### DepthLimiter (control de profundidad/coste)
- **Purpose:** Requirements 6.3 y NFR Performance — cortar por profundidad y nº de páginas.
- **Interfaces:** `can_expand(current_depth, pages_fetched) -> bool`; parámetros
  `max_depth`, `max_pages`, `max_queries` desde config.

### TrainingCollector (captura de proyectos aprobados)
- **Purpose:** Requirement 2 — descargar/copiar en local y registrar metadatos.
- **Interfaces:** `collect(doc: FetchedDocument, tags: list[str]) -> StoredResource`.
- **Comportamiento:** si el doc es descargable, guarda el binario en
  `RECURSOS/ENTRENAMIENTO/`; si no, guarda el texto extraído; escribe un sidecar de
  metadatos; si la URL ya está en el índice (`ResearchStore.has_url`), no re-descarga.
- **Dependencies:** ruta base de RECURSOS validada (anti path-traversal), `ResearchStore`
  para el índice de capturas.

### ResearchStore (puerto de persistencia)
- **Purpose:** persistir el `SourceLedger` y el índice de recursos capturados, y permitir
  recall por temática — sin acoplar el núcleo a ENGRAM.
- **Interfaces:**
  - Ledger: `save_ledger_entry(entry)`, `find_ledger_by_topic(terms) -> list[LedgerEntry]`,
    `get_ledger_entry(key) -> LedgerEntry|None`.
  - Capturas: `has_url(url) -> bool`, `add_resource(meta)`, `list_resources()`.
- **Adaptadores:**
  - `InMemoryStore` (por defecto/portátil; recall solo dentro del proceso).
  - `EngramStore` (en agente-ong; persiste ledger y capturas en ENGRAM, habilitando recall
    entre sesiones y proyectos).

## Data Models

### ResearchRequest
```
- mode: "calls" | "training"
- query_terms: list[str]            # tematica / palabras clave
- scope: { country: str|None, eu: bool }   # ambito (Espana / UE / ...)
- filters: { min_amount: float|None, deadline_after: date|None } | None
- intent: "explore" | "use_in_proposal"     # gobierna la revalidacion
- max_depth: int|None               # override de limites por peticion
- max_pages: int|None
```

### SearchQuery / SearchHit / FetchedDocument
```
SearchQuery:
- text: str
- source_hint: str|None             # forzar una fuente concreta si procede
FetchedDocument:
- url: str
- title: str|None
- content_text: str
- raw_bytes: bytes|None             # presente si era descargable
- content_type: str|None
- outbound_links: list[str]         # para profundizacion (Requirement 6)
```

### SourceRef
```
- url: str
- source_name: str                  # tavily | firecrawl | bdns | ted | ...
- is_official: bool
- retrieved_at: datetime
```

### Claim / GrantOpportunity
```
Claim:
- field: str                        # "importe" | "plazo" | "beneficiarios" | ...
- value: str|None                   # None => no encontrado
- status: VerificationStatus
- is_critical: bool                 # importe/plazo/etc. => sujeto a revalidacion
- stale: bool                       # True si supera staleness_days sin reconfirmar
- sources: list[SourceRef]
GrantOpportunity:
- title, organism, amount, deadline, scope, url      # cada uno como Claim
- overall_status: VerificationStatus
```

### VerificationStatus (enum)
```
VERIFIED | OFFICIAL_UNCROSSED | UNCROSSED_UNVERIFIED | CONFLICTING | NOT_FOUND
```
(La caducidad se expresa con el flag `stale` del `Claim`, ortogonal al estado.)

### LedgerEntry (PERSISTENTE)
```
- key: str                          # URL normalizada o hash de la consulta
- kind: "query" | "url"
- outcome: "useful" | "empty" | "error" | "pending"
- content_summary: str              # resumen breve de la informacion util hallada
- topics: list[str]                 # tematicas/etiquetas para recall por tematica
- source_ref: SourceRef|None
- captured_at: datetime             # cuando se obtuvo/actualizo (control de caducidad)
```

### StoredResource
```
- path: str                         # bajo RECURSOS/ENTRENAMIENTO/
- source_url: str
- captured_at: datetime
- tags: list[str]
- mode_of_capture: "download" | "text_copy"
```

### ResearchReport (salida pública)
```
- mode: str
- opportunities: list[GrantOpportunity]   # modo calls
- resources: list[StoredResource]         # modo training
- ledger: list[LedgerEntry]               # fuentes consultadas (Requirement 5.3)
- reused_from_ledger: list[LedgerEntry]    # pistas previas reutilizadas en esta investigacion
- unresolved: list[{ field/topic, reason, help_needed }]   # Requirement 3.1
- failed_sources: list[{ source_name, error }]             # Reliability
```

## Error Handling

### Error Scenarios
1. **Una fuente falla (timeout / HTTP / rate limit):**
   - **Handling:** retry con backoff hasta N intentos; si persiste, se registra en
     `failed_sources` y la investigación continúa con las demás fuentes.
   - **User Impact:** el informe incluye qué fuentes fallaron; no se pierde el resto.

2. **Dato solicitado no encontrado tras agotar fuentes (Requirement 3.1):**
   - **Handling:** nodo `ask_user`; se añade a `unresolved` con `help_needed` claro.
   - **User Impact:** mensaje explícito de qué falta y qué ayuda se necesita (URL, palabra
     clave, acceso a portal).

3. **Fuentes contradictorias (Requirement 3.3):**
   - **Handling:** `VerificationPolicy` marca `CONFLICTING` y adjunta todas las fuentes.
   - **User Impact:** ve la discrepancia y las fuentes, decide.

4. **Dato de fuente oficial única (Requirement 4.4):**
   - **Handling:** estado `OFFICIAL_UNCROSSED`, anotando la fuente oficial concreta.
   - **User Impact:** sabe que es fiable y por qué no se cruzó.

5. **Dato crítico proveniente solo de pista de ledger / caducado (revalidación):**
   - **Handling:** `needs_revalidation` fuerza reconsultar la fuente; si no se reconfirma, se
     marca `stale` y, según el caso, baja de estado o entra en `unresolved`.
   - **User Impact:** nunca se usa en propuesta un importe/plazo viejo sin reconfirmar; ve la
     marca de caducidad.

6. **Intento de escritura fuera de RECURSOS/ENTRENAMIENTO/ (path traversal):**
   - **Handling:** validar/normalizar la ruta destino contra la base; rechazar si escapa.
   - **User Impact:** ninguno; se evita escritura insegura y se registra el descarte.

7. **Límite de profundidad/páginas alcanzado (Requirement 6.3):**
   - **Handling:** `DepthLimiter` corta la expansión; `compile_report` con lo hallado.
   - **User Impact:** informe parcial honesto con nota de que se alcanzó el límite.

8. **Fallo de persistencia del store (p.ej. ENGRAM no disponible):**
   - **Handling:** la investigación continúa sobre la vista en memoria; el `flush` fallido se
     reintenta y, si persiste, se reporta sin abortar resultados.
   - **User Impact:** obtiene resultados; se avisa de que el aprendizaje no se persistió.

## Testing Strategy

### Unit Testing
- `VerificationPolicy.classify`: tabla de casos (2 fuentes, 1 oficial, 1 no oficial, 0,
  contradictorias) → estados esperados, incluyendo `OFFICIAL_UNCROSSED` vs
  `UNCROSSED_UNVERIFIED`.
- `VerificationPolicy.needs_revalidation`: dato crítico con `intent=use_in_proposal`,
  caducidad por `staleness_days`, y pista de ledger no reconfirmada → `True`.
- `SourceLedger`: normalización de URLs y deduplicación; recall por temática
  (`find_by_topic`); persiste y rehidrata vía store fake.
- `DepthLimiter`: corte por `max_depth` / `max_pages` / `max_queries`.
- `TrainingCollector`: descarga vs copia de texto; rechazo de path traversal; no
  re-descarga de URL ya capturada (`has_url`).
- Cada `SearchSource` con cliente HTTP **mockeado** (sin red real).
- `EngramStore` con ENGRAM mockeado: guarda/recupera `LedgerEntry` con `content_summary`,
  `topics` y `captured_at`.

### Integration Testing
- Flujo del grafo con fuentes fake:
  `plan→recall_ledger→search→read_deep→verify→loop→compile`.
- **Recall entre investigaciones:** primera investigación persiste ledger; segunda
  investigación reutiliza pistas (`reused_from_ledger`) y revalida los datos críticos.
- Modo training end-to-end con FS temporal: verifica archivos en `RECURSOS/ENTRENAMIENTO/`
  + sidecar de metadatos + índice en store.
- Escenario de fuente caída: la investigación continúa y reporta `failed_sources`.
- Escenario `not_found` → aparece en `unresolved` con `help_needed`.
- Escenario de caducidad: pista vieja de ledger fuerza revalidación antes de usarse.

### End-to-End Testing
- Petición real opcional (marcada/skippable, gated por claves de API) contra Tavily/Firecrawl
  para una consulta acotada, validando estructura del `ResearchReport`, presencia de
  `SourceRef` en cada dato y poblado del ledger persistente. No se ejecuta en CI por defecto.
