<?php
// Configuración dinámica de APP_URL
$protocol = isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on' ? "https" : "http";
$host = $_SERVER['HTTP_HOST'];
$script_name = dirname($_SERVER['SCRIPT_NAME']);
$base_path = rtrim($script_name, '/\\') . '/';

define("APP_URL", $protocol . "://" . $host . $base_path);


// Función para generar rutas
function url($path = '') {
    return APP_URL . ltrim($path, '/');
}

// Configuraciones adicionales
const APP_NAME = "SistemaVentaPhp";
const APP_SESSION_NAME = "POS";

// Tipos de documentos
const DOCUMENTOS_USUARIOS = ["DNI", "Otro"];

// Tipos de unidades de productos
const PRODUCTO_UNIDAD = ["Unidad", "Caja", "Paquete", "Lata", "Galon", "Botella", "Bolsa"];

// Configuración de moneda
const MONEDA_SIMBOLO = "S/";
const MONEDA_NOMBRE = "PEN";
const MONEDA_DECIMALES = "2";
const MONEDA_SEPARADOR_MILLAR = ",";
const MONEDA_SEPARADOR_DECIMAL = ".";

// Marcador de campos obligatorios (Font Awesome)
const CAMPO_OBLIGATORIO = '&nbsp; <i class="fas fa-edit"></i> &nbsp;';

// Configuración de zona horaria
date_default_timezone_set("America/Lima");
?>
