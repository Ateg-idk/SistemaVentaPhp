<?php
// Configuración de cookies seguras para producción
$cookie_params = array(
    'lifetime' => 0,
    'path' => '/',
    'domain' => '',
    'secure' => true,    // Solo HTTPS
    'httponly' => true,  // Protección contra XSS
    'samesite' => 'Strict' // Protección contra CSRF
);

session_name(APP_SESSION_NAME);
session_set_cookie_params($cookie_params);
session_start();

// Regenerar ID de sesión periódicamente para seguridad
if (!isset($_SESSION['last_regeneration'])) {
    session_regenerate_id(true);
    $_SESSION['last_regeneration'] = time();
} else if (time() - $_SESSION['last_regeneration'] > 3600) {
    session_regenerate_id(true);
    $_SESSION['last_regeneration'] = time();
}