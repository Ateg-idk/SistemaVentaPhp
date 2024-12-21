<?php
// Configuración de seguridad y cabeceras
ini_set('session.cookie_httponly', 1);
ini_set('session.use_only_cookies', 1);

// Detectar el protocolo y host
$protocol = isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on' ? "https" : "http";
$host = $_SERVER['HTTP_HOST'];

// Detectar el entorno (local o producción)
if ($host === 'localhost' || $host === '127.0.0.1') {
    $base_path = '/SistemaVentaPhp/'; // Ruta base para entorno local
} else {
    $base_path = '/'; // Ruta base para producción
}

// Construir la URL base
define("APP_URL", $protocol . "://" . $host . $base_path);
// Función para generar rutas
function url($path = '') {
    return APP_URL . ltrim($path, '/');
}

// Configuraciones de la aplicación
const APP_NAME = "SistemaVentaPhp";
const APP_SESSION_NAME = "POS";

// Configuración de documentos y productos
const DOCUMENTOS_USUARIOS = ["DNI", "Otro"];
const PRODUCTO_UNIDAD = [
    "Unidad",
    "Caja",
    "Paquete",
    "Lata",
    "Galon",
    "Botella",
    "Bolsa"
];

// Configuración de moneda
const MONEDA_NOMBRE = "PEN";
const MONEDA_DECIMALES = "2";
const MONEDA_SEPARADOR_MILLAR = ",";
const MONEDA_SEPARADOR_DECIMAL = ".";

// Marcador de campos obligatorios
const CAMPO_OBLIGATORIO = '&nbsp; <i class="fas fa-edit"></i> &nbsp;';

// Configuración de zona horaria
date_default_timezone_set("America/Lima");

// Configuración de errores en desarrollo/producción
if ($host === 'localhost' || $host === '127.0.0.1') {
    error_reporting(E_ALL);
    ini_set('display_errors', 1);
} else {
    error_reporting(0);
    ini_set('display_errors', 0);
}

// Función para validar rutas
function validar_ruta($ruta) {
    $ruta_limpia = ltrim($ruta, '/');
    return APP_URL . $ruta_limpia;
}

// Función para obtener la ruta actual
function obtener_ruta_actual() {
    $path = $_SERVER['REQUEST_URI'];
    $base_path_pos = strpos($path, basename(APP_URL));
    if ($base_path_pos !== false) {
        $path = substr($path, $base_path_pos + strlen(basename(APP_URL)));
    }
    return trim($path, '/');
}