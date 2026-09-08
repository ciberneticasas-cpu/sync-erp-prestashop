<?php
/** Called by cambiar_ip.py, locally. No network-interface or ERP changes. */
declare(strict_types=1);
define('MERCABOY_LIBRARY_ONLY', true);
require __DIR__ . '/bridge.php';

try {
    $request = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
    $p = localParameters($request);
    // This installation deliberately uses localhost for DB connectivity across IP changes.
    demand(in_array($p['database_host'], ['localhost', '127.0.0.1'], true), 'MySQL debe usar localhost o 127.0.0.1 antes de cambiar IP');
    $db = new mysqli('localhost', $p['database_user'], $p['database_password'], 'mercaboy_pruebas', 3306);
    $db->set_charset('utf8mb4'); $prefix = $p['database_prefix'];
    $urls = $db->query("SELECT * FROM {$prefix}shop_url ORDER BY id_shop_url")->fetch_all(MYSQLI_ASSOC);
    demand(count($urls) === 1 && (int)$urls[0]['id_shop'] === 1, 'Solo se admite la tienda de pruebas unica');
    $old = $urls[0]['domain'];
    foreach ([$old, $urls[0]['domain_ssl']] as $domain) {
        demand(filter_var($domain, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4), 'No se cambia una tienda con dominio publico');
        $parts = array_map('intval', explode('.', $domain));
        demand($parts[0] === 10 || ($parts[0] === 172 && $parts[1] >= 16 && $parts[1] <= 31)
            || ($parts[0] === 192 && $parts[1] === 168), 'El dominio anterior debe ser una IP privada');
    }
    $config = $db->query("SELECT id_configuration,name,value,id_shop_group,id_shop FROM {$prefix}configuration
      WHERE name IN ('PS_SHOP_DOMAIN','PS_SHOP_DOMAIN_SSL','PS_SSL_ENABLED','PS_SSL_ENABLED_EVERYWHERE')
      ORDER BY id_configuration")->fetch_all(MYSQLI_ASSOC);
    $before = ['shop_urls'=>$urls, 'configuration'=>$config];
    if (($request['apply'] ?? false) !== true) {
        echo json_encode(['before'=>$before, 'old_ip'=>$old, 'new_ip'=>TEST_HOST], JSON_UNESCAPED_UNICODE), PHP_EOL;
        exit;
    }
    demand(($request['expected_before'] ?? null) == $before, 'La tienda cambio desde la vista previa; repita el comando');
    $htaccess = '/var/www/html/.htaccess';
    demand(is_file($htaccess) && is_writable($htaccess), '.htaccess debe existir y ser escribible');
    $htaccessBefore = file_get_contents($htaccess);
    // Initialize the existing shop before moving its URL. All DB connections stay local.
    boot($old, true);
    $native = Db::getInstance();
    demand($native->execute('START TRANSACTION'), 'No se pudo iniciar transaccion');
    try {
        $url = new ShopUrl((int)$urls[0]['id_shop_url']);
        $url->domain = TEST_HOST; $url->domain_ssl = TEST_HOST;
        demand($url->update(), 'No se pudo actualizar ShopUrl');
        foreach (['PS_SHOP_DOMAIN','PS_SHOP_DOMAIN_SSL'] as $key) {
            demand(Configuration::updateGlobalValue($key, TEST_HOST), 'No se pudo actualizar dominio global');
            demand(Configuration::updateValue($key, TEST_HOST, false, 1, 1), 'No se pudo actualizar dominio por tienda');
        }
        ShopUrl::resetMainDomainCache();
        $_SERVER['HTTP_HOST'] = TEST_HOST; $_SERVER['SERVER_NAME'] = TEST_HOST;
        demand(Tools::generateHtaccess(), 'No se pudo regenerar .htaccess');
        demand(strpos(file_get_contents($htaccess), '#Domain: '.TEST_HOST) !== false, '.htaccess no contiene el nuevo dominio');
        demand($native->execute('COMMIT'), 'No se pudo confirmar cambio de dominio');
    } catch (Throwable $e) {
        $native->execute('ROLLBACK');
        demand(file_put_contents($htaccess, $htaccessBefore) !== false, 'Fallo restauracion .htaccess: use el respaldo');
        throw $e;
    }
    // These caches contain generated absolute URLs. Do not delete all var/cache or appParameters.
    $cacheWarning = null;
    try { Tools::clearSmartyCache(); Cache::clean('*'); }
    catch (Throwable $e) { $cacheWarning = 'Dominio aplicado; revisar limpieza de cache Smarty'; }
    echo json_encode(['applied'=>true, 'old_ip'=>$old, 'new_ip'=>TEST_HOST, 'cache_warning'=>$cacheWarning], JSON_UNESCAPED_UNICODE), PHP_EOL;
} catch (Throwable $e) {
    $message = $e instanceof RuntimeException && !($e instanceof mysqli_sql_exception)
        ? $e->getMessage() : 'Fallo de conexion o API nativa; detalles omitidos para proteger credenciales';
    fwrite(STDERR, $message . ' [' . get_class($e) . ':' . $e->getCode() . ', ' . basename($e->getFile()) . ':' . $e->getLine() . ']' . PHP_EOL); exit(1);
}
