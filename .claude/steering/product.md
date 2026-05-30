# Product Steering — agente-ong

> Documento de visión de producto. Referenciado por todos los comandos `/spec-*`.

## Visión

**agente-ong** es una aplicación multi-agente de IA que ayuda a las ONGs a **encontrar
convocatorias de subvención y redactar propuestas de proyecto profesionales** con el
objetivo de maximizar la financiación obtenida.

## Problema que resuelve

Las ONGs disponen de recursos y tiempo limitados para una tarea altamente especializada:
localizar convocatorias (públicas y privadas) adecuadas a su misión y redactar propuestas
competitivas. Este proceso es lento, requiere experiencia en redacción técnica y de
presupuestos, y muchas oportunidades se pierden por falta de capacidad.

## Usuarios

- **Primarios:** personal de ONGs (técnicos de proyectos, responsables de captación de
  fondos) **sin perfil técnico**. La herramienta debe ser usable desde una interfaz web
  sencilla.
- El usuario sube documentación de su organización y de cada proyecto, pide acciones en
  lenguaje natural y descarga los entregables.

## Funcionalidades clave

1. **Búsqueda de oportunidades** — localizar convocatorias públicas o privadas relevantes.
2. **Recomendación de convocatorias** — informe que pondera cuantía económica, dificultad
   de ejecución y probabilidad de éxito, ordenando las mejores opciones.
3. **Redacción íntegra del proyecto** — propuesta profesional que responde a:
   *problemática-solución, qué, cómo, cuándo, dónde, por qué y coste*.
   La **sección de presupuesto es crítica** y debe quedar impecable.
4. **Aprendizaje desde ejemplos** — descargar/copiar plantillas y proyectos aprobados
   como material de referencia para mejorar la redacción.
5. **Material audiovisual simple** — generar gráficos y presentaciones de apoyo a la
   propuesta cuando sea necesario.
6. **Exportación** — descargar los entregables en varios formatos (PDF, presentación,
   DOCX, etc.).
7. **Memoria persistente** — recordar proyectos, estado, preferencias y aprendizaje
   entre sesiones (vía ENGRAM).

## Interacciones tipo (interfaz web)

- "Redacta el proyecto X para presentar a la convocatoria/institución Y".
- "Hazme un resumen de los proyectos que tenemos y su estado".
- Subir recursos para un proyecto; visualizar respuestas de la IA; descargar resultados.

## Principios de producto

- **Calidad y verificación cruzada por encima de velocidad.** Es preferible una propuesta
  bien fundamentada y con datos verificados que una respuesta rápida.
- **Accesible para no técnicos.** La complejidad multi-agente queda oculta tras una UI
  sencilla.
- **El humano decide.** La IA propone, recomienda y redacta; la persona revisa y aprueba.

## Métricas de éxito (orientativas)

- Propuestas redactadas que el usuario considera "listas para presentar" con mínima edición.
- Convocatorias relevantes encontradas por petición.
- Tiempo ahorrado frente a la redacción manual.
