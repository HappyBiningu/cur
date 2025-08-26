from fastapi import FastAPI

app = FastAPI(title="nlp-essay-grader-svc")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/readyz")
def readyz():
    return {"status": "ready"}

@app.get("/")
def root():
    return {"service": "nlp-essay-grader-svc"}