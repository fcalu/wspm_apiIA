# WSPM API

Backend base en FastAPI para consumir datos de ESPN (no oficial) y alimentar modelos WSPM.

## Cómo correr localmente

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Luego entra a:

- http://localhost:8000/
- http://localhost:8000/docs
```

