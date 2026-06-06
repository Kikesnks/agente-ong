"""Script de prueba manual del agente investigador con fuentes reales."""
from dotenv import load_dotenv
from agente_ong.research import Investigador, ResearchConfig, ResearchRequest

load_dotenv()

config = ResearchConfig.from_env()

request = ResearchRequest(
    mode="calls",
    query_terms=["cooperación internacional", "agua"],
    intent="explore",
)

print("Lanzando investigación real...")
print(f"Tavily={'✓' if config.tavily_api_key else '✗'}, Firecrawl={'✓' if config.firecrawl_api_key else '✗'}, BDNS=✓, TED=✓")
print("-" * 60)

with Investigador(config) as inv:
    report = inv.run(request)

print(f"\nConvocatorias encontradas: {len(report.opportunities)}")
for opp in report.opportunities:
    print(f"\n  [{opp.title.status.value}] {opp.title.value}")
    print(f"  URL: {opp.url.value}")

print(f"\nNo resuelto ({len(report.unresolved)}):")
for u in report.unresolved:
    print(f"  [{u.topic}] {u.reason}")

print(f"\nFuentes fallidas ({len(report.failed_sources)}):")
for f in report.failed_sources:
    print(f"  {f.source_name}: {f.error}")

print(f"\nFuentes consultadas: {len(report.ledger)}")