"""Test della guida didattica: struttura delle lezioni, API, indicizzazione RAG."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fusor_sim.app.server import create_app
from fusor_sim.rag import KnowledgeBase

ROOT = Path(__file__).parent.parent
GUIDE = ROOT / "guide"
KNOWLEDGE = ROOT / "knowledge"


def _fake_llm(messages):
    return json.dumps({"reply": "ok", "intents": []})


@pytest.fixture()
def client():
    with TestClient(create_app(llm=_fake_llm)) as c:
        yield c


# ------------------------------------------------------ file delle lezioni


def test_lessons_exist_and_well_formed():
    files = sorted(GUIDE.glob("*.md"))
    assert len(files) == 10
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("# Lezione"), path.name
        meta = next((l for l in lines if l.startswith("**Livello:**")), None)
        assert meta and "Obiettivo:" in meta, path.name


def test_lessons_progress_from_base_to_advanced():
    files = sorted(GUIDE.glob("*.md"))
    first = files[0].read_text(encoding="utf-8")
    last = files[-1].read_text(encoding="utf-8")
    assert "base" in first
    assert "avanzato" in last


def test_lessons_have_clickable_experiments():
    """Ogni lezione ha almeno un prompt eseguibile (blockquote 💬)."""
    for path in sorted(GUIDE.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "> 💬" in text, f"{path.name} non ha esperimenti cliccabili"


# ----------------------------------------------------------------- API


def test_guide_index_endpoint(client):
    lessons = client.get("/api/guide").json()["lessons"]
    assert len(lessons) == 10
    assert lessons[0]["id"] == "00_perche_la_fusione"
    assert [l["id"] for l in lessons] == sorted(l["id"] for l in lessons)
    levels = {l["level"] for l in lessons}
    assert levels == {"base", "intermedio", "avanzato"}
    assert all(l["title"] and l["objective"] for l in lessons)


def test_guide_lesson_endpoint(client):
    data = client.get("/api/guide/04_la_griglia").json()
    assert data["markdown"].startswith("# Lezione 4")


def test_guide_unknown_lesson_404(client):
    assert client.get("/api/guide/99_inventata").status_code == 404
    # niente path traversal: id non in indice -> 404
    assert client.get("/api/guide/..%2Fpyproject").status_code in (404, 422)


# ------------------------------------------------------------------ RAG


def test_rag_indexes_guide_too():
    kb = KnowledgeBase([KNOWLEDGE, GUIDE])
    hits = kb.search("come fanno i tokamak a confinare il plasma senza griglia?")
    sources = {h.source for h in hits}
    assert sources & {"08_oltre_il_fusore", "lawson"}


def test_rag_finds_numerical_honesty_lesson():
    kb = KnowledgeBase([KNOWLEDGE, GUIDE])
    hits = kb.search("quando fidarsi di una simulazione, conservazione energia CFL")
    assert hits[0].source == "07_onesta_numerica"
