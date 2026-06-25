"""Built-in SPARQL template registry (fallback when sparql/templates/*.jinja.rq
are not yet present). Maps each competency-question intent to a Jinja template.

Templates are loaded from ``sparql/templates/<intent>.jinja.rq`` when available;
otherwise the embedded defaults below are used so the demo runs offline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from app.core.config import settings

PREFIXES = (
    "PREFIX hcmo: <http://w3id.org/hcmo#>\n"
    "PREFIX ex: <http://example.org/hcmo/data#>\n"
    "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
    "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
)

# intent -> embedded Jinja template body (slots referenced as {{ slot }})
EMBEDDED_TEMPLATES: Dict[str, str] = {
    "datasets_by_system": PREFIXES + """
SELECT ?dataset ?title ?system ?systemName WHERE {
  ?exp a hcmo:HomeCageExperiment ;
       hcmo:usesSystem ?system ;
       hcmo:hasDataset ?dataset .
  ?dataset hcmo:title ?title .
  OPTIONAL { ?system hcmo:systemName ?systemName . }
  {% if system_name %}
  FILTER(CONTAINS(LCASE(STR(?system)), "{{ system_name }}")
         || (BOUND(?systemName) && CONTAINS(LCASE(STR(?systemName)), "{{ system_name }}")))
  {% endif %}
}
LIMIT {{ limit | default(200) }}
""",
    "metrics_for_experiment": PREFIXES + """
SELECT ?experiment ?expLabel ?metric ?metricName WHERE {
  ?experiment a hcmo:HomeCageExperiment ;
              hcmo:measuresMetric ?metric .
  OPTIONAL { ?experiment rdfs:label ?expLabel . }
  OPTIONAL { ?metric hcmo:metricName ?metricName . }
  {% if dataset %}
  ?ds a hcmo:Dataset ; hcmo:hasExperiment ?experiment .
  OPTIONAL { ?ds hcmo:identifier ?dsId . }
  OPTIONAL { ?ds hcmo:title ?dsTitle . }
  OPTIONAL { ?ds rdfs:label ?dsLabel . }
  FILTER(
    CONTAINS(LCASE(STR(?ds)), "{{ dataset | lower }}")
    || (BOUND(?dsId) && CONTAINS(LCASE(STR(?dsId)), "{{ dataset | lower }}"))
    || (BOUND(?dsTitle) && CONTAINS(LCASE(STR(?dsTitle)), "{{ dataset | lower }}"))
    || (BOUND(?dsLabel) && CONTAINS(LCASE(STR(?dsLabel)), "{{ dataset | lower }}"))
  )
  {% endif %}
  {% if metric %}
  FILTER(CONTAINS(LCASE(STR(?metric)), "{{ metric }}")
         || (BOUND(?metricName) && CONTAINS(LCASE(STR(?metricName)), "{{ metric }}")))
  {% endif %}
  {% if phrase %}
  FILTER(BOUND(?expLabel) && CONTAINS(LCASE(STR(?expLabel)), "{{ phrase | lower }}"))
  {% endif %}
}
LIMIT {{ limit | default(200) }}
""",
    "experiments_by_species": PREFIXES + """
SELECT ?experiment ?expLabel ?cohort ?species ?strain WHERE {
  ?experiment a hcmo:HomeCageExperiment ;
              hcmo:hasCohort ?cohort .
  OPTIONAL { ?experiment rdfs:label ?expLabel . }
  OPTIONAL { ?cohort hcmo:species ?species . }
  OPTIONAL { ?cohort hcmo:strain ?strain . }
  {% if species %}
  FILTER(BOUND(?species) && CONTAINS(LCASE(STR(?species)), "{{ species }}"))
  {% endif %}
  {% if strain %}
  FILTER(BOUND(?strain) && CONTAINS(LCASE(STR(?strain)), "{{ strain }}"))
  {% endif %}
}
LIMIT {{ limit | default(200) }}
""",
    "vcg_readiness": PREFIXES + """
SELECT ?dataset ?title ?identifier WHERE {
  ?dataset a hcmo:Dataset .
  OPTIONAL { ?dataset hcmo:title ?title . }
  OPTIONAL { ?dataset hcmo:identifier ?identifier . }
}
ORDER BY ?dataset
LIMIT {{ limit | default(200) }}
""",
    "systems_overview": PREFIXES + """
SELECT ?system ?systemName ?vendor WHERE {
  ?system a hcmo:HomeCageSystem .
  OPTIONAL { ?system hcmo:systemName ?systemName . }
  OPTIONAL { ?system hcmo:vendor ?vendor . }
}
ORDER BY ?system
LIMIT {{ limit | default(200) }}
""",
    "other": PREFIXES + """
SELECT ?s ?type ?label WHERE {
  ?s a ?type .
  FILTER(STRSTARTS(STR(?type), "http://w3id.org/hcmo#"))
  OPTIONAL { ?s rdfs:label ?label . }
}
LIMIT {{ limit | default(50) }}
""",
}


def template_name_for_intent(intent: str) -> str:
    """Map an intent to its template name."""
    return intent if intent in EMBEDDED_TEMPLATES else "other"


def load_template_source(
    intent: str,
    templates_dir: Optional[Path] = None,
    prefer_files: bool = False,
) -> str:
    """Return the Jinja template source for an intent.

    By default the embedded templates win, because their slot contract is the
    one produced by this backend's slot extractor (the on-disk
    ``sparql/templates/*.jinja.rq`` files are authored independently and may use
    a different slot vocabulary). Set ``prefer_files=True`` to use the on-disk
    file for ``<intent>.jinja.rq`` when present.
    """
    name = template_name_for_intent(intent)
    if prefer_files:
        tdir = Path(templates_dir or settings.sparql_templates_dir)
        candidate = tdir / f"{name}.jinja.rq"
        if candidate.exists():
            try:
                return candidate.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
    return EMBEDDED_TEMPLATES[name]
