from fastapi import FastAPI

app = FastAPI(title="math-checker-svc")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/readyz")
def readyz():
    return {"status": "ready"}

@app.get("/")
def root():
    return {"service": "math-checker-svc"}