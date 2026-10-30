"""Ghost Charges: a local web page that finds the subscriptions haunting your bank statement.

The statement is read in memory and never written to disk. Nothing is sent anywhere except the merchant
descriptions, to the model endpoint you configure, which by default is Gemma in Ollama on this machine."""

from __future__ import annotations

from pathlib import Path

from datetime import date
from decimal import Decimal

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, JSONResponse

from . import letters, names, service, statement

STATIC = Path(__file__).parent / "static"
DEMO = Path(__file__).parent.parent / "demo" / "statement.csv"
MAX_BYTES = 5 * 1024 * 1024

app = FastAPI(title="Ghost Charges", docs_url=None, redoc_url=None)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/config")
def config():
    return {"model": names.model_label() if names.enabled() else None, "local": names.runs_locally(),
            "demo": DEMO.exists()}


def _run(data: bytes, use_model: bool, died: date | None = None):
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "That file is larger than 5 MB: export a shorter period.")
    try:
        return JSONResponse(service.analyse(data, use_model, died))
    except statement.StatementError as e:
        raise HTTPException(422, str(e))


@app.post("/api/analyse")
async def analyse(file: UploadFile = File(...), model: bool = True, died: date | None = None):
    return _run(await file.read(), model, died)


@app.post("/api/demo")
def demo(model: bool = True, died: date | None = None):
    if not DEMO.exists():
        raise HTTPException(404, "No demo statement on this server.")
    return _run(DEMO.read_bytes(), model, died)


class Charge(BaseModel):
    day: date
    amount: Decimal


class LetterRequest(BaseModel):
    merchant: str = Field(min_length=1, max_length=80)
    holder: str = Field(min_length=1, max_length=80)
    died: date
    sender: str = Field("", max_length=80)
    relation: str = Field("", max_length=40)
    language: str = "en"
    charges: list[Charge] = Field(default_factory=list, max_length=200)


@app.post("/api/letter")
def letter(req: LetterRequest):
    return letters.write(req.merchant, req.holder, req.died, [(c.day, c.amount) for c in req.charges],
                         req.sender, req.relation, req.language)
