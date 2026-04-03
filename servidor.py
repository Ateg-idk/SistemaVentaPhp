"""
AutoService Pro — Servidor Backend
Railway (FastAPI + Uvicorn) — v4.0 SQLite

NUEVO en v4.0:
  - SQLite como base de datos principal (en /data/datos/autoservice.db)
  - Migración automática desde db.json al primer arranque
  - Endpoints paginados: GET /api/ventas, /api/ordenes, /api/caja
  - POST /api/venta atómico por transacción SQL (race condition imposible)
  - Multi-taller: ?taller=2 selecciona DB separado por sucursal
  - GET /api/db sigue funcionando — compatibilidad total con frontend actual
  - Backups automáticos del SQLite cada 50 guardados
"""

import os
import json
import time
import shutil
import sqlite3
import threading
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── Configuración ──────────────────────────────────────────────────────────────
_raw_key = os.environ.get("API_KEY", "")
if not _raw_key:
    raise RuntimeError("❌ La variable de entorno API_KEY no está configurada. "
                       "Agrega API_KEY en Railway → Variables antes de iniciar.")
API_KEY    = _raw_key
PORT       = int(os.environ.get("PORT", 7890))
STATIC_DIR = Path(__file__).parent.resolve()   # relativo al propio servidor.py

if Path("/data").exists():
    DATA_DIR = Path("/data/datos")
else:
    DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/datos"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

F_DB     = DATA_DIR / "db.json"
F_CONFIG = DATA_DIR / "config.json"
F_USERS  = DATA_DIR / "usuarios.json"
F_AUDIT  = DATA_DIR / "audit.json"
F_SQLITE = DATA_DIR / "autoservice.db"

_save_count = 0
_db_lock    = threading.Lock()

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="TallerPOS API v1.0", docs_url=None, redoc_url=None)
_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if not _ALLOWED_ORIGINS:
    _ALLOWED_ORIGINS = ["*"]  # fallback — restringe con CORS_ORIGINS=https://tu-app.up.railway.app
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "x-api-key"],
)

# ══════════════════════════════════════════════════════════════════════════════
# SQLITE — helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_db_path(taller_id="1") -> Path:
    if taller_id == "1":
        return F_SQLITE
    safe = "".join(c for c in taller_id if c.isalnum() or c in "-_")
    return DATA_DIR / f"autoservice_{safe}.db"

@contextmanager
def db_conn(taller_id="1"):
    path = get_db_path(taller_id)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_schema(taller_id="1"):
    with db_conn(taller_id) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY, value TEXT
        );
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS vehiculos (
            id INTEGER PRIMARY KEY, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mecanicos (
            id INTEGER PRIMARY KEY, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inventario (
            id INTEGER PRIMARY KEY, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ordenes (
            id TEXT PRIMARY KEY, fecha TEXT NOT NULL,
            cliId INTEGER, data TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ord_fecha ON ordenes(fecha);
        CREATE INDEX IF NOT EXISTS idx_inv_id ON inventario(id);
        CREATE TABLE IF NOT EXISTS ventas (
            id TEXT PRIMARY KEY, fecha TEXT NOT NULL, data TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ven_fecha ON ventas(fecha);
        CREATE TABLE IF NOT EXISTS caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL, data TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_caja_fecha ON caja(fecha);
        CREATE TABLE IF NOT EXISTS presupuestos (
            id TEXT PRIMARY KEY, fecha TEXT NOT NULL, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS compras (
            id TEXT PRIMARY KEY, fecha TEXT NOT NULL, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cxp (
            id INTEGER PRIMARY KEY, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cxc (
            id INTEGER PRIMARY KEY, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS planilla (
            id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS turnos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, data TEXT NOT NULL
        );
        """)
    print(f"[SQLite] Schema OK — {get_db_path(taller_id).name}")

# ══════════════════════════════════════════════════════════════════════════════
# MIGRACIÓN desde db.json
# ══════════════════════════════════════════════════════════════════════════════

def migrar_json_a_sqlite(taller_id="1"):
    if not F_DB.exists():
        print("[MIGRAR] Sin db.json — omitiendo")
        return
    with db_conn(taller_id) as conn:
        n = conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
        if n > 0:
            print(f"[MIGRAR] SQLite ya tiene {n} ventas — omitiendo")
            return
    print("[MIGRAR] Iniciando desde db.json...")
    try:
        data = json.loads(F_DB.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[MIGRAR] Error: {e}"); return

    with db_conn(taller_id) as conn:
        def ins(tabla, rows, tiene_fecha=False):
            for r in (rows or []):
                rid = r.get("id")
                if rid is None: continue
                rj = json.dumps(r, ensure_ascii=False)
                if tiene_fecha:
                    conn.execute(f"INSERT OR IGNORE INTO {tabla}(id,fecha,data) VALUES(?,?,?)",
                                 (rid, r.get("fecha",""), rj))
                else:
                    conn.execute(f"INSERT OR IGNORE INTO {tabla}(id,data) VALUES(?,?)", (rid, rj))

        ins("clientes",    data.get("clientes",    []))
        ins("vehiculos",   data.get("vehiculos",   []))
        ins("mecanicos",   data.get("mecanicos",   []))
        ins("inventario",  data.get("inventario",  []))
        ins("proveedores", data.get("proveedores", []))
        ins("cxp",         data.get("cxp",         []))
        ins("cxc",         data.get("cxc",         []))
        ins("presupuestos",data.get("presupuestos",[]), True)
        ins("compras",     data.get("compras",     []), True)

        for r in data.get("ordenes", []):
            conn.execute("INSERT OR IGNORE INTO ordenes(id,fecha,cliId,data) VALUES(?,?,?,?)",
                         (r["id"], r.get("fecha",""), r.get("cliId"),
                          json.dumps(r, ensure_ascii=False)))

        for r in data.get("ventas", []):
            conn.execute("INSERT OR IGNORE INTO ventas(id,fecha,data) VALUES(?,?,?)",
                         (r["id"], r.get("fecha",""), json.dumps(r, ensure_ascii=False)))

        for r in data.get("caja", []):
            conn.execute("INSERT INTO caja(fecha,data) VALUES(?,?)",
                         (r.get("fecha",""), json.dumps(r, ensure_ascii=False)))

        for r in data.get("gastos", []):
            conn.execute("INSERT INTO gastos(fecha,data) VALUES(?,?)",
                         (r.get("fecha",""), json.dumps(r, ensure_ascii=False)))

        for r in data.get("planilla", []):
            conn.execute("INSERT INTO planilla(data) VALUES(?)", (json.dumps(r, ensure_ascii=False),))

        for r in data.get("turnos", []):
            conn.execute("INSERT INTO turnos(data) VALUES(?)", (json.dumps(r, ensure_ascii=False),))

        for key in ("otN","presN","compN","venN"):
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                         (key, str(data.get(key, 0))))

        turno = data.get("turnoActivo")
        if turno:
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('turnoActivo',?)",
                         (json.dumps(turno, ensure_ascii=False),))

        ts = int(time.time())
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('last_ts',?)", (str(ts),))

    # Backup del JSON original
    bk = DATA_DIR / f"db_pre_sqlite_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    shutil.copy2(F_DB, bk)
    print(f"[MIGRAR] ✅ Completado — backup JSON en {bk.name}")

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def read_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] {path}: {e}")
    return default.copy() if isinstance(default, dict) else list(default)

def write_json(path, data):
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        print(f"[ERROR] {path}: {e}")
        tmp.unlink(missing_ok=True)
        raise

def get_ts(taller_id="1") -> int:
    with db_conn(taller_id) as conn:
        r = conn.execute("SELECT value FROM meta WHERE key='last_ts'").fetchone()
        return int(r[0]) if r else 0

def set_ts(taller_id="1") -> int:
    ts = int(time.time())
    with db_conn(taller_id) as conn:
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('last_ts',?)", (str(ts),))
    return ts

def maybe_backup(taller_id="1"):
    global _save_count
    _save_count += 1
    if _save_count % 50 == 0:
        try:
            src = get_db_path(taller_id)
            ts  = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            dst = BACKUP_DIR / f"autoservice_{taller_id}_{ts}.db"
            shutil.copy2(src, dst)
            backups = sorted(BACKUP_DIR.glob(f"autoservice_{taller_id}_*.db"),
                             key=lambda f: f.stat().st_mtime)
            while len(backups) > 30:
                backups.pop(0).unlink(missing_ok=True)
            print(f"[BACKUP] {dst.name}")
        except Exception as e:
            print(f"[WARN] Backup falló: {e}")

def check_key(request: Request):
    if API_KEY and request.headers.get("x-api-key","") != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

def get_taller(request: Request) -> str:
    return request.query_params.get("taller", "1")

# ══════════════════════════════════════════════════════════════════════════════
# DB ↔ SQLITE — compatibilidad total con el frontend
# ══════════════════════════════════════════════════════════════════════════════

def sqlite_to_dict(taller_id="1") -> dict:
    with db_conn(taller_id) as conn:
        def rows(t, order="id"):
            return [json.loads(r["data"])
                    for r in conn.execute(f"SELECT data FROM {t} ORDER BY {order}")]

        meta   = {r["key"]: r["value"]
                  for r in conn.execute("SELECT key,value FROM meta")}
        turno  = None
        if "turnoActivo" in meta:
            try: turno = json.loads(meta["turnoActivo"])
            except: pass

        return {
            "clientes":    rows("clientes"),
            "vehiculos":   rows("vehiculos"),
            "mecanicos":   rows("mecanicos"),
            "inventario":  rows("inventario"),
            "ordenes":     [json.loads(r["data"]) for r in
                            conn.execute("SELECT data FROM ordenes ORDER BY fecha DESC")],
            "ventas":      [json.loads(r["data"]) for r in
                            conn.execute("SELECT data FROM ventas ORDER BY fecha DESC,id DESC")],
            "caja":        [json.loads(r["data"]) for r in
                            conn.execute("SELECT data FROM caja ORDER BY fecha,id")],
            "presupuestos":[json.loads(r["data"]) for r in
                            conn.execute("SELECT data FROM presupuestos ORDER BY fecha DESC")],
            "compras":     [json.loads(r["data"]) for r in
                            conn.execute("SELECT data FROM compras ORDER BY fecha DESC")],
            "proveedores": rows("proveedores"),
            "cxp":         rows("cxp"),
            "cxc":         rows("cxc"),
            "gastos":      [json.loads(r["data"]) for r in
                            conn.execute("SELECT data FROM gastos ORDER BY fecha,id")],
            "planilla":    rows("planilla"),
            "turnos":      rows("turnos"),
            "otN":         int(meta.get("otN",  1000)),
            "presN":       int(meta.get("presN", 100)),
            "compN":       int(meta.get("compN",   1)),
            "venN":        int(meta.get("venN",    0)),
            "turnoActivo": turno,
        }

def dict_to_sqlite(data: dict, taller_id="1"):
    """
    Sincroniza el dict completo del frontend al SQLite.
    Estrategia: DELETE+INSERT para tablas con id fijo (respeta eliminaciones),
    merge inteligente para ventas (protege ventas de /api/venta no incluidas aún).
    """
    with db_conn(taller_id) as conn:

        def reemplazar(tabla, rows, tiene_fecha=False):
            """DELETE + INSERT — respeta eliminaciones del frontend."""
            conn.execute(f"DELETE FROM {tabla}")
            for r in (rows or []):
                rid = r.get("id")
                if rid is None: continue
                rj = json.dumps(r, ensure_ascii=False)
                if tiene_fecha:
                    conn.execute(f"INSERT INTO {tabla}(id,fecha,data) VALUES(?,?,?)",
                                 (rid, r.get("fecha",""), rj))
                else:
                    conn.execute(f"INSERT INTO {tabla}(id,data) VALUES(?,?)", (rid, rj))

        def merge_ventas(rows):
            """
            Para ventas: INSERT OR REPLACE para no perder ventas atómicas de /api/venta
            que el frontend aún no tiene en su DB local.
            Sí elimina ventas anuladas (las que vienen con anulada=true ya están en rows).
            """
            # Traer ids que ya existen en SQLite
            ids_server = {r[0] for r in conn.execute("SELECT id FROM ventas").fetchall()}
            ids_front  = {r.get("id") for r in (rows or []) if r.get("id")}
            # Ids que están en servidor pero no en frontend — son ventas de /api/venta
            # recientes que el frontend no descargó aún — preservarlas
            for r in (rows or []):
                rid = r.get("id")
                if rid is None: continue
                conn.execute("INSERT OR REPLACE INTO ventas(id,fecha,data) VALUES(?,?,?)",
                             (rid, r.get("fecha",""), json.dumps(r, ensure_ascii=False)))
            # No borrar ventas que están en servidor pero no en frontend
            # (se borrarán en la próxima sincronización cuando el frontend las descargue)

        def reemplazar_caja(rows):
            """Caja: DELETE+INSERT completo — el frontend es la fuente de verdad."""
            conn.execute("DELETE FROM caja")
            for r in (rows or []):
                conn.execute("INSERT INTO caja(fecha,data) VALUES(?,?)",
                             (r.get("fecha",""), json.dumps(r, ensure_ascii=False)))

        reemplazar("clientes",    data.get("clientes",   []))
        reemplazar("vehiculos",   data.get("vehiculos",  []))
        reemplazar("mecanicos",   data.get("mecanicos",  []))
        reemplazar("inventario",  data.get("inventario", []))
        reemplazar("proveedores", data.get("proveedores",[]))
        reemplazar("cxp",         data.get("cxp",        []))
        reemplazar("cxc",         data.get("cxc",        []))
        reemplazar("presupuestos",data.get("presupuestos",[]), tiene_fecha=True)
        reemplazar("compras",     data.get("compras",    []), tiene_fecha=True)

        # Órdenes: DELETE+INSERT completo — respeta eliminaciones
        conn.execute("DELETE FROM ordenes")
        for r in data.get("ordenes", []):
            conn.execute("INSERT INTO ordenes(id,fecha,cliId,data) VALUES(?,?,?,?)",
                         (r["id"], r.get("fecha",""), r.get("cliId"),
                          json.dumps(r, ensure_ascii=False)))

        # Ventas: merge — protege ventas atómicas de /api/venta
        merge_ventas(data.get("ventas", []))

        # Caja: DELETE+INSERT completo
        reemplazar_caja(data.get("caja", []))

        # Gastos: DELETE+INSERT
        conn.execute("DELETE FROM gastos")
        for r in data.get("gastos", []):
            conn.execute("INSERT INTO gastos(fecha,data) VALUES(?,?)",
                         (r.get("fecha",""), json.dumps(r, ensure_ascii=False)))

        # Planilla: DELETE+INSERT
        conn.execute("DELETE FROM planilla")
        for r in data.get("planilla", []):
            conn.execute("INSERT INTO planilla(data) VALUES(?)",
                         (json.dumps(r, ensure_ascii=False),))

        # Turnos: DELETE+INSERT
        conn.execute("DELETE FROM turnos")
        for r in data.get("turnos", []):
            conn.execute("INSERT INTO turnos(data) VALUES(?)",
                         (json.dumps(r, ensure_ascii=False),))

        for key in ("otN","presN","compN","venN"):
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                         (key, str(data.get(key,0))))

        turno = data.get("turnoActivo")
        if turno:
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('turnoActivo',?)",
                         (json.dumps(turno,ensure_ascii=False),))
        else:
            conn.execute("DELETE FROM meta WHERE key='turnoActivo'")

# ══════════════════════════════════════════════════════════════════════════════
# DEFAULTS
# ══════════════════════════════════════════════════════════════════════════════

CONFIG_DEFAULT = {
    "taller":"AutoService Pro","ruc":"","dir":"","dist":"",
    "tel":"","cel":"","email":"","footer":"Gracias por su preferencia",
    "urlPublica":"",
    "categorias":{
        "Filtros":    ["Filtro de Aceite","Filtro de Aire","Filtro de Combustible","Filtro de Habitáculo"],
        "Lubricantes":["Aceite de Motor","Aceite de Caja","Aceite de Diferencial"],
        "Frenos":     ["Pastillas","Discos","Tambores","Líquido de Frenos"],
        "Motor":      ["Bujías","Correas","Rodamientos","Juntas"],
        "Eléctrico":  ["Baterías","Alternadores","Arranques","Fusibles"],
        "Suspensión": ["Amortiguadores","Resortes","Rótulas","Terminales"],
        "Otros":      ["General"]
    },
    "permisos":{
        "admin":   {"verCosto":True, "verCaja":True, "verReportes":True, "verConfig":True,
                    "eliminar":True, "verSueldos":True,"crearOT":True,"verPresupuestos":True,
                    "verCompras":True,"verCxp":True,"verVentas":True},
        "cajero":  {"verCosto":True, "verCaja":True, "verReportes":True, "verConfig":False,
                    "eliminar":False,"verSueldos":False,"crearOT":True,"verPresupuestos":True,
                    "verCompras":True,"verCxp":True,"verVentas":True},
        "mecanico":{"verCosto":False,"verCaja":False,"verReportes":False,"verConfig":False,
                    "eliminar":False,"verSueldos":False,"crearOT":True,"verPresupuestos":False,
                    "verCompras":False,"verCxp":False,"verVentas":False},
        "vendedor":{"verCosto":False,"verCaja":False,"verReportes":False,"verConfig":False,
                    "eliminar":False,"verSueldos":False,"crearOT":False,"verPresupuestos":True,
                    "verCompras":False,"verCxp":False,"verVentas":True}
    }
}
USERS_DEFAULT = [{"id":1,"nombre":"Admin","emoji":"👑","rol":"admin",
                  "pin":"1234","color":"#e8b84b","activo":True}]

# ── Arranque ──────────────────────────────────────────────────────────────────
init_schema("1")
migrar_json_a_sqlite("1")
if not F_CONFIG.exists(): write_json(F_CONFIG, CONFIG_DEFAULT)
if not F_USERS.exists():  write_json(F_USERS,  USERS_DEFAULT)
if not F_AUDIT.exists():  write_json(F_AUDIT,  [])

# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health(request: Request):
    check_key(request)
    with db_conn("1") as conn:
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ["ventas","ordenes","inventario","clientes"]}
    return {"status":"ok","version":"TallerPOS-1.0-sqlite",
            "time":datetime.utcnow().isoformat(),
            "sqlite_mb":round(F_SQLITE.stat().st_size/1024/1024,2) if F_SQLITE.exists() else 0,
            "counts":counts,"save_count":_save_count}

@app.get("/api/sync")
async def get_sync(request: Request):
    check_key(request)
    taller = get_taller(request)
    return JSONResponse({
        "ts":     get_ts(taller),
        "ts_cfg": int(F_CONFIG.stat().st_mtime) if F_CONFIG.exists() else 0,
        "ts_usr": int(F_USERS.stat().st_mtime)  if F_USERS.exists()  else 0,
    })

@app.get("/api/db")
async def get_db(request: Request):
    check_key(request)
    taller = get_taller(request)
    db = sqlite_to_dict(taller)
    for campo in ("cxc","gastos","turnos","planilla"):
        if campo not in db: db[campo] = []
    if "venN" not in db: db["venN"] = 0
    return JSONResponse(db)

@app.post("/api/db")
async def post_db(request: Request):
    check_key(request)
    taller = get_taller(request)
    data   = await request.json()
    with _db_lock:
        dict_to_sqlite(data, taller)
        ts = set_ts(taller)
        maybe_backup(taller)
    return {"ok":True,"ts":ts}

@app.post("/api/venta")
async def post_venta(request: Request):
    check_key(request)
    taller  = get_taller(request)
    payload = await request.json()
    venta   = payload.get("venta")
    items   = payload.get("items", [])
    caja_e  = payload.get("caja",  [])
    cxc_e   = payload.get("cxc",   None)

    if not venta:
        raise HTTPException(status_code=400, detail="Falta campo venta")

    path = get_db_path(taller)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("BEGIN EXCLUSIVE")

    try:
        # Validar stock real
        for it in items:
            inv_id = it.get("invId"); qty = int(it.get("qty",1))
            if not inv_id: continue
            row = conn.execute("SELECT data FROM inventario WHERE id=?", (inv_id,)).fetchone()
            if not row: continue
            inv = json.loads(row["data"])
            ei  = it.get("equivIdx")
            if ei is not None and inv.get("equiv") and len(inv["equiv"]) > ei:
                disp = inv["equiv"][ei].get("stock",0)
            else:
                disp = inv.get("stock",0)
            if disp < qty:
                conn.rollback(); conn.close()
                return JSONResponse(status_code=409, content={
                    "ok":False,"error":"stock_insuficiente",
                    "producto":inv.get("desc",f"ID {inv_id}"),
                    "disponible":disp,"solicitado":qty})

        # Descontar stock
        for it in items:
            inv_id = it.get("invId"); qty = int(it.get("qty",1))
            if not inv_id: continue
            row = conn.execute("SELECT data FROM inventario WHERE id=?", (inv_id,)).fetchone()
            if not row: continue
            inv = json.loads(row["data"]); ei = it.get("equivIdx")
            if ei is not None and inv.get("equiv") and len(inv["equiv"]) > ei:
                inv["equiv"][ei]["stock"] = max(0, inv["equiv"][ei].get("stock",0) - qty)
            else:
                inv["stock"] = max(0, inv.get("stock",0) - qty)
            conn.execute("UPDATE inventario SET data=? WHERE id=?",
                         (json.dumps(inv,ensure_ascii=False), inv_id))

        # Registrar venta
        conn.execute("INSERT OR REPLACE INTO ventas(id,fecha,data) VALUES(?,?,?)",
                     (venta["id"], venta.get("fecha",""), json.dumps(venta,ensure_ascii=False)))

        for e in caja_e:
            conn.execute("INSERT INTO caja(fecha,data) VALUES(?,?)",
                         (e.get("fecha",""), json.dumps(e,ensure_ascii=False)))

        if cxc_e:
            conn.execute("INSERT OR IGNORE INTO cxc(id,data) VALUES(?,?)",
                         (cxc_e["id"], json.dumps(cxc_e,ensure_ascii=False)))

        venN_r = conn.execute("SELECT value FROM meta WHERE key='venN'").fetchone()
        venN   = int(venN_r[0])+1 if venN_r else 1
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('venN',?)", (str(venN),))

        ts = int(time.time())
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('last_ts',?)", (str(ts),))
        conn.commit()
        maybe_backup(taller)

    except Exception as e:
        conn.rollback(); conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    conn.close()
    return {"ok":True,"ts":ts,"ventaId":venta.get("id")}

# ── Endpoints paginados ───────────────────────────────────────────────────────
@app.get("/api/ventas")
async def api_ventas(request: Request, page: int=1, limit: int=50,
                     q: str="", fecha: str="", desde: str="", hasta: str=""):
    check_key(request)
    taller = get_taller(request); offset = (page-1)*limit
    with db_conn(taller) as conn:
        w, p = [], []
        if q:     w.append("(id LIKE ? OR data LIKE ?)"); p += [f"%{q}%",f"%{q}%"]
        if fecha: w.append("fecha=?"); p.append(fecha)
        if desde: w.append("fecha>=?"); p.append(desde)
        if hasta: w.append("fecha<=?"); p.append(hasta)
        ws = ("WHERE "+" AND ".join(w)) if w else ""
        total = conn.execute(f"SELECT COUNT(*) FROM ventas {ws}", p).fetchone()[0]
        rows  = conn.execute(
            f"SELECT data FROM ventas {ws} ORDER BY fecha DESC,id DESC LIMIT ? OFFSET ?",
            p+[limit,offset]).fetchall()
    return JSONResponse({"items":[json.loads(r["data"]) for r in rows],
                         "total":total,"page":page,"pages":(total+limit-1)//limit})

@app.get("/api/ordenes")
async def api_ordenes(request: Request, page: int=1, limit: int=50,
                      q: str="", estado: str="", fecha: str=""):
    check_key(request)
    taller = get_taller(request); offset = (page-1)*limit
    with db_conn(taller) as conn:
        w, p = [], []
        if estado: w.append("data LIKE ?"); p.append(f'%"estado":"{estado}"%')
        if fecha:  w.append("fecha=?");     p.append(fecha)
        if q:      w.append("(id LIKE ? OR data LIKE ?)"); p += [f"%{q}%",f"%{q}%"]
        ws = ("WHERE "+" AND ".join(w)) if w else ""
        total = conn.execute(f"SELECT COUNT(*) FROM ordenes {ws}", p).fetchone()[0]
        rows  = conn.execute(
            f"SELECT data FROM ordenes {ws} ORDER BY fecha DESC LIMIT ? OFFSET ?",
            p+[limit,offset]).fetchall()
    return JSONResponse({"items":[json.loads(r["data"]) for r in rows],
                         "total":total,"page":page})

@app.get("/api/caja")
async def api_caja(request: Request, fecha: str="", desde: str="", hasta: str=""):
    check_key(request)
    taller = get_taller(request)
    with db_conn(taller) as conn:
        w, p = [], []
        if fecha: w.append("fecha=?"); p.append(fecha)
        if desde: w.append("fecha>=?"); p.append(desde)
        if hasta: w.append("fecha<=?"); p.append(hasta)
        ws = ("WHERE "+" AND ".join(w)) if w else ""
        rows = conn.execute(f"SELECT data FROM caja {ws} ORDER BY fecha,id", p).fetchall()
    return JSONResponse({"items":[json.loads(r["data"]) for r in rows]})

# ── Config / Usuarios / Audit ─────────────────────────────────────────────────
@app.get("/api/config")
async def get_config(request: Request):
    check_key(request)
    return JSONResponse(read_json(F_CONFIG, CONFIG_DEFAULT))

@app.post("/api/config")
async def post_config(request: Request):
    check_key(request)
    write_json(F_CONFIG, await request.json())
    return {"ok":True,"ts":int(time.time())}

@app.get("/api/usuarios")
async def get_usuarios(request: Request):
    check_key(request)
    return JSONResponse(read_json(F_USERS, USERS_DEFAULT))

@app.post("/api/usuarios")
async def post_usuarios(request: Request):
    check_key(request)
    write_json(F_USERS, await request.json())
    return {"ok":True,"ts":int(time.time())}

@app.get("/api/audit")
async def get_audit(request: Request):
    check_key(request)
    taller = get_taller(request)
    with db_conn(taller) as conn:
        rows = conn.execute("SELECT data FROM audit ORDER BY id DESC LIMIT 500").fetchall()
    return JSONResponse([json.loads(r["data"]) for r in rows])

@app.post("/api/audit")
async def post_audit(request: Request):
    check_key(request)
    taller = get_taller(request)
    entry  = await request.json()
    entry["_ts"] = datetime.utcnow().isoformat()
    with db_conn(taller) as conn:
        conn.execute("INSERT INTO audit(ts,data) VALUES(?,?)",
                     (entry["_ts"], json.dumps(entry,ensure_ascii=False)))
        conn.execute("DELETE FROM audit WHERE id NOT IN "
                     "(SELECT id FROM audit ORDER BY id DESC LIMIT 2000)")
    return {"ok":True}

@app.post("/api/backup")
async def post_backup(request: Request):
    check_key(request)
    taller = get_taller(request)
    data   = await request.json()
    ts     = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dst    = BACKUP_DIR / f"backup_{ts}.json"
    write_json(dst, data)
    if "DB"       in data: dict_to_sqlite(data["DB"], taller)
    if "CONFIG"   in data: write_json(F_CONFIG, data["CONFIG"])
    if "USUARIOS" in data: write_json(F_USERS,  data["USUARIOS"])
    return {"ok":True,"backup":dst.name}

@app.get("/api/diagnostico")
async def diagnostico(request: Request):
    check_key(request)
    taller = get_taller(request)
    sp     = get_db_path(taller)
    with db_conn(taller) as conn:
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ["ventas","ordenes","inventario","clientes","vehiculos","caja"]}
    return JSONResponse({
        "version":"TallerPOS-1.0-sqlite","data_dir":str(DATA_DIR),
        "sqlite":str(sp),
        "sqlite_mb":round(sp.stat().st_size/1024/1024,2) if sp.exists() else 0,
        "counts":counts,"save_count":_save_count,
        "backups":len(list(BACKUP_DIR.glob("*.db")))+len(list(BACKUP_DIR.glob("*.json")))
    })

@app.get("/api/talleres")
async def get_talleres(request: Request):
    check_key(request)
    result = []
    for f in DATA_DIR.glob("autoservice*.db"):
        tid = "1" if f.stem == "autoservice" else f.stem.replace("autoservice_","")
        result.append({"id":tid,"archivo":f.name,
                       "mb":round(f.stat().st_size/1024/1024,2)})
    return JSONResponse({"talleres":result})

@app.post("/api/talleres")
async def crear_taller(request: Request):
    check_key(request)
    body = await request.json()
    tid  = body.get("id","")
    if not tid or not all(c.isalnum() or c in "-_" for c in tid):
        raise HTTPException(400, "ID inválido")
    init_schema(tid)
    return {"ok":True,"taller":tid}

# ── Estáticos ─────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    for name in ["index.html","autoservice_v33.html","autoservice.html"]:
        f = STATIC_DIR / name
        if f.exists():
            html = f.read_text(encoding="utf-8")
            # Inyectar meta tag con la API key para que el frontend no la tenga hardcodeada
            meta_inject = f'<meta name="as-api-key" content="{API_KEY}">'
            html = html.replace("</head>", f"  {meta_inject}\n</head>", 1)
            content = html.encode("utf-8")
            return Response(content=content, media_type="text/html; charset=utf-8",
                            headers={"Content-Length": str(len(content)),
                                     "Cache-Control": "no-cache, no-store, must-revalidate",
                                     "Pragma": "no-cache"})
    return HTMLResponse("<h1>AutoService Pro</h1><p>Coloca tu index.html junto a servidor.py</p>",
                        status_code=503)

@app.get("/{path:path}")
async def static_files(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    f = (STATIC_DIR / path).resolve()
    # Protección contra path traversal: el archivo debe estar dentro de STATIC_DIR
    if not str(f).startswith(str(STATIC_DIR)):
        raise HTTPException(status_code=403, detail="Forbidden")
    if f.exists() and f.is_file():
        return FileResponse(str(f))
    raise HTTPException(status_code=404, detail="Not found")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"✅ TallerPOS v1.0 — Puerto {PORT}")
    print(f"📁 Datos: {DATA_DIR}")
    print(f"🗄️  SQLite: {F_SQLITE}")
    print(f"🔑 API Key: OK ({API_KEY[:4]}...)")
    uvicorn.run("servidor:app", host="0.0.0.0", port=PORT, reload=False)
