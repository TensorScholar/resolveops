import json
from pathlib import Path

from resolveops.domain.models import (
    AnalysisResult,
    CustomerProfile,
    KnowledgeArticle,
    Outcome,
    Ticket,
)

MODELS = [Ticket, CustomerProfile, KnowledgeArticle, AnalysisResult, Outcome]
target = Path("schemas")
target.mkdir(exist_ok=True)
for model in MODELS:
    path = target / f"{model.__name__}.schema.json"
    path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n")
    print(path)
