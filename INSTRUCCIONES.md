# TallerPOS v1.0 — Sistema Integrado Taller + Mostrador

## ¿Qué incluye este sistema?

TallerPOS combina lo mejor de dos sistemas en uno:

- **Módulo Taller**: Órdenes de Trabajo, vehículos, mecánicos, presupuestos, historial
- **Módulo Mostrador POS**: Venta directa de productos al cliente con carrito, boletas e IGV
- **Inventario unificado**: Repuestos (para OTs), productos (para mostrador) o ambos
- **Reportes por canal**: Compara ingresos de taller vs mostrador
- **Multi-usuario con roles**: Admin, Cajero, Mecánico, Vendedor (con permisos granulares)
- **Sync multi-dispositivo**: Varios celulares/PCs en tiempo real
- **Backups automáticos**: SQLite en volumen persistente de Railway

---

## Archivos del proyecto

```
tallerpOS/
├── index.html       → Sistema completo (frontend)
├── servidor.py      → Backend FastAPI + SQLite (v1.0)
├── requirements.txt → Dependencias Python (versiones fijadas)
├── Procfile         → Comando de inicio en Railway
├── railway.json     → Configuración de Railway
└── .gitignore       → Archivos ignorados por Git
```

---

## PASOS PARA SUBIR A RAILWAY

### PASO 1 — Subir a GitHub

1. Ir a https://github.com/new
2. Nombre: `tallerpOS` — marcar como **Privado**
3. Clic en "Create repository"
4. Clic en "uploading an existing file"
5. Arrastrar TODOS los archivos de esta carpeta
6. Clic en "Commit changes"

---

### PASO 2 — Crear proyecto en Railway

1. Ir a https://railway.app
2. Login with GitHub
3. Clic en **"New Project"** → **"Deploy from GitHub repo"**
4. Seleccionar `tallerpOS`
5. Esperar 2-3 minutos

---

### PASO 3 — Variables de entorno (OBLIGATORIO)

En Railway → tu servicio → pestaña **"Variables"**, agregar:

```
API_KEY  = moycars2026
DATA_DIR = /data
```

> ⚠️ Sin API_KEY el servidor **no arranca**.

---

### PASO 4 — Volumen persistente (OBLIGATORIO)

En Railway → tu servicio → pestaña **"Volumes"**:

1. Clic en "Add Volume"
2. Mount path: `/data`
3. Clic en "Add"

> ⚠️ Sin el volumen, los datos se pierden al reiniciar Railway.

---

### PASO 5 — Dominio

En Railway → pestaña **"Settings"** → sección "Domains":
1. Clic en "Generate Domain"
2. Recibirás una URL tipo: `tallerpOS-production.up.railway.app`

---

### PASO 6 (opcional) — Restringir CORS

En **"Variables"** agregar:

```
CORS_ORIGINS = https://tu-app.up.railway.app
```

---

## Tipos de inventario

| Tipo | Aparece en | Se descuenta cuando |
|------|-----------|---------------------|
| 🔧 Repuesto | Selector de OTs | Se cobra la OT |
| 🛒 Producto | POS Mostrador | Se cobra en mostrador |
| 🔀 Ambos | OTs + Mostrador | En cualquiera de los dos |

---

## Roles y permisos

| Permiso | Admin | Cajero | Mecánico | Vendedor |
|---------|-------|--------|----------|---------|
| Ver costos | ✅ | ✅ | ❌ | ❌ |
| Acceder Caja | ✅ | ✅ | ❌ | ❌ |
| Mostrador POS | ✅ | ✅ | ❌ | ✅ |
| Crear OTs | ✅ | ✅ | ✅ | ❌ |
| Ver Reportes | ✅ | ✅ | ❌ | ❌ |
| Eliminar | ✅ | ❌ | ❌ | ❌ |

---

## Flujo OT → Mostrador (nuevo en v1.0)

1. Mecánico registra la OT y agrega repuestos
2. Al finalizar → "Por Cobrar" → aparece botón **🛒 POS**
3. Al clicar POS, los repuestos + mano de obra se cargan en el carrito
4. El cajero puede agregar más productos desde el mostrador
5. Al cobrar → se genera la boleta y la OT queda como "Entregada"
6. El stock se descuenta automáticamente

---

## Migrar datos desde sistema anterior

1. En tu sistema anterior → Configuración → Exportar/Backup
2. Descargar el JSON de backup
3. En TallerPOS → Configuración → Restaurar Backup
4. Subir el JSON

---

## Costo estimado Railway

| Concepto | Costo |
|----------|-------|
| GitHub | Gratis |
| Railway Hobby | $5 USD/mes |
| Volumen 1GB | Incluido |

**Total: ~S/ 19/mes**
