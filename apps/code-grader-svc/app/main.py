from fastapi import FastAPI

app = FastAPI(title="code-grader-svc")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/readyz")
def readyz():
    return {"status": "ready"}

@app.get("/")
def root():
    return {"service": "code-grader-svc"}