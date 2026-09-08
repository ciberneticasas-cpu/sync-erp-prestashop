<?php
/** Local CLI adapter for PrestaShop 8.1.7. Never install in the web root. */
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(403); exit; }
ini_set('display_errors', 'stderr');
error_reporting(E_ALL & ~E_DEPRECATED);

function demand($condition, string $message): void {
    if (!$condition) { throw new RuntimeException($message); }
}
function envValues(string $path): array {
    demand(is_readable($path), 'No se puede leer el .env indicado');
    $values = [];
    foreach (file($path, FILE_IGNORE_NEW_LINES) as $line) {
        $line = trim($line);
        if ($line === '' || $line[0] === '#' || strpos($line, '=') === false) { continue; }
        [$key, $value] = explode('=', $line, 2);
        $values[strtoupper(trim($key))] = trim(trim($value), "\"'");
    }
    return $values;
}
function configureTestHost(array $request): void {
    $host = $request['test_host'] ?? '';
    demand(is_string($host) && filter_var($host, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4), 'IP de pruebas invalida');
    $parts = array_map('intval', explode('.', $host));
    $private = $parts[0] === 10 || ($parts[0] === 172 && $parts[1] >= 16 && $parts[1] <= 31) || ($parts[0] === 192 && $parts[1] === 168);
    demand($private && $host !== '192.168.0.231', 'Se requiere una IP LAN de pruebas distinta del ERP');
    if (defined('TEST_HOST')) { demand(TEST_HOST === $host, 'No se puede cambiar destino dentro del proceso'); }
    else { define('TEST_HOST', $host); }
}
function localParameters(array $request): array {
    configureTestHost($request);
    $root = realpath($request['prestashop_root'] ?? '');
    demand($root === '/var/www/html', 'Solo se permite /var/www/html en el servidor de pruebas');
    $parameters = require $root . '/app/config/parameters.php';
    $p = $parameters['parameters'];
    demand($p['database_name'] === 'mercaboy_pruebas', 'Base de datos protegida: se requiere mercaboy_pruebas');
    demand(in_array($p['database_host'], ['localhost', '127.0.0.1', TEST_HOST], true), 'Host MySQL protegido');
    demand(empty($p['database_port']) || (int)$p['database_port'] === 3306, 'Puerto MySQL protegido');
    demand((bool)preg_match('/^\w+$/D', $p['database_prefix']), 'Prefijo invalido');
    // Check the local interface, independently of configuration or DNS.
    $interfaces = net_get_interfaces();
    $addresses = [];
    foreach ($interfaces as $interface) { foreach ($interface['unicast'] ?? [] as $address) { $addresses[] = $address['address'] ?? ''; } }
    demand(in_array(TEST_HOST, $addresses, true), 'La IP de pruebas configurada no esta asignada al servidor');
    return $p;
}
function connection(array $request, array $p): mysqli {
    $env = envValues($request['env_file']);
    // Keep .env unchanged; use its MySQL credentials only when it explicitly targets this test copy.
    $useEnv = ($env['MARIADB_DATABASE'] ?? '') === 'mercaboy_pruebas'
        && in_array($env['MARIADB_HOST'] ?? '', ['localhost','127.0.0.1',TEST_HOST], true);
    $db = new mysqli('localhost', $useEnv ? $env['MARIADB_USER'] : $p['database_user'],
        $useEnv ? $env['MARIADB_PASSWORD'] : $p['database_password'], 'mercaboy_pruebas', 3306);
    $db->set_charset('utf8mb4');
    $prefix = $p['database_prefix'];
    $shops = $db->query("SELECT id_shop, domain, domain_ssl FROM {$prefix}shop_url")->fetch_all(MYSQLI_ASSOC);
    demand(count($shops) === 1 && (int)$shops[0]['id_shop'] === 1 && $shops[0]['domain'] === TEST_HOST
        && $shops[0]['domain_ssl'] === TEST_HOST, 'Se requiere una sola tienda con el dominio de pruebas configurado');
    return $db;
}
function snapshot(mysqli $db, array $p, array $ids = []): array {
    $prefix = $p['database_prefix'];
    $db->query('START TRANSACTION READ ONLY');
    try {
        $lang = (int)$db->query("SELECT value FROM {$prefix}configuration WHERE name='PS_LANG_DEFAULT' LIMIT 1")->fetch_row()[0];
        $where = $ids ? ' AND p.id_product IN ('.implode(',', array_map('intval', $ids)).')' : '';
        $rows = $db->query("SELECT p.id_product AS id, pl.name, p.reference, p.ean13, ps.price,
          ps.active, ps.available_for_order, ps.id_tax_rules_group, ps.cache_default_attribute,
          p.product_type, ps.unity, ps.unit_price_ratio, ps.ecotax, ps.minimal_quantity,
          COALESCE(sa.quantity,0) AS quantity, COALESCE(sa.out_of_stock,2) AS out_of_stock,
          COALESCE(sa.depends_on_stock,0) AS depends_on_stock
          FROM {$prefix}product p JOIN {$prefix}product_shop ps ON ps.id_product=p.id_product AND ps.id_shop=1
          JOIN {$prefix}product_lang pl ON pl.id_product=p.id_product AND pl.id_shop=1 AND pl.id_lang=$lang
          LEFT JOIN {$prefix}stock_available sa ON sa.id_product=p.id_product AND sa.id_product_attribute=0 AND sa.id_shop=1
          WHERE 1=1 $where ORDER BY p.id_product")->fetch_all(MYSQLI_ASSOC);
        $products = [];
        foreach ($rows as $row) { $row['id'] = (int)$row['id']; $row['combinations'] = []; $row['specific_prices'] = []; $products[$row['id']] = $row; }
        $rows = $db->query("SELECT pa.id_product, pa.id_product_attribute AS id, pa.reference, pa.ean13,
          pas.price, pas.default_on, pas.minimal_quantity, COALESCE(sa.quantity,0) AS quantity,
          COALESCE(sa.out_of_stock,2) AS out_of_stock, COALESCE(sa.depends_on_stock,0) AS depends_on_stock
          FROM {$prefix}product_attribute pa JOIN {$prefix}product_attribute_shop pas
          ON pas.id_product_attribute=pa.id_product_attribute AND pas.id_shop=1
          LEFT JOIN {$prefix}stock_available sa ON sa.id_product=pa.id_product
          AND sa.id_product_attribute=pa.id_product_attribute AND sa.id_shop=1 ORDER BY pa.id_product_attribute")->fetch_all(MYSQLI_ASSOC);
        $attrs = $db->query("SELECT pac.id_product_attribute, a.id_attribute, ag.id_attribute_group, agl.name AS group_name, al.name AS label
          FROM {$prefix}product_attribute_combination pac JOIN {$prefix}attribute a ON a.id_attribute=pac.id_attribute
          JOIN {$prefix}attribute_group ag ON ag.id_attribute_group=a.id_attribute_group
          JOIN {$prefix}attribute_lang al ON al.id_attribute=a.id_attribute AND al.id_lang=$lang
          JOIN {$prefix}attribute_group_lang agl ON agl.id_attribute_group=ag.id_attribute_group AND agl.id_lang=$lang
          ORDER BY pac.id_product_attribute, a.id_attribute")->fetch_all(MYSQLI_ASSOC);
        $byCombination = [];
        foreach ($attrs as $attr) { $byCombination[$attr['id_product_attribute']][] = $attr; }
        foreach ($rows as $row) {
            if (!isset($products[$row['id_product']])) { continue; }
            $row['id'] = (int)$row['id']; $row['attributes'] = $byCombination[$row['id']] ?? [];
            $products[$row['id_product']]['combinations'][] = $row;
        }
        $rows = $db->query("SELECT * FROM {$prefix}specific_price ORDER BY id_specific_price")->fetch_all(MYSQLI_ASSOC);
        foreach ($rows as $row) { if (isset($products[$row['id_product']])) { $products[$row['id_product']]['specific_prices'][] = $row; } }
        $db->commit();
        return ['target' => TEST_HOST . '/mercaboy_pruebas/1', 'products' => array_values($products), 'lang' => $lang];
    } catch (Throwable $e) { $db->rollback(); throw $e; }
}
function boot(?string $httpHost = null, bool $withKernel = false): void {
    $_SERVER['HTTP_HOST'] = $httpHost ?? TEST_HOST; $_SERVER['SERVER_NAME'] = $httpHost ?? TEST_HOST;
    $_SERVER['REMOTE_ADDR'] = '127.0.0.1'; $_SERVER['REQUEST_URI'] = '/';
    // Bootstrap can use cached appParameters.php instead of parameters.php.
    // Inspect generated cache text without require: require_once later must still return its array.
    foreach (glob('/var/www/html/var/cache/*/appParameters.php') as $cached) {
        $source = file_get_contents($cached);
        foreach (['database_host'=>['localhost','127.0.0.1',TEST_HOST], 'database_name'=>['mercaboy_pruebas']] as $key=>$allowed) {
            $pattern = '/[\'"]' . $key . '[\'"]\s*=>\s*[\'"]([^\'"]+)[\'"]/';
            demand(preg_match($pattern, $source, $match) === 1 && in_array($match[1], $allowed, true), 'Cache de conexion apunta fuera de pruebas o formato no reconocido');
        }
    }
    require_once '/var/www/html/config/config.inc.php';
    demand(_DB_NAME_ === 'mercaboy_pruebas', 'Bootstrap intento acceder a otra base');
    demand(in_array(_DB_SERVER_, ['localhost','localhost:3306','127.0.0.1','127.0.0.1:3306',TEST_HOST,TEST_HOST . ':3306'], true), 'Bootstrap con servidor distinto de pruebas');
    if ($withKernel) {
        ObjectModel::disableCache();
        global $kernel;
        $kernel = new AppKernel('prod', false);
        $kernel->boot();
    }
    Shop::setContext(Shop::CONTEXT_SHOP, 1);
    $context = Context::getContext(); $context->shop = new Shop(1);
    $context->language = new Language((int)Configuration::get('PS_LANG_DEFAULT'));
    $context->currency = new Currency((int)Configuration::get('PS_CURRENCY_DEFAULT'));
    $context->country = new Country((int)Configuration::get('PS_COUNTRY_DEFAULT'));
    $context->customer = new Customer();
    $context->cart = new Cart(); // In-memory context; no cart/order is persisted.
    $context->cart->id_shop = 1;
    $context->cart->id_currency = $context->currency->id;
    $context->cart->id_lang = $context->language->id;
}
function normalized(string $s): string {
    return mb_strtolower(str_replace(['ó','Ó'], ['o','O'], trim($s)));
}
function attributeId(string $label): int {
    $lang = (int)Configuration::get('PS_LANG_DEFAULT'); $groups = [];
    foreach (AttributeGroup::getAttributesGroups($lang) as $group) {
        if (normalized($group['name']) === 'presentacion') { $groups[] = $group; }
    }
    demand(count($groups) <= 1, 'Existen varios grupos Presentacion');
    if (!$groups) {
        $group = new AttributeGroup(); $group->group_type = 'select'; $group->is_color_group = false;
        foreach (Language::getLanguages(false) as $language) {
            $group->name[$language['id_lang']] = 'Presentación'; $group->public_name[$language['id_lang']] = 'Presentación';
        }
        demand($group->add(), 'No se pudo crear grupo'); $groupId = (int)$group->id;
    } else { $groupId = (int)$groups[0]['id_attribute_group']; }
    $matches = [];
    foreach (AttributeGroup::getAttributes($lang, $groupId) as $attr) {
        if (normalized($attr['name']) === normalized($label)) { $matches[] = $attr; }
    }
    demand(count($matches) <= 1, 'Valores de atributo duplicados');
    if ($matches) { return (int)$matches[0]['id_attribute']; }
    $attr = new ProductAttribute(); $attr->id_attribute_group = $groupId;
    foreach (Language::getLanguages(false) as $language) { $attr->name[$language['id_lang']] = $label; }
    demand($attr->add(), 'No se pudo crear atributo'); return (int)$attr->id;
}
function verifyProduct(array $operation): array {
    $product = new Product((int)$operation['id'], false, null, 1);
    demand(abs((float)$product->price - (float)$operation['base_price']) < 0.00001, 'Precio padre distinto del aprobado');
    if ($operation['stage_disabled']) { demand(!(bool)$product->active, 'El borrador no debe estar activo'); }
    if (!empty($operation['preview_only'])) { demand((bool)$product->active && !(bool)$product->available_for_order, 'La vista previa debe estar visible con compra deshabilitada'); }
    $result = [];
    foreach ($operation['presentations'] as $item) {
        $id = (int)$item['combination_id'];
        if ($id) {
            $combo = new Combination($id, null, 1);
            demand((int)$combo->id_product === (int)$product->id, 'Combinacion ajena');
            demand(abs((float)$combo->price - (float)$item['impact']) < 0.00001, 'Impacto no coincide');
            demand($combo->reference === $item['reference'], 'Referencia no coincide');
            demand((int)$combo->minimal_quantity === 1, 'Minimo debe ser 1 presentacion');
            if ($item['default']) { demand((int)$product->cache_default_attribute === $id, 'Predeterminada incorrecta'); }
        }
        $specific = null;
        $net = Product::getPriceStatic($product->id, false, $id ?: false, 6, null, false, false, 1, false, null, null, null, $specific, false, false);
        $visible = Product::getPriceStatic($product->id, true, $id ?: false, 6);
        demand(abs($net-(float)$item['net_price']) < 0.01, 'Motor de precios difiere: revisar precios especificos y reglas fiscales');
        $quantity = StockAvailable::getQuantityAvailableByProduct($product->id, $id, 1);
        if ($item['quantity'] !== null) { demand($quantity === (int)$item['quantity'], 'Stock distinto del aprobado'); }
        $result[] = ['combination_id'=>$id, 'reference'=>$item['reference'], 'net_price'=>$net, 'visible_price'=>$visible, 'quantity'=>$quantity];
    }
    if (count($result) > 1) { demand(count(array_unique(array_column($result, 'visible_price'))) === count($result), 'El motor devuelve precios visibles iguales; revisar promociones'); }
    return ['id'=>(int)$product->id, 'prices'=>$result];
}
function applyProduct(array $operation): array {
    $db = Db::getInstance(); demand($db->execute('START TRANSACTION'), 'No inicio transaccion');
    try {
        $product = new Product((int)$operation['id'], false, null, 1);
        demand(Validate::isLoadedObject($product), 'Producto inexistente');
        $product->price = $operation['base_price'];
        if ($operation['stage_disabled']) { $product->active = false; }
        if (!empty($operation['preview_only'])) { $product->active = true; $product->available_for_order = false; }
        if (!empty($operation['new_name'])) {
            $product->name[(int)Configuration::get('PS_LANG_DEFAULT')] = $operation['new_name'];
        }
        demand($product->update(), 'No se pudo actualizar producto');
        $default = 0;
        foreach ($operation['presentations'] as &$item) {
            if ($operation['mode'] === 'simple') { continue; }
            $id = (int)$item['combination_id']; $combo = new Combination($id ?: null, null, 1);
            if ($id) { demand((int)$combo->id_product === (int)$product->id, 'Combinacion ajena'); }
            $combo->id_product = (int)$product->id; $combo->price = $item['impact'];
            $combo->reference = $item['reference']; $combo->minimal_quantity = 1;
            // Preserve EAN/images/other fields on existing combinations. New fractions have no invented EAN.
            if ($id) { demand($combo->update(), 'No se pudo actualizar combinacion'); }
            else {
                $combo->ean13 = ''; demand($combo->add(), 'No se pudo crear combinacion');
                demand($combo->setAttributes([attributeId($item['label'])]), 'No se pudo asociar atributo');
            }
            $item['combination_id'] = (int)$combo->id;
            if ($item['default']) { $default = (int)$combo->id; }
            if ($item['quantity'] !== null) {
                StockAvailable::setQuantity((int)$product->id, (int)$combo->id, (int)$item['quantity'], 1);
                StockAvailable::setProductOutOfStock((int)$product->id, 0, 1, (int)$combo->id);
            }
        }
        unset($item);
        if ($operation['mode'] !== 'simple') {
            demand($default > 0, 'Falta predeterminada');
            demand($product->deleteDefaultAttributes() && $product->setDefaultAttribute($default), 'No se pudo establecer predeterminada');
        }
        Product::flushPriceCache();
        $verification = verifyProduct($operation);
        demand($db->execute('COMMIT'), 'No se pudo confirmar');
        return ['operation'=>$operation, 'verification'=>$verification];
    } catch (Throwable $e) { $db->execute('ROLLBACK'); Product::flushPriceCache(); throw $e; }
}

if (defined('MERCABOY_LIBRARY_ONLY')) { return; }

try {
    $request = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
    $parameters = localParameters($request); $connection = connection($request, $parameters);
    $command = $argv[1] ?? 'snapshot';
    if ($command === 'snapshot') { $result = snapshot($connection, $parameters, $request['ids'] ?? []); }
    elseif ($command === 'prices') {
        $current = snapshot($connection, $parameters, $request['ids'] ?? []);
        demand(count($current['products']) <= 20, 'Limite 20 productos para prices');
        boot(); $result = [];
        foreach ($current['products'] as $row) {
            $prices = [];
            foreach ($row['combinations'] ?: [['id'=>0, 'reference'=>$row['reference']]] as $combo) {
                $id = (int)$combo['id'];
                $prices[] = ['combination_id'=>$id, 'reference'=>$combo['reference'],
                    'net_without_reduction'=>Product::getPriceStatic($row['id'], false, $id ?: false, 6, null, false, false),
                    'visible_price'=>Product::getPriceStatic($row['id'], true, $id ?: false, 6)];
            }
            $result[] = ['id'=>$row['id'], 'prices'=>$prices];
        }
    }
    elseif ($command === 'apply' || $command === 'verify') {
        $operation = $request['operation'];
        $current = snapshot($connection, $parameters, [(int)$operation['id']]);
        if ($command === 'apply') {
            demand(in_array($request['authorization'] ?? '', ['CSV_REVIEWED_TEST_ONLY', 'CLI_APPLY_TEST_ONLY'], true), 'Falta autorizacion del controlador');
            demand($current['products'][0] == $operation['before'], 'Producto cambio desde la auditoria: regenere el plan');
        }
        boot(null, $command === 'apply');
        $result = $command === 'apply' ? applyProduct($operation) : verifyProduct($operation);
    } else { throw new RuntimeException('Comando desconocido'); }
    echo json_encode($result, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR), PHP_EOL;
} catch (Throwable $e) {
    // Never print database exceptions: they can include credentials or SQL data.
    $message = $e instanceof RuntimeException && !($e instanceof mysqli_sql_exception) ? $e->getMessage() : 'Fallo interno de conexion/PrestaShop; revise configuracion local';
    fwrite(STDERR, $message . ' [' . get_class($e) . ':' . $e->getCode() . ', linea ' . $e->getLine() . ']' . PHP_EOL); exit(1);
}
