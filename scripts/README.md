# scripts/

Scripts manuales, fuera de la suite automatizada y fuera del alcance de cualquier spec.

## `prueba_filtro_semantico.py`

Lanza una investigación real (modo "calls") con los términos y el contexto del
diagnóstico del 12-06/28-06-2026, y clasifica los resultados con el filtro semántico
(SPEC 2) usando Ollama local, para juzgar a ojo la calidad del prompt antes de decidir si
merece la pena afinarlo.

**Cómo lanzarlo:**

El script NO carga `.env` (ningún código de `src/` lo hace tampoco — la app real solo lee
variables ya presentes en el entorno del proceso). Si quieres Tavily/Firecrawl activos,
exporta las claves a mano en el mismo shell antes de lanzarlo (PowerShell):

```powershell
$env:TAVILY_API_KEY="..."
$env:FIRECRAWL_API_KEY="..."
python scripts/prueba_filtro_semantico.py
```

Sin exportarlas, el script avisa por consola y sigue igualmente con las fuentes públicas
(BDNS, TED, lector propio).

**Requisitos:**
- Ollama corriendo en local (`http://localhost:11434`) con el modelo `qwen2.5:7b`
  descargado (`ollama pull qwen2.5:7b`).
- Entorno virtual del proyecto activo, con las dependencias instaladas
  (`pip install -r requirements.txt`).
- `TAVILY_API_KEY`/`FIRECRAWL_API_KEY` exportadas en el shell (opcional; BDNS y TED son
  públicas, sin clave).

**Salida:** por consola y en `Informes/prueba_filtro_AAAA-MM-DD_HHMM.md`. `Informes/` ya
está en `.gitignore`: los informes generados no se suben al repo.
