<?php

	const APP_URL="http://localhost/SistemaVenta/";
	const APP_NAME="SistemaVenta";
	const APP_SESSION_NAME="POS";

	/*----------  Tipos de documentos  ----------*/
	const DOCUMENTOS_USUARIOS=["DNI","Otro"];


	/*----------  Tipos de unidades de productos  ----------*/
	const PRODUCTO_UNIDAD=["Unidad","Caja","Paquete","Lata","Galon","Botella","Bolsa"];

	/*----------  Configuración de moneda  ----------*/
	const MONEDA_SIMBOLO="S/";
	const MONEDA_NOMBRE="PEN";
	const MONEDA_DECIMALES="2";
	const MONEDA_SEPARADOR_MILLAR=",";
	const MONEDA_SEPARADOR_DECIMAL=".";


	/*----------  Marcador de campos obligatorios (Font Awesome) ----------*/
	const CAMPO_OBLIGATORIO='&nbsp; <i class="fas fa-edit"></i> &nbsp;';

	/*----------  Zona horaria  ----------*/
	date_default_timezone_set("America/Lima");

	