"""Household inventory API. SQLite is the sole authority for package counts."""
import json
import logging
import os
import sqlite3
import time

from app.lookup import fetch_product
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("stoneinventory")
Barcode = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9]{8,14}$")]
Count = Annotated[int, Field(strict=True, ge=0, le=1000000)]


@contextmanager
def database():
    path = Path(os.environ.get("DATABASE_PATH", "data/inventory.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
    finally:
        if con.in_transaction:
            con.rollback()
        con.close()


def initialize():
    with database() as db:
        db.execute("PRAGMA journal_mode=WAL")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, 2):
            raise RuntimeError("Unsupported database schema version")
        if version == 0:
            db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE products (
                    barcode TEXT PRIMARY KEY, name TEXT, brand TEXT, package_size TEXT,
                    category TEXT, image_url TEXT, ingredients TEXT,
                    allergens TEXT, dietary_labels TEXT,
                    serving_size TEXT, servings_per_package REAL,
                    nutrition_json TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'manual', source_product_id TEXT,
                    source_payload_json TEXT NOT NULL DEFAULT '{}', source_fetched_at TEXT,
                    manually_verified INTEGER NOT NULL DEFAULT 0,
                    unresolved INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE inventory (
                    barcode TEXT PRIMARY KEY REFERENCES products(barcode),
                    quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity BETWEEN 0 AND 1000000),
                    minimum_quantity INTEGER NOT NULL DEFAULT 0 CHECK(minimum_quantity>=0),
                    target_quantity INTEGER NOT NULL DEFAULT 0 CHECK(target_quantity>=0),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE transactions (
                    id INTEGER PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                    barcode TEXT NOT NULL REFERENCES products(barcode),
                    action TEXT NOT NULL CHECK(action IN ('ADD','REMOVE','RECONCILE')),
                    quantity_before INTEGER NOT NULL, quantity_after INTEGER NOT NULL,
                    delta INTEGER NOT NULL, device_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE INDEX transactions_barcode ON transactions(barcode,id);
                CREATE TABLE requests (
                    request_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    status_code INTEGER NOT NULL, response TEXT NOT NULL
                );
                PRAGMA user_version=1;
                COMMIT;
            """)
        if version < 2:
            db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE product_lookups (
                    barcode TEXT PRIMARY KEY REFERENCES products(barcode),
                    outcome TEXT NOT NULL,
                    next_attempt_at REAL NOT NULL,
                    attempted_at REAL NOT NULL
                );
                CREATE TABLE lookup_budget (
                    id INTEGER PRIMARY KEY CHECK(id=1), next_attempt_at REAL NOT NULL
                );
                INSERT INTO lookup_budget VALUES(1,0);
                PRAGMA user_version=2;
                COMMIT;
            """)
    log.info('event=database_ready schema=2')


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="StoneInventory", version="0.3.0", lifespan=lifespan)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Operation(StrictModel):
    request_id: UUID
    barcode: Barcode
    device_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")


class Scan(Operation):
    action: Literal["add", "remove"]
    quantity: Annotated[int, Field(strict=True, ge=1, le=1000000)] = 1


class Reconcile(Operation):
    quantity: Count
    expected_quantity: Count | None = None


class Nutrients(StrictModel):
    """Values are per the stated basis. Unknown values remain null, never zero."""
    basis: Literal["per_100g", "per_100ml", "per_serving", "per_100g_or_100ml"]
    calories_kcal: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    protein_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    carbohydrates_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    fat_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    fiber_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    sugars_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    sodium_mg: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class Product(StrictModel):
    name: str = Field(min_length=1, max_length=300, pattern=r"\S")
    brand: str | None = Field(default=None, max_length=200)
    package_size: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    ingredients: str | None = Field(default=None, max_length=10000)
    allergens: str | None = Field(default=None, max_length=2000)
    dietary_labels: str | None = Field(default=None, max_length=2000)
    serving_size: str | None = Field(default=None, max_length=100)
    servings_per_package: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    nutrition: Nutrients | None = None
    minimum_quantity: Count = 0
    target_quantity: Count = 0


def product_view(db, barcode):
    row = db.execute("SELECT p.*, i.quantity, i.minimum_quantity, i.target_quantity FROM products p JOIN inventory i USING(barcode) WHERE barcode=?", (barcode,)).fetchone()
    if row is None:
        raise HTTPException(404, "Product not found")
    result = dict(row)
    result["nutrition"] = json.loads(result.pop("nutrition_json"))
    result["source_payload"] = json.loads(result.pop("source_payload_json"))
    result["unresolved"] = bool(result["unresolved"])
    result["manually_verified"] = bool(result["manually_verified"])
    return result


@app.exception_handler(sqlite3.Error)
async def database_error(request, exc):
    log.error("event=database_failure type=%s", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable; retry using the same request_id"})


@app.get("/api/health")
def health():
    with database() as db:
        db.execute("SELECT 1 FROM inventory LIMIT 1")
    return {"status": "ok", "database": "ok"}


@app.get("/api/products/{barcode}")
def get_product(barcode: Barcode):
    with database() as db:
        return product_view(db, barcode)


@app.get("/api/products")
def products(unresolved: bool = False):
    with database() as db:
        rows = db.execute("SELECT barcode FROM products WHERE (?=0 OR unresolved=1) ORDER BY barcode", (int(unresolved),)).fetchall()
        return [product_view(db, row[0]) for row in rows]


@app.put("/api/products/{barcode}")
def identify_product(barcode: Barcode, product: Product):
    values = product.model_dump(exclude={"nutrition", "minimum_quantity", "target_quantity"})
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO products(barcode) VALUES(?)", (barcode,))
        db.execute("INSERT OR IGNORE INTO inventory(barcode) VALUES(?)", (barcode,))
        assignments = ', '.join(f'{key}=?' for key in values)
        db.execute(f"UPDATE products SET {assignments}, nutrition_json=?, unresolved=0, manually_verified=1, source='manual', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE barcode=?", (*values.values(), json.dumps(product.nutrition.model_dump() if product.nutrition else {}), barcode))
        db.execute("UPDATE inventory SET minimum_quantity=?, target_quantity=? WHERE barcode=?", (product.minimum_quantity, product.target_quantity, barcode))
        result = product_view(db, barcode)
        db.commit()
    log.info("event=product_identified barcode=%s", barcode)
    return result


def resolve_product(barcode):
    """Reserve lookup briefly, release DB lock for network, protect manual edits."""
    now = time.time()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO products(barcode) VALUES(?)", (barcode,))
        db.execute("INSERT OR IGNORE INTO inventory(barcode) VALUES(?)", (barcode,))
        product = product_view(db, barcode)
        if not product["unresolved"] or product["manually_verified"]:
            return {"lookup": "cached", "product": product}
        attempt = db.execute("SELECT * FROM product_lookups WHERE barcode=?", (barcode,)).fetchone()
        if attempt and attempt["next_attempt_at"] > now:
            return {"lookup": attempt["outcome"], "product": product}
        if os.environ.get("LOOKUP_ENABLED", "1") != "1":
            db.commit()
            return {"lookup": "disabled", "product": product}
        budget = db.execute("SELECT next_attempt_at FROM lookup_budget WHERE id=1").fetchone()[0]
        if budget > now:
            db.commit()
            return {"lookup": "deferred", "product": product}
        # At most 12 product requests/minute in this single authoritative database.
        db.execute("UPDATE lookup_budget SET next_attempt_at=? WHERE id=1", (now + 5,))
        db.execute("INSERT INTO product_lookups VALUES(?,?,?,?) ON CONFLICT(barcode) DO UPDATE SET outcome=excluded.outcome,next_attempt_at=excluded.next_attempt_at,attempted_at=excluded.attempted_at",
                   (barcode, "pending", now + 60, now))
        db.commit()
    outcome, fields = fetch_product(barcode)
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        if fields:
            assignments = ", ".join(f"{key}=?" for key in fields)
            db.execute(f"UPDATE products SET {assignments}, source='openfoodfacts', source_fetched_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'), unresolved=0 WHERE barcode=? AND unresolved=1 AND manually_verified=0",
                       (*fields.values(), barcode))
        db.execute("UPDATE product_lookups SET outcome=?,next_attempt_at=? WHERE barcode=?",
                   (outcome, time.time() + (86400 if outcome in ("not_found", "incomplete") else 60), barcode))
        product = product_view(db, barcode)
        db.commit()
    log.info("event=product_lookup barcode=%s outcome=%s source=openfoodfacts", barcode, outcome)
    return {"lookup": outcome, "product": product}


@app.post("/api/products/{barcode}/resolve")
def resolve(barcode: Barcode):
    return resolve_product(barcode)


def operate(operation, action):
    payload = json.dumps({**operation.model_dump(mode="json", exclude_none=True), "operation": action}, sort_keys=True)
    request_id = str(operation.request_id)
    # Avoid external calls on replay. Recheck under the writer lock after enrichment.
    with database() as db:
        prior = db.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
        if prior:
            if prior["payload"] != payload:
                raise HTTPException(409, "request_id was already used for a different operation")
            return JSONResponse(status_code=prior["status_code"], content=json.loads(prior["response"]))
    if action == "ADD":
        resolve_product(operation.barcode)
    with database() as db:
        # The writer lock covers deduplication, inventory, audit log, and saved response.
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
        if prior:
            if prior["payload"] != payload:
                raise HTTPException(409, "request_id was already used for a different operation")
            return JSONResponse(status_code=prior["status_code"], content=json.loads(prior["response"]))
        db.execute("INSERT OR IGNORE INTO products(barcode) VALUES(?)", (operation.barcode,))
        db.execute("INSERT OR IGNORE INTO inventory(barcode) VALUES(?)", (operation.barcode,))
        product = product_view(db, operation.barcode)
        before = product["quantity"]
        after = operation.quantity if action == "RECONCILE" else before + (operation.quantity if action == "ADD" else -operation.quantity)
        status = 200
        if action == "RECONCILE" and operation.expected_quantity is not None and before != operation.expected_quantity:
            status = 409
            result = {"status": "error", "detail": "Count changed since you opened this item. Review the current count and try again.", "inventory": {"before": before, "after": before}}
        elif after < 0 or after > 1000000:
            status = 409
            result = {"status": "error", "detail": "Insufficient inventory" if after < 0 else "Quantity limit exceeded", "inventory": {"before": before, "after": before}}
        else:
            db.execute("UPDATE inventory SET quantity=?, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE barcode=?", (after, operation.barcode))
            cur = db.execute("INSERT INTO transactions(request_id,barcode,action,quantity_before,quantity_after,delta,device_id) VALUES(?,?,?,?,?,?,?)", (request_id, operation.barcode, action, before, after, after-before, operation.device_id))
            product["quantity"] = after
            result = {"status": "success", "request_id": request_id, "transaction_id": cur.lastrowid, "product": product, "inventory": {"before": before, "after": after}}
        db.execute("INSERT INTO requests VALUES(?,?,?,?)", (request_id, payload, status, json.dumps(result)))
        db.commit()
    log.info("event=inventory_operation action=%s barcode=%s request_id=%s status=%s", action, operation.barcode, request_id, status)
    return JSONResponse(status_code=status, content=result)


@app.post("/api/scan")
def scan(operation: Scan):
    return operate(operation, operation.action.upper())


@app.post("/api/inventory/reconcile")
def reconcile(operation: Reconcile):
    return operate(operation, "RECONCILE")


@app.get("/api/products/{barcode}/transactions")
def history(barcode: Barcode):
    with database() as db:
        return [dict(row) for row in db.execute("SELECT * FROM transactions WHERE barcode=? ORDER BY id", (barcode,))]


STATIC = Path(__file__).parent / "static"
app.mount("/assets", StaticFiles(directory=STATIC), name="assets")


@app.get("/", include_in_schema=False)
def web_home():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.middleware("http")
async def browser_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-cache"
    return response
