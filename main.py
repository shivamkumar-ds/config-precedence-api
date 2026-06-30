import os
from pathlib import Path

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
ENVIRONMENT = "development"

DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

VALID_KEYS = {"port", "workers", "debug", "log_level", "api_key"}


def normalize_key(raw_key: str):
    """Map a raw key (from yaml/.env/OS env/CLI) to one of our canonical config keys."""
    k = raw_key.strip()
    upper = k.upper()
    if upper in ("NUM_WORKERS", "NUMWORKERS"):
        return "workers"
    if upper.startswith("APP_"):
        upper = upper[4:]
    candidate = upper.lower()
    if candidate in VALID_KEYS:
        return candidate
    return None


def coerce_value(key: str, value):
    if key in ("port", "workers"):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if key == "debug":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    return str(value)


def load_yaml_layer():
    path = BASE_DIR / f"config.{ENVIRONMENT}.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    result = {}
    for k, v in data.items():
        norm = normalize_key(str(k))
        if norm:
            result[norm] = v
    return result


def load_dotenv_layer():
    path = BASE_DIR / ".env"
    if not path.exists():
        return {}
    values = dotenv_values(path)
    result = {}
    for k, v in values.items():
        if v is None:
            continue
        norm = normalize_key(k)
        if norm:
            result[norm] = v
    return result


def load_os_env_layer():
    result = {}
    for k, v in os.environ.items():
        if k.upper().startswith("APP_"):
            norm = normalize_key(k)
            if norm:
                result[norm] = v
    return result


@app.get("/effective-config")
async def effective_config(request: Request):
    config = dict(DEFAULTS)
    config.update(load_yaml_layer())
    config.update(load_dotenv_layer())
    config.update(load_os_env_layer())

    # Highest precedence: CLI-style overrides via ?set=key=value (repeatable)
    for item in request.query_params.getlist("set"):
        if "=" not in item:
            continue
        raw_key, raw_value = item.split("=", 1)
        norm = normalize_key(raw_key)
        if norm:
            config[norm] = raw_value

    final = {}
    for key in ("port", "workers", "debug", "log_level", "api_key"):
        final[key] = coerce_value(key, config.get(key, DEFAULTS[key]))

    final["api_key"] = "****"
    return final


@app.get("/")
async def root():
    return {"status": "ok"}
