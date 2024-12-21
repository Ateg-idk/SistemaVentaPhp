<?php
// Configuración y autoload
require_once "./config/app.php";
require_once "./autoload.php";

// Inicio de sesión
require_once "./app/views/inc/session_start.php";

// Procesamiento de la URL y verificación de seguridad
$url = isset($_GET['views']) ? explode("/", trim($_GET['views'], '/')) : ["login"];
$vista_actual = $url[0];

// Instanciar controladores
use app\controllers\viewsController;
use app\controllers\loginController;

$insLogin = new loginController();
$viewsController = new viewsController();
$vista = $viewsController->obtenerVistasControlador($vista_actual);

// Definir vistas públicas
$vistas_publicas = ["login", "404"];

// Iniciar el buffer de salida
ob_start();

// Verificar estado de la sesión para vistas protegidas
if (!in_array($vista_actual, $vistas_publicas) && 
    (!isset($_SESSION['id']) || empty($_SESSION['id']) || 
     !isset($_SESSION['usuario']) || empty($_SESSION['usuario']))) {
    
    // Limpiar cualquier salida previa
    ob_clean();
    
    // Redirigir al login
    header("Location: " . APP_URL . "login/");
    exit();
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <?php require_once "./app/views/inc/head.php"; ?>
</head>
<body>
    <?php
    if(in_array($vista, $vistas_publicas)){
        // Cargar vistas públicas
        require_once "./app/views/content/".$vista."-view.php";
    } else {
        try {
            ?>
            <main class="page-container">
                <?php 
                require_once "./app/views/inc/navlateral.php";
                ?>
                <section class="full-width pageContent scroll" id="pageContent">
                    <?php
                    require_once "./app/views/inc/navbar.php";
                    
                    // Verificar que el archivo de vista existe
                    if(is_file($vista)){
                        require_once $vista;
                    } else {
                        // Si no existe la vista, mostrar 404
                        require_once "./app/views/content/404-view.php";
                    }
                    ?>
                </section>
            </main>
            <?php
        } catch (Exception $e) {
            // Log del error y mostrar página 404
            error_log("Error en vista: " . $e->getMessage());
            require_once "./app/views/content/404-view.php";
        }
    }
    
    // Cargar scripts
    require_once "./app/views/inc/script.php";
    ?>
    
    <script>
    // Prevenir problemas de caché en navegación
    if (window.history.replaceState) {
        window.history.replaceState(null, null, window.location.href);
    }
    </script>
</body>
</html>
<?php
// Limpiar y enviar el buffer
ob_end_flush();
?>