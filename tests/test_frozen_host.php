<?php
// Exercise both real writer entry points without booting PrestaShop or opening SQL.
declare(strict_types=1);
define('MERCABOY_LIBRARY_ONLY', true);
$preparer = ($argv[1] ?? '') === 'preparer';
require $preparer ? __DIR__ . '/../../corregirPresentacionBlister/bridge.php' : __DIR__ . '/../bridge.php';
$mode = $argv[2] ?? 'settings';
putenv('SERVIDOR_CONGELADO');
$request = ['test_host'=>'10.5.0.227', 'SERVIDOR_CONGELADO'=>'10.5.0.227'];
if ($mode === 'environment') {
    $request['SERVIDOR_CONGELADO'] = '192.168.0.227';
    putenv('SERVIDOR_CONGELADO=10.5.0.227');
}
if ($mode === 'legacy') {
    unset($request['SERVIDOR_CONGELADO']);
    $request['baseline_host'] = '10.5.0.227';
}
if ($mode === 'invalid') {
    $request['SERVIDOR_CONGELADO'] = '';
    try { configureTestHost($request); } catch (RuntimeException $e) {
        demand(strpos($e->getMessage(), 'IPv4 invalida') !== false, 'Error inesperado');
        echo "OK origen vacío rechazado\n"; exit;
    }
    throw new RuntimeException('Se aceptó origen vacío');
}
configureTestHost($request);
demand(SERVIDOR_CONGELADO === '10.5.0.227', 'Origen incorrecto');
try {
    if ($preparer) { applyProduct([]); } else { applyPrices([]); }
} catch (RuntimeException $e) {
    demand(strpos($e->getMessage(), '10.5.0.227 no admite escrituras') !== false, 'Error inesperado');
    echo 'OK ' . ($preparer ? 'preparador' : 'precios') . ' protege origen ' . $mode . "\n"; exit;
}
throw new RuntimeException('No se rechazó escritura sobre origen');
